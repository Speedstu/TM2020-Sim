// SPDX-License-Identifier: GPL-3.0-or-later
// Finite-episode gamma=1 objective. Potential shaping cancels at termination.
#[derive(Clone,Copy)]
pub enum Outcome { Running, Finish, Failure{remaining_seconds:f64} }
pub fn reward(before:f64,after:f64,elapsed_seconds:f64,outcome:Outcome)->f64{
    let (bonus,potential)=match outcome{
        Outcome::Running=>(0.,after),Outcome::Finish=>(100.,0.),Outcome::Failure{remaining_seconds}=>(-100.-remaining_seconds.max(0.),0.)};
    bonus-elapsed_seconds+potential-before
}
// Training-only recovery objective: grade DNF progress while preserving the
// exact 100-time objective for successful full races. Early failure keeps the
// full horizon cost; the bounded route potential never makes failure a win.
pub fn recovery_reward(before:f64,after:f64,elapsed_seconds:f64,outcome:Outcome,end_potential:f64)->f64{
    reward(before,after,elapsed_seconds,outcome)+if matches!(outcome,Outcome::Failure{..}){end_potential}else{0.}
}
#[cfg(test)]
mod tests{
 use super::*;
 #[test]fn faster_finish_has_exact_time_advantage(){
  let a=reward(-3.,0.,27.,Outcome::Finish);let b=reward(-3.,0.,22.,Outcome::Finish);
  assert_eq!(b-a,5.);
 }
 #[test]fn arbitrary_checkpoint_and_distance_shaping_cancels(){
  let values=[-3.,-4.,8.,6.,15.,10.];let mut total=0.;
  for i in 0..values.len()-1{total+=reward(values[i],values[i+1],1.,Outcome::Running);}
  total+=reward(*values.last().unwrap(),0.,1.,Outcome::Finish);
  assert!((total-(100.-6.-values[0])).abs()<1e-12);
 }
 #[test]fn going_back_and_forward_never_earns_extra_progress(){
  let looped=reward(1.,9.,1.,Outcome::Running)+reward(9.,1.,1.,Outcome::Running);
  assert_eq!(looped,-2.);
 }
 #[test]fn failing_early_does_not_reduce_the_episode_cost(){
  let early=reward(-3.,0.,4.,Outcome::Failure{remaining_seconds:36.});
  let late=reward(-3.,0.,32.,Outcome::Failure{remaining_seconds:8.});assert_eq!(early,late);
 }
 #[test]fn failure_is_worse_than_any_finish_before_the_horizon(){
  let worst_finish=reward(-6.,0.,40.,Outcome::Finish);
  let quickest_failure=reward(-6.,0.,0.,Outcome::Failure{remaining_seconds:40.});assert!(worst_finish>quickest_failure);
 }
 #[test]fn recovery_grades_failures_without_rewarding_early_abort(){
  let at=|seconds,progress|recovery_reward(0.,0.,seconds,Outcome::Failure{remaining_seconds:40.-seconds},progress);
  assert_eq!(at(5.,25.),at(35.,25.));assert_eq!(at(35.,80.)-at(35.,25.),55.);
  assert!(at(35.,100.)<reward(0.,0.,40.,Outcome::Finish));
 }
 #[test]fn successful_recovery_race_still_optimizes_only_time(){
  let total=recovery_reward(0.,38.,8.,Outcome::Running,38.)+
      recovery_reward(38.,72.,8.,Outcome::Running,72.)+
      recovery_reward(72.,0.,5.,Outcome::Finish,100.);
  assert_eq!(total,79.);
 }
 #[test]fn recovery_bank_return_subtracts_initial_potential(){
  let total=recovery_reward(80.,94.,2.,Outcome::Running,94.)+
      recovery_reward(94.,0.,1.,Outcome::Finish,100.);
  assert_eq!(total,17.);
 }
}
