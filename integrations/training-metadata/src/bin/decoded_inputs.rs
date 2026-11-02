use anyhow::{Result,ensure};
fn main()->Result<()>{
 let a:Vec<_>=std::env::args().collect();ensure!(a.len()==2,"decoded_inputs REPLAY_OR_GHOST");
 let replay=gearbox_gbx::Replay::parse(&std::fs::read(&a[1])?)?;
 ensure!(replay.ghosts.len()==1,"one ghost required");let ghost=&replay.ghosts[0];
 let decoded=ghost.inputs.first().ok_or_else(||anyhow::anyhow!("ghost has no inputs"))?.decode()?;
 println!("{}",serde_json::to_string(&serde_json::json!({"mapUid":replay.map_uid,
  "seed":ghost.validation_seed.map(|s|s as u32),"timeMs":ghost.race_time_ms,"inputs":decoded}))?);Ok(())
}
