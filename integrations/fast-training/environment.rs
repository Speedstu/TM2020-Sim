//! GPL-3.0-or-later. In-process recovered physics, causal route observations.
//! Route inputs contain geometry only; no recorded steering, speed or timing
//! is used in observations, controls, rewards or the geometric controller.
use anyhow::{Context, Result, ensure};
use gearbox_engine::{Controls,Savestate,Session,Vec3};
use gearbox_gbx::{Map,Replay,record::CLASS_VEHICLE_VIS};
use std::{cell::{Cell,RefCell},ffi::{CStr,CString,c_char,c_void},path::Path,sync::Arc};
pub const NX:usize=48;
#[repr(C)]
#[derive(Clone)]
pub struct Output {
    observation:[f64;NX],reward:f64,progress:f64,cross_track:f64,speed:f64,
    rigid_words:[u32;22],tick:u32,checkpoints:u32,terminated:u32,truncated:u32,
    advanced_ticks:u32,finish_ms:i32,controls:[f32;3],reserved:u32,
}
#[derive(Clone)]
struct Route { points:Vec<[f32;3]>, arc:Vec<f64> }
impl Route {
    fn load(path:&Path,uid:Option<&str>)->Result<Self>{
        let replay=Replay::parse(&std::fs::read(path)?)?;
        ensure!(replay.map_uid.as_deref()==uid,"route replay map UID differs");
        let ghost=replay.ghosts.iter().find(|g|g.race_time_ms.is_some()).context("no finished route ghost")?;
        let mut timed:Vec<_>=ghost.record_entities().filter(|e|e.class_id==CLASS_VEHICLE_VIS)
            .flat_map(|e|&e.samples).filter(|s|s.time_ms>=0 && s.time_ms<=ghost.race_time_ms.unwrap() as i32)
            .filter_map(|s|s.vehicle.as_ref().map(|v|(s.time_ms,v.position))).collect();
        timed.sort_by_key(|x|x.0);timed.dedup_by_key(|x|x.0);
        let mut points=Vec::new();let mut arc=Vec::new();let mut distance=0.0;
        for (_,point) in timed {
            ensure!(point.iter().all(|v|v.is_finite()),"nonfinite route point");
            if let Some(previous)=points.last(){
                let d=length(sub(point,*previous));if d<0.05{continue;}distance+=d;
            }
            points.push(point);arc.push(distance);
        }
        ensure!(points.len()>=20 && points.len()<=20000 && distance>50.0,"invalid route geometry");
        Ok(Self{points,arc})
    }
    fn locate(&self,pos:[f32;3],previous:usize)->(usize,f64,[f32;3],f64){
        let lo=previous.saturating_sub(8);let hi=(previous+12).min(self.points.len()-1);
        let mut best=(previous,self.arc[previous],self.points[previous],f64::INFINITY);
        for i in lo..hi{
            let a=self.points[i];let d=sub(self.points[i+1],a);let len2=dot(d,d);
            let f=if len2>0.0{(dot(sub(pos,a),d)/len2).clamp(0.0,1.0)}else{0.0};
            let point=std::array::from_fn(|k|a[k]+d[k]*f as f32);
            let distance=length(sub(pos,point));
            if distance<best.3 {best=(i,self.arc[i]+f*(self.arc[i+1]-self.arc[i]),point,distance);}
        }
        best
    }
    fn at(&self,s:f64)->[f32;3]{
        let end=*self.arc.last().unwrap();
        if s>end{
            let n=self.points.len();let a=self.points[n-1];let delta=sub(a,self.points[n-2]);
            let f=((s-end)/length(delta)) as f32;
            return std::array::from_fn(|k|a[k]+f*delta[k]);
        }
        let s=s.clamp(0.0,*self.arc.last().unwrap());
        let i=self.arc.partition_point(|v|*v<=s).saturating_sub(1).min(self.points.len()-2);
        let f=((s-self.arc[i])/(self.arc[i+1]-self.arc[i])).clamp(0.0,1.0) as f32;
        std::array::from_fn(|k|self.points[i][k]+f*(self.points[i+1][k]-self.points[i][k]))
    }
}
fn sub(a:[f32;3],b:[f32;3])->[f32;3]{std::array::from_fn(|k|a[k]-b[k])}
fn dot(a:[f32;3],b:[f32;3])->f64{(0..3).map(|k|f64::from(a[k])*f64::from(b[k])).sum()}
fn length(a:[f32;3])->f64{dot(a,a).sqrt()}
#[derive(Clone)]
struct Bank {
    saved:Savestate,tick:u32,index:usize,progress:f64,cross:f64,
    nearest:[f32;3],previous:[f32;3],
}
#[derive(Clone)]
struct Env {
    session:Session,initial:Savestate,route:Arc<Route>,horizon:u32,
    banks:Arc<Vec<Bank>>,
    tick:u32,index:usize,progress:f64,best:f64,cross:f64,nearest:[f32;3],
    previous:[f32;3],stale:u32,offroute:u32,done:bool,failed:bool,
    lookahead:f64,gain:f64,residual:f64,
    planner:bool,planned:Cell<Option<f64>>,
}
impl Env {
    fn open(map:&Path,packs:&Path,replay:&Path,horizon:u32)->Result<Self>{
        ensure!((1..=100000).contains(&horizon),"invalid horizon");
        let parsed=Map::parse(&std::fs::read(map)?)?;
        let route=Arc::new(Route::load(replay,parsed.uid.as_deref())?);
        let mut session=gearbox_world::open_file(map,packs,
            gearbox_world::OpenOptions{t0:-1500,seed:Some(2026),car:None})?;
        for _ in 0..150{session.step(Controls::default());}
        ensure!(session.race_ms()==0,"missing initial race boundary");
        let initial=session.save();
        let mut env=Self{session,initial,route,horizon,banks:Arc::new(Vec::new()),tick:0,index:0,progress:0.,best:0.,cross:0.,nearest:[0.;3],
            previous:[0.;3],stale:0,offroute:0,done:false,failed:false,lookahead:35.,gain:5.,residual:0.35,
            planner:false,planned:Cell::new(None)};
        env.update_route();
        let mut banks=vec![Bank{saved:env.initial.clone(),tick:0,index:env.index,progress:env.progress,cross:env.cross,
            nearest:env.nearest,previous:[0.;3]}];
        // Expert commands are used only to construct complete reset snapshots.
        // No command target or future expert state enters policy observations.
        let recording=Replay::parse(&std::fs::read(replay)?)?;
        let record=gearbox_run::Record::from_replay(&recording)?;
        ensure!(record.run.t0<=0 && record.respawns.is_empty(),"reset bank requires a complete non-respawning replay");
        let packs=gearbox_packs::packs::PackSet::open(packs)?;
        let mut demo=record.open(&parsed,&packs)?;let mut index=0;let mut finish=None;
        for t in 0..10000{
            let now=demo.race_ms();
            if now>=0{
                let (i,s,nearest,cross)=env.route.locate(demo.body().pos.to_array(),index);index=i;
                if now>0 && now%1000==0 && now<record.time_ms-500{
                    let c=demo.applied;
                    banks.push(Bank{saved:demo.save(),tick:now as u32/10,index:i,progress:s,cross,nearest,
                        previous:[c.gas,c.brake,c.steer]});
                }
            }
            ensure!(record.step(&mut demo,t),"unsupported reset bank respawn");
            finish=demo.race().and_then(|r|r.finish);if finish.is_some(){break;}
        }
        ensure!(finish==Some(record.time_ms as u32),"reset bank did not reproduce reference finish");
        env.banks=Arc::new(banks);Ok(env)
    }
    fn reset(&mut self,seed:u32)->Result<Output>{
        self.reset_bank(seed,0)
    }
    fn reset_bank(&mut self,seed:u32,bank:usize)->Result<Output>{
        let b=self.banks.get(bank).context("unknown complete reset snapshot")?;
        ensure!(b.tick<self.horizon,"reset snapshot is outside the episode horizon");
        self.session.restore(&b.saved);self.session.seed=Some(seed);
        self.tick=b.tick;self.index=b.index;self.progress=b.progress;self.best=b.progress;
        self.cross=b.cross;self.nearest=b.nearest;self.previous=b.previous;
        self.stale=0;self.offroute=0;self.done=false;self.failed=false;
        self.planned.set(None);
        self.output(0.,0)
    }
    fn update_route(&mut self){
        let (i,s,nearest,cross)=self.route.locate(self.session.body().pos.to_array(),self.index);
        self.index=i;self.progress=s;self.nearest=nearest;self.cross=cross;
    }
    fn baseline(&self)->f64{
        if self.planner {
            if let Some(steer)=self.planned.get(){return steer;}
            if self.done{return f64::from(self.previous[2]);}
            let mut best=(f64::INFINITY,0.);
            // In this pinned engine the only World writes during stepping are
            // shape scaling. If every selectable model has unit collision
            // scale, forecasts leave World unchanged. Keep one uniquely owned
            // copy and restore ALL mutable Session fields for each candidate.
            // Other models retain the full independent clone path.
            let reusable=self.session.config.models.iter().flatten()
                .all(|m|m.assets.tuning.collision_scale==1.);
            let mut future=self.session.clone();
            if reusable {Arc::make_mut(&mut future.world);}
            for i in 0..17 {
                let steer=(i as f64-8.)/8.;
                let quantized=(steer*127.).round() as f32/127.;
                if i>0 {
                    if reusable {
                        let owned=std::mem::replace(&mut future.world,Arc::clone(&self.session.world));
                        future=Session{world:owned,..self.session.clone()};
                    } else {future=self.session.clone();}
                }
                let mut index=self.index;
                let mut progress=self.progress;let mut score=0.;
                for tick in 0..60 {
                    future.step(Controls{gas:1.,brake:0.,steer:quantized});
                    let (j,s,nearest,cross)=self.route.locate(future.body().pos.to_array(),index);
                    index=j;progress=s;
                    if (tick+1)%10==0 {
                        let body=future.body();
                        let delta=body.rot.transpose_mul_vec(Vec3::from(self.route.at(progress+10.))-Vec3::from(nearest));
                        let velocity=body.rot.transpose_mul_vec(body.vel);
                        let norm=(f64::from(delta.x).powi(2)+f64::from(delta.z).powi(2)).sqrt().max(0.1);
                        let perpendicular=(f64::from(velocity.x)*f64::from(delta.z)-f64::from(velocity.z)*f64::from(delta.x))/norm;
                        score+=cross.powi(2)+0.01*perpendicular.powi(2);
                    }
                    if future.race().is_some_and(|r|r.finish.is_some()){score-=10000.;break;}
                }
                score-=10.*(progress-self.progress);
                score+=0.01*(steer-f64::from(self.previous[2])).powi(2);
                if score<best.0{best=(score,steer);}
            }
            self.planned.set(Some(best.1));return best.1;
        }
        let body=self.session.body();let speed=f64::from(body.vel.dot(body.vel)).sqrt();
        let look=(self.lookahead+speed*0.15).clamp(8.,100.);
        let delta=body.rot.transpose_mul_vec(Vec3::from(self.route.at(self.progress+look))-body.pos);
        let error=body.rot.transpose_mul_vec(Vec3::from(self.nearest)-body.pos);
        (-self.gain*f64::from(delta.x).atan2(f64::from(delta.z))-0.15*f64::from(error.x)).clamp(-1.,1.)
    }
    fn output(&self,reward:f64,advanced:u32)->Result<Output>{
        let body=self.session.body();let mut obs=[0.;NX];
        let vel=body.rot.transpose_mul_vec(body.vel).to_array();
        let ang=body.rot.transpose_mul_vec(body.ang_vel).to_array();
        let up=body.rot.transpose_mul_vec(Vec3::from([0.,1.,0.])).to_array();
        for k in 0..3{obs[k]=f64::from(vel[k])/100.;obs[3+k]=f64::from(ang[k])/10.;obs[6+k]=f64::from(up[k]);}
        for (i,distance) in [10.,25.,50.,100.].iter().enumerate(){
            let local=body.rot.transpose_mul_vec(Vec3::from(self.route.at(self.progress+distance))-body.pos).to_array();
            for k in 0..3{obs[9+3*i+k]=(f64::from(local[k])/50.).clamp(-4.,4.);}
        }
        let error=body.rot.transpose_mul_vec(Vec3::from(self.nearest)-body.pos).to_array();
        for k in 0..3{obs[21+k]=f64::from(error[k])/10.;obs[24+k]=f64::from(self.previous[k]);}
        let race=self.session.race().context("no race state")?;
        obs[27]=race.checkpoints.len() as f64/10.;obs[28]=f64::from(body.vel.dot(body.vel)).sqrt()/100.;
        obs[29]=self.progress/self.route.arc.last().unwrap();
        obs[30]=1.-self.tick as f64/self.horizon as f64;obs[31]=self.baseline();
        let car=self.session.vehicle();
        obs[32]=f64::from(car.steering);
        obs[33]=f64::from(car.wheels[0].steering_angle+car.wheels[1].steering_angle)/std::f64::consts::PI;
        for k in 0..4{
            obs[34+k]=f64::from(car.wheels[k].contact!=0);
            let slip=f64::from(car.wheels[k].slip);obs[38+k]=slip/(1.+slip.abs());
        }
        obs[42]=f64::from(car.rpm)/10000.;obs[43]=f64::from(car.gear)/6.;
        obs[44]=f64::from(car.turbo_active!=0);obs[45]=f64::from(car.body_contact!=0);
        obs[46]=f64::from(car.support_contact_count)/4.;obs[47]=f64::from(car.drift_direction)/2.;
        ensure!(obs.iter().all(|v|v.is_finite()) && reward.is_finite(),"nonfinite environment result");
        let raw=gearbox_trace::typed::state(&self.session).body.floats();
        Ok(Output{observation:obs,reward,progress:self.progress,cross_track:self.cross,speed:obs[28]*100.,
            rigid_words:raw.map(f32::to_bits),tick:self.tick,checkpoints:race.checkpoints.len() as u32,
            terminated:u32::from(race.finish.is_some()),truncated:u32::from(self.done && race.finish.is_none()),
            advanced_ticks:advanced,finish_ms:race.finish.map_or(-1,|t|t as i32),controls:self.previous,reserved:0})
    }
    fn step(&mut self,controls:[f32;3],repeat:u32)->Result<Output>{
        ensure!(!self.done && !self.failed,"reset required");
        ensure!((1..=100).contains(&repeat) && controls.iter().all(|v|v.is_finite()) &&
                (0.0..=1.0).contains(&controls[0]) && (0.0..=1.0).contains(&controls[1]) &&
                (-1.0..=1.0).contains(&controls[2]),"invalid action or repeat");
        self.failed=true; // A panic after partial advancement requires reset.
        self.planned.set(None);
        let before_cp=self.session.race().context("no race")?.checkpoints.len();let before_best=self.best;
        let mut advanced=0;
        for _ in 0..repeat.min(self.horizon-self.tick){
            self.session.step(Controls{gas:controls[0],brake:controls[1],steer:controls[2]});
            self.tick+=1;advanced+=1;self.update_route();
            if self.progress>self.best+0.01{self.best=self.progress;self.stale=0;}else{self.stale+=1;}
            self.offroute=if self.cross>30.0{self.offroute+1}else{0};
            if self.session.race().is_some_and(|r|r.finish.is_some()) ||
                self.tick>=self.horizon || self.offroute>=75 || self.stale>=250{
                self.done=true;break;
            }
        }
        self.previous=controls;
        let race=self.session.race().context("no race")?;
        let progress=(self.best-before_best).clamp(0.,30.);
        let cp=race.checkpoints.len().saturating_sub(before_cp);
        let finish=if race.finish.is_some(){100.0}else{0.0};
        let failure=if self.done && race.finish.is_none(){-20.0}else{0.0};
        let reward=0.05*progress+10.0*cp as f64+finish+failure-
            0.01*advanced as f64-0.000005*self.cross.min(30.).powi(2)*advanced as f64;
        let result=self.output(reward,advanced);
        if result.is_ok(){self.failed=false;}
        result
    }
}
thread_local!{static ERROR:RefCell<CString>=RefCell::new(CString::new("").unwrap());}
fn error(e:impl std::fmt::Display){ERROR.with(|s|*s.borrow_mut()=CString::new(e.to_string().replace('\0'," ")).unwrap());}
fn attempt<T>(f:impl FnOnce()->Result<T>)->Option<T>{
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)){
        Ok(Ok(v))=>Some(v),Ok(Err(e))=>{error(format!("{e:#}"));None},
        Err(_)=>{error("unsupported physics path panicked; no transition accepted");None},
    }
}
unsafe fn env<'a>(p:*mut c_void)->Result<&'a mut Env>{ensure!(!p.is_null(),"null environment");Ok(unsafe{&mut *p.cast::<Env>()})}
unsafe fn path<'a>(p:*const c_char)->Result<&'a Path>{ensure!(!p.is_null(),"null path");Ok(Path::new(unsafe{CStr::from_ptr(p)}.to_str()?))}
#[unsafe(no_mangle)]pub extern "C" fn tmfast_version()->u32{4}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_bank_size(p:*mut c_void)->u32{
    attempt(||Ok(unsafe{env(p)?}.banks.len() as u32)).unwrap_or(0)
}
#[unsafe(no_mangle)]pub extern "C" fn tmfast_last_error()->*const c_char{ERROR.with(|s|s.borrow().as_ptr())}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_open(m:*const c_char,p:*const c_char,r:*const c_char,h:u32)->*mut c_void{
    attempt(||unsafe{Env::open(path(m)?,path(p)?,path(r)?,h)}).map_or(std::ptr::null_mut(),|v|Box::into_raw(Box::new(v)).cast())
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_clone(p:*mut c_void)->*mut c_void{
    attempt(||Ok(unsafe{env(p)?}.clone())).map_or(std::ptr::null_mut(),|v|Box::into_raw(Box::new(v)).cast())
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_configure(p:*mut c_void,l:f64,g:f64,r:f64)->i32{
    attempt(||{ensure!((5.0..=100.0).contains(&l)&&(0.1..=20.0).contains(&g)&&(0.0..=2.0).contains(&r),"bad controller parameters");
        let e=unsafe{env(p)?};e.lookahead=l;e.gain=g;e.residual=r;e.planned.set(None);Ok(())}).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_configure_planner(p:*mut c_void,enabled:u32)->i32{
    attempt(||{ensure!(enabled<=1,"invalid planner flag");let e=unsafe{env(p)?};e.planner=enabled!=0;e.planned.set(None);Ok(())}).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_reset(p:*mut c_void,seed:u32,out:*mut Output)->i32{
    attempt(||{ensure!(!out.is_null(),"null output");unsafe{*out=env(p)?.reset(seed)?};Ok(())}).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_reset_bank(p:*mut c_void,seed:u32,bank:u32,out:*mut Output)->i32{
    attempt(||{ensure!(!out.is_null(),"null output");unsafe{*out=env(p)?.reset_bank(seed,bank as usize)?};Ok(())}).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_step(p:*mut c_void,action:*const f64,repeat:u32,out:*mut Output)->i32{
    attempt(||{ensure!(!action.is_null()&&!out.is_null(),"null action/output");let e=unsafe{env(p)?};
        let a=unsafe{std::slice::from_raw_parts(action,3)};ensure!(a.iter().all(|v|v.is_finite()&&v.abs()<=1.),"invalid policy action");
        let steer=((e.baseline()+e.residual*a[2]).clamp(-1.,1.)*127.).round() as i32;
        let controls=[f32::from(a[0]>=0.0),f32::from(a[1]>=0.0),steer as f32/127.0];
        match e.step(controls,repeat){Ok(v)=>{unsafe{*out=v};Ok(())},Err(x)=>Err(x)}
    }).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_step_controls(p:*mut c_void,a:*const f32,repeat:u32,out:*mut Output)->i32{
    attempt(||{ensure!(!a.is_null()&&!out.is_null(),"null controls/output");let e=unsafe{env(p)?};let a=unsafe{std::slice::from_raw_parts(a,3)};
        match e.step([a[0],a[1],a[2]],repeat){Ok(v)=>{unsafe{*out=v};Ok(())},Err(x)=>Err(x)}
    }).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmfast_close(p:*mut c_void){if !p.is_null(){drop(unsafe{Box::from_raw(p.cast::<Env>())});}}

/// Offline-only supervised data. The replay's full input state is handled by
/// the upstream Record driver, including countdown, RNG and action-key flags.
pub fn export_demonstration(map:&Path,packs:&Path,route:&Path,replay:&Path,output:&Path,
                            lookahead:f64,gain:f64,residual:f64)->Result<serde_json::Value>{
    use std::io::Write;
    let parsed=Map::parse(&std::fs::read(map)?)?;
    let recording=Replay::parse(&std::fs::read(replay)?)?;
    ensure!(recording.map_uid==parsed.uid,"demonstration map UID differs");
    let record=gearbox_run::Record::from_replay(&recording)?;
    ensure!(record.run.t0<=0 && record.respawns.is_empty(),"partial or respawning demonstration unsupported");
    let set=gearbox_packs::packs::PackSet::open(packs)?;
    let mut env=Env::open(map,packs,route,4000)?;
    env.session=record.open(&parsed,&set)?;
    env.lookahead=lookahead;env.gain=gain;env.residual=residual;
    let mut file=std::fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    for i in 0..NX{write!(file,"observation_{i},")?;}writeln!(file,"steer,baseline,race_ms")?;
    let mut rows=0;let mut outside=0;let mut finish=None;
    for tick in 0..10000{
        let now=env.session.race_ms();
        if now>=0 && now%50==0{
            env.tick=now as u32/10;env.update_route();
            let c=env.session.applied;env.previous=[c.gas,c.brake,c.steer];
            let x=env.output(0.,0)?.observation;
            let target=record.run.at(now).steer;
            for v in x{write!(file,"{v:.17},")?;}
            writeln!(file,"{target:.17},{:.17},{now}",env.baseline())?;
            rows+=1;outside+=usize::from((f64::from(target)-env.baseline()).abs()>residual);
        }
        ensure!(record.step(&mut env.session,tick),"unsupported demonstration respawn");
        finish=env.session.race().and_then(|r|r.finish);
        if finish.is_some(){break;}
    }
    ensure!(finish==Some(record.time_ms as u32),"demonstration finish differs from original replay");
    Ok(serde_json::json!({"replay":replay,"rows":rows,"finishMs":finish,"seed":record.run.seed,
        "targetsOutsideResidual":outside,"recordedControlsUsedAsSupervisedTargetsOnly":true,
        "lookahead":lookahead,"gain":gain,"residual":residual,"horizon":4000}))
}
