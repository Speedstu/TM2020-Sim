// SPDX-License-Identifier: GPL-3.0-or-later
// Real recovered physics. No replay, demonstration route or map identity in X.
// Static rays and approximate swept-AABB waypoint tracking are also used live.
use anyhow::{Result,Context,ensure};
use gearbox_engine::{Controls,Session,Savestate,Vec3,Mat3};
use std::{ffi::{CStr,CString,c_char,c_void},cell::RefCell,path::Path,sync::Arc};
const NX:usize=48;
const POTENTIAL_SHAPING:bool=cfg!(feature="progress-shaping");
const MINIMUM_TIME:bool=cfg!(feature="minimum-time");
mod minimum_time_reward;
mod preview;
use minimum_time_reward::Outcome;

#[repr(C)]
#[derive(Clone)]
pub struct Output { observation:[f64;NX],reward:f64,progress:f64,cross_track:f64,speed:f64,
 rigid_words:[u32;22],tick:u32,checkpoints:u32,terminated:u32,truncated:u32,
 advanced_ticks:u32,finish_ms:i32,controls:[f32;3],reserved:u32 }
#[derive(Clone)]
struct Mark { id:u32,kind:u32,order:u32,min:[f32;3],max:[f32;3] }
impl Mark {fn center(&self)->Vec3{Vec3::from(std::array::from_fn(|k|(self.min[k]+self.max[k])*0.5))}}
#[derive(Clone,Default)]
struct Tracker { visited:Vec<u32>,previous:Option<[f32;3]> }
#[derive(Clone)]
struct Bank { saved:Savestate,tracker:Tracker,tick:u32,previous:[f32;3],travel:f64,route_index:usize,route_best:f64 }
#[derive(Clone)]
struct TrainingRoute { points:Vec<[f32;3]>,arc:Vec<f64> }
impl TrainingRoute {
 fn locate(&self,pos:Vec3,index:usize)->(usize,f64,f64){
  let mut best=(index,self.arc[index],f64::INFINITY);
  for i in index.saturating_sub(8)..(index+12).min(self.points.len()-1){
   let a=Vec3::from(self.points[i]);let d=Vec3::from(self.points[i+1])-a;
   let n=d.dot(d);let f=if n>0.{((pos-a).dot(d)/n).clamp(0.,1.)}else{0.};
   let delta=pos-(a+d*f);let cross=f64::from(delta.dot(delta));
   if cross<best.2{best=(i,self.arc[i]+f64::from(f)*(self.arc[i+1]-self.arc[i]),cross);}
  }best
 }
}
impl Tracker {
 fn update(&mut self,marks:&[Mark],p:[f32;3]) {
  if let Some(a)=self.previous {
   // Discontinuities are restarts/respawns, never swept checkpoint crossings.
   if (Vec3::from(p)-Vec3::from(a)).dot(Vec3::from(p)-Vec3::from(a))<2500. {
    for m in marks.iter().filter(|m|m.kind==2) {
     let (mut lo,mut hi)=(0f32,1f32);
     for k in 0..3 {let d=p[k]-a[k];
      if d.abs()<1e-6 {if a[k]<m.min[k]||a[k]>m.max[k]{hi=-1.;break;}}
      else {let x=(m.min[k]-a[k])/d;let y=(m.max[k]-a[k])/d;lo=lo.max(x.min(y));hi=hi.min(x.max(y));}
     }
     if hi>=lo&&!self.visited.contains(&m.id){self.visited.push(m.id);}
    }
   }
  }
  self.previous=Some(p);
 }
 fn goal<'a>(&self,marks:&'a [Mark],p:Vec3)->Option<&'a Mark> {
  let candidates:Vec<_>=marks.iter().filter(|m|m.kind==2&&!self.visited.contains(&m.id)).collect();
  let order=candidates.iter().map(|m|m.order).min();
  let pool:Vec<_>=if let Some(order)=order {candidates.into_iter().filter(|m|m.order==order).collect()}
   else {marks.iter().filter(|m|m.kind==1||m.kind==4).collect()};
  pool.into_iter().min_by(|a,b|{let d=a.center()-p;let e=b.center()-p;d.dot(d).total_cmp(&e.dot(e))})
 }
}
#[derive(Clone)]
struct Env {session:Session,initial:Savestate,marks:Arc<Vec<Mark>>,tracker:Tracker,horizon:u32,tick:u32,internal_controls:bool,launch_delta:f32,
 previous:[f32;3],done:bool,failed:bool,travel:f64,stuck:u32,banks:Arc<Vec<Bank>>,
 training_route:Option<Arc<TrainingRoute>>,route_index:usize,route_best:f64,route_cross_squared:f64}
