use anyhow::{Result,ensure};
fn main()->Result<()>{
 let a:Vec<_>=std::env::args().collect();ensure!(a.len()==3,"metadata map|replay|inputs|analysis FILE");
 let bytes=std::fs::read(&a[2])?;
 let value=match a[1].as_str(){
  "map"=>{let m=gearbox_gbx::Map::parse(&bytes)?;serde_json::json!({"mapUid":m.uid,"name":m.name,"playerModel":m.player_model,"collection":m.collection,"lapRace":m.lap_race,"laps":m.laps})},
  "replay"=>{let r=gearbox_gbx::Replay::parse(&bytes)?;ensure!(r.ghosts.len()==1,"one ghost required");let g=&r.ghosts[0];
   serde_json::json!({"mapUid":r.map_uid,"validationSeed":g.validation_seed.map(|s|s as u32),"respawns":g.respawns,"declaredMs":g.race_time_ms})},
  "inputs"=>{let r=gearbox_gbx::Replay::parse(&bytes)?;
   let mut ghosts=Vec::new();
   for g in &r.ghosts {
    let decoded=g.inputs.iter().map(|group|group.decode()).collect::<Result<Vec<_>>>()?;
    ghosts.push(serde_json::json!({"declaredMs":g.race_time_ms,"validationSeed":g.validation_seed.map(|s|s as u32),
      "respawns":g.respawns,"groups":decoded}));
   }
   serde_json::json!({"schema":"tm2020_original_replay_inputs_v1","mapUid":r.map_uid,"ghosts":ghosts})},
  "analysis"=>{let r=gearbox_gbx::Replay::parse(&bytes)?;let mut ghosts=Vec::new();
   for g in &r.ghosts {
    let decoded=g.inputs.iter().map(|group|group.decode()).collect::<Result<Vec<_>>>()?;
    let mut samples=Vec::new();
    for entity in g.record_entities().filter(|e|e.class_id==gearbox_gbx::record::CLASS_VEHICLE_VIS){
     for s in &entity.samples{if let Some(v)=&s.vehicle{samples.push(serde_json::json!({"ms":s.time_ms,"vehicle":v}));}}
    }
    ghosts.push(serde_json::json!({"declaredMs":g.race_time_ms,"validationSeed":g.validation_seed.map(|s|s as u32),
      "respawns":g.respawns,"checkpointMs":g.checkpoints_ms,"groups":decoded,"visualSamples":samples,
      "visualControlsAreQuantizedRenderingData":true}));
   }
   serde_json::json!({"schema":"tm2020_original_replay_analysis_v1","mapUid":r.map_uid,"ghosts":ghosts})},
  "decode-owned"=>{let v:serde_json::Value=serde_json::from_slice(&bytes)?;
   ensure!(v["kind"]=="owned-input-capture","only explicit owned input-capture envelopes are supported");
   let data=v["data"].as_array().ok_or_else(||anyhow::anyhow!("missing bytes"))?.iter()
    .map(|x|x.as_u64().filter(|&n|n<256).map(|n|n as u8).ok_or_else(||anyhow::anyhow!("invalid byte"))).collect::<Result<Vec<_>>>()?;
   let group=gearbox_gbx::inputs::PlayerInputs{version:12,start_offset_ms:Some(0),ticks:v["ticks"].as_u64().unwrap_or(0) as usize,data};
   ensure!(group.ticks>0&&group.ticks<100000,"invalid owned tick count");
   serde_json::json!({"ownedOnly":true,"clientReplay":false,"decoded":group.decode()?})},
  _=>anyhow::bail!("unsupported mode")};
 println!("{}",serde_json::to_string(&value)?);Ok(())
}
