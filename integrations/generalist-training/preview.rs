// Explicit extra perception ABI. The legacy 48-value Output layout is intact.
use super::*;
const PREVIEW_NX:usize=72;
impl Env {
 fn preview(&self,raw:&[f32;24],tracker:&Tracker)->Result<[f64;PREVIEW_NX]>{
  ensure!(raw.iter().all(|v|v.is_finite()&&v.abs()<100000.),"invalid preview telemetry");
  let mut x=[0.;PREVIEW_NX];x[..48].copy_from_slice(&self.observation(raw[..21].try_into().unwrap(),tracker)?);
  let rot=Mat3::from_array(raw[3..12].try_into().unwrap());let pos=Vec3::from([raw[0],raw[1],raw[2]]);
  let omega=rot.transpose_mul_vec(Vec3::from([raw[21],raw[22],raw[23]]));
  for k in 0..3{x[48+k]=(f64::from(omega[k])/10.).clamp(-2.,2.);}
  // Ordered future triggers, not an expert line. Branches use the same nearest
  // admissible-checkpoint heuristic as the existing tracker, not hidden intent.
  let mut future=tracker.clone();let mut from=pos;
  for i in 0..4 {
   if let Some(mark)=future.goal(&self.marks,from){
    let center=mark.center();future.visited.push(mark.id);from=center;
    if i>0 {let local=rot.transpose_mul_vec(center-pos);
     for k in 0..3{x[51+(i-1)*3+k]=(f64::from(local[k])/200.).clamp(-4.,4.);}}
   }
  }
  // Long-range ground geometry, with three lateral probes at each distance.
  // Material/contact flags are not guessed. This is coarse anticipation,
  // not a solved road graph or a claim of arbitrary-map navigation.
  let mut k=60;
  for distance in [48.,96.,144.,224.] {for side in [-12.,0.,12.] {
   x[k]=self.session.pick_static(pos+rot*Vec3::new(side,24.,distance),rot*Vec3::new(0.,-96.,0.))
    .map_or(1.,|hit|f64::from(hit.fraction).clamp(0.,1.));k+=1;
  }}
  Ok(x)
 }
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmgen_preview_current(p:*mut c_void,o:*mut f64)->i32{
 attempt(||{ensure!(!o.is_null(),"null preview output");let e=unsafe{env(p)?};
  let mut raw=[0.;24];raw[..21].copy_from_slice(&e.raw());
  raw[21..].copy_from_slice(&e.session.body().ang_vel.to_array());
  let x=e.preview(&raw,&e.tracker)?;unsafe{std::ptr::copy_nonoverlapping(x.as_ptr(),o,PREVIEW_NX)};Ok(())
 }).map_or(-1,|_|0)
}
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmgen_observe72(p:*mut c_void,r:*const f32,reset:u32,o:*mut f64)->i32{
 attempt(||{ensure!(!r.is_null()&&!o.is_null()&&reset<=1,"invalid preview arguments");
  let e=unsafe{env(p)?};let raw:&[f32;24]=unsafe{std::slice::from_raw_parts(r,24)}.try_into().unwrap();
  let mut tracker=if reset!=0{Tracker::default()}else{e.tracker.clone()};
  let _=e.preview(raw,&tracker)?;tracker.update(&e.marks,[raw[0],raw[1],raw[2]]);
  let x=e.preview(raw,&tracker)?;unsafe{std::ptr::copy_nonoverlapping(x.as_ptr(),o,PREVIEW_NX)};e.tracker=tracker;Ok(())
 }).map_or(-1,|_|0)
}
// Checkpoints are owned Env clones from this exact shared immutable world.
// Restore all physical/session state; never teleport only the body.
#[unsafe(no_mangle)]pub unsafe extern "C" fn tmgen_restore_checkpoint(p:*mut c_void,s:*mut c_void,seed:u32,o:*mut Output)->i32{
 attempt(||{ensure!(p!=s&&!o.is_null(),"invalid checkpoint restore");
  let source=unsafe{env(s)?};let target=unsafe{env(p)?};
  ensure!(Arc::ptr_eq(&source.marks,&target.marks)&&source.horizon==target.horizon,"checkpoint belongs to another world");
  ensure!(!source.done&&!source.failed,"checkpoint is terminal or failed");
  target.session.restore(&source.session.save());target.session.seed=Some(seed);
  target.tracker=source.tracker.clone();target.tick=source.tick;target.previous=source.previous;
  target.done=false;target.failed=false;target.travel=source.travel;target.stuck=source.stuck;
  target.route_index=source.route_index;target.route_best=source.route_best;target.route_cross_squared=source.route_cross_squared;
  unsafe{*o=target.output(0.,0)?};Ok(())
 }).map_or(-1,|_|0)
}