impl Env {
 fn open(map:&Path,packs:&Path,horizon:u32)->Result<Self>{
  ensure!((1..=100000).contains(&horizon),"invalid horizon");
  let mut session=gearbox_world::open_file(map,packs,gearbox_world::OpenOptions{t0:-1500,seed:Some(2026),car:None})?;
  for _ in 0..150{session.step(Controls::default());}ensure!(session.race_ms()==0,"race zero missing");
  ensure!(!session.race.rules.lap_race&&session.race.rules.laps<=1,"multilap navigation is not implemented");
  let marks:Vec<_>=session.waypoint_triggers().iter().map(|m|Mark{id:m.waypoint,kind:m.kind,
   order:session.waypoint_order(m.waypoint).unwrap_or(0),min:m.min,max:m.max}).collect();
  ensure!(marks.iter().any(|m|m.kind==1||m.kind==4),"no map finish geometry");
  let initial=session.save();let mut e=Self{session,initial,marks:Arc::new(marks),tracker:Tracker::default(),
   horizon,tick:0,internal_controls:false,launch_delta:0.,previous:[0.;3],done:false,failed:false,travel:0.,stuck:0,banks:Arc::new(Vec::new()),
   training_route:None,route_index:0,route_best:0.,route_cross_squared:0.};
  e.tracker.update(&e.marks,e.session.body().pos.to_array());Ok(e)
 }
 fn raw(&self)->[f32;21]{
  let b=self.session.body();let v=self.session.vehicle();let mut r=[0.;21];
  r[..3].copy_from_slice(&b.pos.to_array());r[3..12].copy_from_slice(&b.rot.to_array());
  r[12..15].copy_from_slice(&b.vel.to_array());r[15..18].copy_from_slice(&self.previous);
  r[18]=v.gear as f32;r[19]=f32::from(v.support_contact_count>0);r[20]=f32::from(v.turbo_active!=0);r
 }
 fn observation(&self,raw:&[f32;21],tracker:&Tracker)->Result<[f64;NX]>{
  ensure!(raw.iter().all(|x|x.is_finite()&&x.abs()<100000.),"bad external telemetry");
  let pos=Vec3::from([raw[0],raw[1],raw[2]]);let rot=Mat3::from_array(raw[3..12].try_into().unwrap());
  for i in 0..3 {for j in 0..3 {let x=rot.rows[i].dot(rot.rows[j]);ensure!((x-if i==j{1.}else{0.}).abs()<0.03,"nonorthogonal telemetry");}}
  let vel=rot.transpose_mul_vec(Vec3::from([raw[12],raw[13],raw[14]]));
  let up=rot.transpose_mul_vec(Vec3::new(0.,1.,0.));let mut x=[0.;NX];
  for k in 0..3{x[k]=f64::from(vel[k])/100.;x[3+k]=f64::from(up[k]);x[9+k]=f64::from(raw[15+k]);}
  if let Some(m)=tracker.goal(&self.marks,pos){let d=rot.transpose_mul_vec(m.center()-pos);
   for k in 0..3{x[6+k]=(f64::from(d[k])/100.).clamp(-4.,4.);}}
  x[12]=f64::from(raw[18])/6.;x[13]=f64::from(raw[19]);x[14]=f64::from(raw[20]);
  let ray=|origin:[f32;3],delta:[f32;3]|->f64{
   self.session.pick_static(pos+rot*Vec3::from(origin),rot*Vec3::from(delta)).map_or(1.,|h|f64::from(h.fraction).clamp(0.,1.))};
  let mut n=15;
  for y in [0.5,2.] {for i in 0..11 {let a=(i as f32-5.)*std::f32::consts::PI/12.;
   x[n]=ray([0.,y,0.],[80.*a.sin(),0.,80.*a.cos()]);n+=1;}}
  for (a,b) in [(0.,0.),(-4.,8.),(0.,8.),(4.,8.),(-6.,20.),(0.,20.),(6.,20.),(-10.,40.),(0.,40.),(10.,40.),(0.,65.)]{
   x[n]=ray([a,6.,b],[0.,-24.,0.]);n+=1;}
  ensure!(x.iter().all(|v|v.is_finite()),"nonfinite observation");Ok(x)
 }
 fn potential(&self)->Result<f64>{
  if cfg!(feature="recovery-progress") {if let Some(route)=&self.training_route {
   return Ok(100.*(self.route_best/route.arc.last().copied().unwrap_or(1.)).clamp(0.,1.)-0.05*self.route_cross_squared.min(400.));
  }}
  if !POTENTIAL_SHAPING{return Ok(0.);}
  let race=self.session.race().context("no race potential")?;let pos=self.session.body().pos;
  let distance=self.tracker.goal(&self.marks,pos).map_or(0.,|g|{let d=g.center()-pos;f64::from(d.dot(d).sqrt()).min(300.)});
  Ok(5.*race.checkpoints.len() as f64-0.02*distance)
 }
 fn output(&self,reward:f64,advanced:u32)->Result<Output>{
  let r=self.session.race().context("no race")?;let b=self.session.body();let v=b.vel.dot(b.vel).sqrt();
  Ok(Output{observation:self.observation(&self.raw(),&self.tracker)?,reward,progress:self.travel,cross_track:0.,speed:f64::from(v),
   rigid_words:gearbox_trace::typed::state(&self.session).body.floats().map(f32::to_bits),tick:self.tick,
   checkpoints:r.checkpoints.len() as u32,terminated:u32::from(r.finish.is_some()||(MINIMUM_TIME&&self.done)),truncated:u32::from(!MINIMUM_TIME&&self.done&&r.finish.is_none()),
   advanced_ticks:advanced,finish_ms:r.finish.map_or(-1,|t|t as i32),controls:self.previous,reserved:0})
 }
 fn reset(&mut self,seed:u32)->Result<Output>{self.session.restore(&self.initial);self.session.seed=Some(seed);
  self.tracker=Tracker::default();self.tracker.update(&self.marks,self.session.body().pos.to_array());
  self.tick=0;self.previous=[0.;3];self.done=false;self.failed=false;self.travel=0.;self.stuck=0;
  self.route_index=0;self.route_best=0.;self.route_cross_squared=0.;self.output(0.,0)}
 fn reset_bank(&mut self,seed:u32,bank:usize)->Result<Output>{
  if bank==0{return self.reset(seed);}
  let b=self.banks.get(bank-1).context("unknown complete curriculum snapshot")?;
  ensure!(b.tick<self.horizon,"curriculum snapshot exceeds horizon");
  self.session.restore(&b.saved);self.session.seed=Some(seed);self.tracker=b.tracker.clone();self.tick=b.tick;
  self.previous=b.previous;self.travel=b.travel;self.done=false;self.failed=false;self.stuck=0;
  self.route_index=b.route_index;self.route_best=b.route_best;self.route_cross_squared=0.;self.output(0.,0)
 }
 #[cfg(feature="replay-curriculum")]
 fn load_banks(&mut self,map:&Path,packs:&Path,replay:&Path)->Result<()>{
  let parsed=gearbox_gbx::Map::parse(&std::fs::read(map)?)?;
  let r=gearbox_gbx::Replay::parse(&std::fs::read(replay)?)?;
  ensure!(r.map_uid==parsed.uid,"curriculum replay UID differs");
  let record=gearbox_run::Record::from_replay(&r)?;
  ensure!(record.respawns.is_empty()&&record.run.t0<=0,"curriculum requires a complete replay without respawns");
  let set=gearbox_packs::packs::PackSet::open(packs)?;let mut session=record.open(&parsed,&set)?;
  let mut tracker=Tracker::default();let mut banks=Vec::new();let mut finish=None;let mut travel=0.;
  let mut points:Vec<[f32;3]>=Vec::new();let mut arc=Vec::new();let mut route_distance=0.;
  for tick in 0..30000 {
   let now=session.race_ms();
   if now>=0 {
    tracker.update(&self.marks,session.body().pos.to_array());
    let pos=session.body().pos;
    let distance=points.last().map_or(1.,|p|{let d=pos-Vec3::from(*p);f64::from(d.dot(d).sqrt())});
    if points.is_empty()||distance>0.05 {
     if !points.is_empty(){route_distance+=distance;}
     points.push(pos.to_array());arc.push(route_distance);
    }
    if now>0&&now%500==0&&now<record.time_ms-250&&now<self.horizon as i32*10{
     let c=session.applied;banks.push(Bank{saved:session.save(),tracker:tracker.clone(),tick:now as u32/10,
        previous:[c.gas,c.brake,c.steer],travel,route_index:points.len()-1,route_best:route_distance});
    }
   }
   let before=session.body().pos;
   ensure!(record.step(&mut session,tick),"unsupported curriculum respawn");
   if session.vehicle.body!=u32::MAX {let d=session.body().pos-before;travel+=f64::from(d.dot(d).sqrt());}
   finish=session.race().and_then(|r|r.finish);if finish.is_some(){break;}
  }
  ensure!(finish==Some(record.time_ms as u32),"curriculum source does not reproduce its finish");
  ensure!(!banks.is_empty()&&points.len()>20,"no curriculum snapshots generated");self.banks=Arc::new(banks);
  self.training_route=Some(Arc::new(TrainingRoute{points,arc}));Ok(())
 }
 fn time_reward(&self,before:f64,after:f64,elapsed:f64,outcome:Outcome)->Result<f64>{
  Ok(if cfg!(feature="recovery-progress") {
   minimum_time_reward::recovery_reward(before,after,elapsed,outcome,self.potential()?)
  }else{minimum_time_reward::reward(before,after,elapsed,outcome)})
 }
 fn step(&mut self,c:[f32;3],repeat:u32)->Result<Output>{
  ensure!(!self.done&&!self.failed,"reset required");ensure!((1..=100).contains(&repeat)&&c.iter().all(|x|x.is_finite())&&
   (0.0..=1.0).contains(&c[0])&&(0.0..=1.0).contains(&c[1])&&c[2].abs()<=1.,"bad controls/repeat");
  let before_phi=if MINIMUM_TIME{self.potential()?}else{0.};let before_ms=self.session.race_ms();
  self.failed=true;let cp=self.session.race().context("no race")?.checkpoints.len();
  let mut reward=0.;let mut advanced=0;
  for _ in 0..repeat.min(self.horizon-self.tick){
   let before=self.session.body().pos;
   let goal=self.tracker.goal(&self.marks,before).map(|m|m.center());
   let controls=Controls{gas:c[0],brake:c[1],steer:c[2]};
   if self.internal_controls {
    // Match the DLL's physical consumer: apply commands while leaving the
    // device input history untouched. Do not manufacture input-change events
    // and their seed-dependent start adjustments at 5/10/15 seconds.
    let input=self.session.input;self.session.step_with_input(controls,input);
   }else{self.session.step(controls);}
   self.tick+=1;advanced+=1;
   // Explicit simulator-only launch uncertainty, applied once at 20 ms.
   // Zero leaves the original physics path bit-identical. No midrace resets
   // or position correction, and this is never applied to an actual client.
   if self.tick==2&&self.launch_delta!=0.&&self.session.vehicle.body!=u32::MAX {
    let delta=self.session.body().rot*Vec3::new(0.,0.,self.launch_delta);
    let velocity=self.session.body().vel+delta;
    self.session.dyna.set_velocity(gearbox_engine::dyna::BodyHandle(self.session.vehicle.body),velocity);
    self.session.vehicle.vel=self.session.vehicle.vel+delta;
   }
   // A parked/frozen vehicle can legitimately lose its dynamic body. Treat
   // this as an absorbing episode end; never index the null body handle or
   // invent a rigid state. reserved=1 explicitly marks absent car physics.
   if self.session.vehicle.body==u32::MAX {
    self.done=true;self.previous=c;
    let r=self.session.race().context("no race at body removal")?;
    let finished=r.finish.is_some();
    reward+=10.*r.checkpoints.len().saturating_sub(cp) as f64;
    reward+=if finished{100.}else{-5.};
    if MINIMUM_TIME{
     let end=r.finish.map_or(self.session.race_ms() as f64,|t|t as f64);
     reward=self.time_reward(before_phi,0.,(end-f64::from(before_ms)).max(0.)/1000.,if finished{Outcome::Finish}else{Outcome::Failure{remaining_seconds:(f64::from(self.horizon)*0.01-end/1000.).max(0.)}})?;
    }
    self.failed=false;
    return Ok(Output{observation:[0.;NX],reward,progress:self.travel,cross_track:0.,speed:0.,
     rigid_words:[0;22],tick:self.tick,checkpoints:r.checkpoints.len() as u32,
     terminated:1,truncated:0,advanced_ticks:advanced,finish_ms:r.finish.map_or(-1,|t|t as i32),
     controls:self.previous,reserved:1});
   }
   let after=self.session.body().pos;self.tracker.update(&self.marks,after.to_array());
   if cfg!(feature="recovery-progress"){if let Some(route)=&self.training_route{
    let (index,progress,cross)=route.locate(after,self.route_index);self.route_index=index;self.route_best=self.route_best.max(progress);self.route_cross_squared=cross;
   }}
   let d=after-before;let distance=f64::from(d.dot(d).sqrt());self.travel+=distance;
   self.stuck=if distance>0.02{0}else{self.stuck+1};
   if let Some(g)=goal {let a=g-before;let b=g-after;reward+=0.05*f64::from(a.dot(a).sqrt()-b.dot(b).sqrt());}
   reward-=0.002;
   if self.session.race().is_some_and(|r|r.finish.is_some())||self.tick>=self.horizon||self.stuck>=400{
    self.done=true;break;}
  }
  self.previous=c;let r=self.session.race().context("no race")?;
  reward+=10.*r.checkpoints.len().saturating_sub(cp) as f64;
  if r.finish.is_some(){reward+=100.;}else if self.done{reward-=5.;}
  if MINIMUM_TIME{
   let end=r.finish.map_or(self.session.race_ms() as f64,|t|t as f64);
   let outcome=if r.finish.is_some(){Outcome::Finish}else if self.done{Outcome::Failure{remaining_seconds:(f64::from(self.horizon)*0.01-end/1000.).max(0.)}}else{Outcome::Running};
   let after_phi=if self.done{0.}else{self.potential()?};
   reward=self.time_reward(before_phi,after_phi,(end-f64::from(before_ms)).max(0.)/1000.,outcome)?;
  }
  let result=self.output(reward,advanced);if result.is_ok(){self.failed=false;}result
 }
}
thread_local!{static ERROR:RefCell<CString>=RefCell::new(CString::new("").unwrap());}
fn attempt<T>(f:impl FnOnce()->Result<T>)->Option<T>{match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)){
 Ok(Ok(v))=>Some(v),other=>{let msg=match other{Ok(Err(e))=>format!("{e:#}"),_=>"physics panic: reset required".into()};
 ERROR.with(|e|*e.borrow_mut()=CString::new(msg.replace('\0'," ")).unwrap());None}}}
