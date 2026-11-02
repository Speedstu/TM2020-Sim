use anyhow::{Result,ensure};
use gearbox_engine::Controls;
use std::{path::Path,time::Instant};
fn main()->Result<()>{
    let args:Vec<_>=std::env::args().collect();ensure!(args.len()==3,"fast-probe MAP PACKS");
    let start=Instant::now();
    let mut session=gearbox_world::open_file(Path::new(&args[1]),Path::new(&args[2]),
        gearbox_world::OpenOptions{t0:-1500,seed:Some(2026),car:None})?;
    for _ in 0..150{session.step(Controls::default());}
    let cold=start.elapsed().as_secs_f64();let initial=session.save();
    let start=Instant::now();let mut ticks=0;let mut finishes=0;
    for _ in 0..10{
        session.restore(&initial);
        for _ in 0..3000{
            session.step(Controls{gas:1.,brake:0.,steer:0.});ticks+=1;
            if session.race().is_some_and(|r|r.finish.is_some()){finishes+=1;break;}
        }
    }
    let elapsed=start.elapsed().as_secs_f64();
    println!("{}",serde_json::json!({"coldSeconds":cold,"ticks":ticks,"stepSeconds":elapsed,
        "collisionScales":session.config.models.iter().flatten().map(|m|m.assets.tuning.collision_scale).collect::<Vec<_>>(),
        "physicsTicksPerSecond":ticks as f64/elapsed,"fullThrottleFinishes":finishes,
        "completeExactPhysicsQualified":false}));Ok(())
}