unsafe fn env<'a>(p:*mut c_void)->Result<&'a mut Env>{ensure!(!p.is_null(),"null environment");Ok(unsafe{&mut *p.cast::<Env>()})}
unsafe fn path<'a>(p:*const c_char)->Result<&'a Path>{ensure!(!p.is_null(),"null path");Ok(Path::new(unsafe{CStr::from_ptr(p)}.to_str()?))}
#[unsafe(no_mangle)]pub extern "C" fn tmgen_reward_version()->u32{if !MINIMUM_TIME{1}else if cfg!(feature="recovery-progress"){4}else if POTENTIAL_SHAPING{2}else{3}}
#[unsafe(no_mangle)]pub extern "C" fn tmfast_version()->u32{4}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_set_control_mode(p:*mut c_void,mode:u32)->i32{
 attempt(||{ensure!(mode<=1,"invalid control mode");let e=unsafe{env(p)?};
 ensure!(e.tick==0&&!e.done&&!e.failed,"control mode can change only at race zero");
 e.internal_controls=mode==1;Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_control_mode(p:*mut c_void)->u32{
 attempt(||Ok(u32::from(unsafe{env(p)?}.internal_controls))).unwrap_or(u32::MAX)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_input_adjustments(p:*mut c_void)->u32{
 attempt(||Ok(unsafe{env(p)?}.session.race.players.first().and_then(|p|p.controller.as_ref())
  .map_or(0,|c|u32::from(c.start_adjustments&3)))).unwrap_or(u32::MAX)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_launch_uncertainty(p:*mut c_void,delta:f32)->i32{
 attempt(||{ensure!(delta.is_finite()&&delta.abs()<=0.1,"launch uncertainty outside +/-0.1 m/s");
 let e=unsafe{env(p)?};ensure!(e.tick==0&&!e.done&&!e.failed,"launch uncertainty must be set at race zero");
 e.launch_delta=delta;Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub extern "C" fn tmfast_last_error()->*const c_char{ERROR.with(|e|e.borrow().as_ptr())}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_open(m:*const c_char,p:*const c_char,_r:*const c_char,h:u32)->*mut c_void{
 attempt(||{let mut e=unsafe{Env::open(path(m)?,path(p)?,h)}?;
  #[cfg(feature="replay-curriculum")]
  {let replay=unsafe{path(_r)?};if !replay.as_os_str().is_empty()&&replay!=Path::new("/dev/null") {e.load_banks(unsafe{path(m)?},unsafe{path(p)?},replay)?;}}
  Ok(e)}).map_or(std::ptr::null_mut(),|e|Box::into_raw(Box::new(e)).cast())}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_clone(p:*mut c_void)->*mut c_void{
 attempt(||Ok(unsafe{env(p)?}.clone())).map_or(std::ptr::null_mut(),|e|Box::into_raw(Box::new(e)).cast())}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_bank_size(p:*mut c_void)->u32{attempt(||Ok(1+unsafe{env(p)?}.banks.len() as u32)).unwrap_or(0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_configure(p:*mut c_void,_l:f64,_g:f64,r:f64)->i32{
 attempt(||{unsafe{env(p)?};ensure!(r==1.,"direct policy needs residual=1");Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_configure_planner(p:*mut c_void,on:u32)->i32{
 attempt(||{unsafe{env(p)?};ensure!(on==0,"no replay/MPC controller here");Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_reset(p:*mut c_void,seed:u32,o:*mut Output)->i32{
 attempt(||{ensure!(!o.is_null(),"null output");unsafe{*o=env(p)?.reset(seed)?};Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_reset_bank(p:*mut c_void,seed:u32,bank:u32,o:*mut Output)->i32{
 attempt(||{ensure!(!o.is_null(),"null reset bank output");unsafe{*o=env(p)?.reset_bank(seed,bank as usize)?};Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_step_controls(p:*mut c_void,c:*const f32,r:u32,o:*mut Output)->i32{
 attempt(||{ensure!(!c.is_null()&&!o.is_null(),"null arguments");let a=unsafe{std::slice::from_raw_parts(c,3)};
 unsafe{*o=env(p)?.step([a[0],a[1],a[2]],r)?};Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_step(p:*mut c_void,c:*const f64,r:u32,o:*mut Output)->i32{
 attempt(||{ensure!(!c.is_null()&&!o.is_null(),"null arguments");let a=unsafe{std::slice::from_raw_parts(c,3)};
 ensure!(a.iter().all(|x|x.is_finite()&&x.abs()<=1.),"bad action");
 let c=[f32::from(a[0]>=0.),f32::from(a[1]>=0.),(a[2]*127.).round() as f32/127.];
 unsafe{*o=env(p)?.step(c,r)?};Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_close(p:*mut c_void){if !p.is_null(){drop(unsafe{Box::from_raw(p.cast::<Env>())});}}
// External perception never advances or places the physics car. Tracker is caller-local.
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmgen_observe(p:*mut c_void,raw:*const f32,reset:u32,o:*mut f64)->i32{
 attempt(||{ensure!(!raw.is_null()&&!o.is_null()&&reset<=1,"bad observation arguments");
 let e=unsafe{env(p)?};let r:&[f32;21]=unsafe{std::slice::from_raw_parts(raw,21)}.try_into().unwrap();
 let mut t=if reset!=0{Tracker::default()}else{e.tracker.clone()};
 // Validate BEFORE accepting a new tracker position.
 let _=e.observation(r,&t)?;t.update(&e.marks,[r[0],r[1],r[2]]);let x=e.observation(r,&t)?;
 unsafe{std::ptr::copy_nonoverlapping(x.as_ptr(),o,NX)};e.tracker=t;Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmgen_track_pose(p:*mut c_void,pos:*const f32,reset:u32)->i32{
 attempt(||{ensure!(!pos.is_null()&&reset<=1,"bad tracking arguments");
 let e=unsafe{env(p)?};let v=unsafe{std::slice::from_raw_parts(pos,3)};
 ensure!(v.iter().all(|x|x.is_finite()&&x.abs()<100000.),"bad tracking position");
 if reset!=0{e.tracker=Tracker::default();}e.tracker.update(&e.marks,[v[0],v[1],v[2]]);Ok(())}).map_or(-1,|_|0)}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmgen_raw(p:*mut c_void,o:*mut f32)->i32{
 attempt(||{ensure!(!o.is_null(),"null raw output");let r=unsafe{env(p)?}.raw();unsafe{std::ptr::copy_nonoverlapping(r.as_ptr(),o,21)};Ok(())}).map_or(-1,|_|0)}

pub fn export_demonstration(map:&Path,packs:&Path,replay:&Path,output:&Path)->Result<serde_json::Value>{
 use std::io::Write;
 let parsed=gearbox_gbx::Map::parse(&std::fs::read(map)?)?;
 let replay=gearbox_gbx::Replay::parse(&std::fs::read(replay)?)?;
 ensure!(replay.map_uid==parsed.uid,"demonstration UID differs");
 let record=gearbox_run::Record::from_replay(&replay)?;
 ensure!(record.respawns.is_empty()&&record.run.t0<=0,"partial/respawning demonstration unsupported");
 let mut e=Env::open(map,packs,10000)?;
 let set=gearbox_packs::packs::PackSet::open(packs)?;e.session=record.open(&parsed,&set)?;
 e.tracker=Tracker::default();
 let mut out=std::fs::OpenOptions::new().write(true).create_new(true).open(output)?;
 for i in 0..48{write!(out,"x{i},")?;}writeln!(out,"gas,brake,steer")?;
 let mut rows=0;let mut finish=None;
 for tick in 0..30000{
  let now=e.session.race_ms();
  if now>=0 {
   e.tracker.update(&e.marks,e.session.body().pos.to_array());
   if now%50==0{
    let c=e.session.applied;e.previous=[c.gas,c.brake,c.steer];
    let x=e.observation(&e.raw(),&e.tracker)?;let target=record.run.at(now);
    for v in x{write!(out,"{v:.17},")?;}writeln!(out,"{},{},{}",target.gas,target.brake,target.steer)?;rows+=1;
   }
  }
  ensure!(record.step(&mut e.session,tick),"unsupported respawn");
  finish=e.session.race().and_then(|r|r.finish);if finish.is_some(){break;}
 }
 ensure!(finish==Some(record.time_ms as u32),"demonstration did not reproduce original finish");
 Ok(serde_json::json!({"rows":rows,"finishMs":finish,"replayCommandsInInferenceObservations":false,
  "mapUidInObservations":false,"demonstrationControlsUsedOnlyAsTargets":true}))
}
