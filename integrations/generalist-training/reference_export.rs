//! Exact pre-tick rigid state plus effective pedals/steering, at 100 Hz.
//! Metadata proves reference reproduction; it is separate from controller qualification.
use anyhow::{Result, ensure};
use std::{path::Path, io::{BufWriter, Write}};
fn main()->Result<()> {
    let a:Vec<_>=std::env::args().collect();
    ensure!(a.len()==5,"reference-export MAP PACKS GHOST OUTPUT.f32");
    let map=gearbox_gbx::Map::parse(&std::fs::read(&a[1])?)?;
    let replay=gearbox_gbx::Replay::parse(&std::fs::read(&a[3])?)?;
    ensure!(map.uid==replay.map_uid,"Reference UID mismatch");
    let record=gearbox_run::Record::from_replay(&replay)?;
    ensure!(record.respawns.is_empty(),"Respawning reference unsupported");
    let packs=gearbox_packs::packs::PackSet::open(Path::new(&a[2]))?;
    let mut session=record.open(&map,&packs)?;
    let mut rows=Vec::new();let mut finish=None;let mut checkpoints=0;
    for tick in 0..30000 {
        let now=session.race_ms();
        let state=if now>=0 {Some(gearbox_trace::typed::state(&session).body.floats())}else{None};
        ensure!(record.step(&mut session,tick),"Reference respawn unsupported");
        if let Some(state)=state {
            ensure!(now==rows.len() as i32*10,"Reference missing a pre-tick state");
            let mut row=[0f32;25];row[..22].copy_from_slice(&state);
            row[22]=session.applied.gas;row[23]=session.applied.brake;row[24]=session.applied.steer;
            rows.push(row);
        }
        if let Some(r)=session.race() {finish=r.finish;checkpoints=r.checkpoints.len();}
        if finish.is_some(){break;}
    }
    ensure!(finish==Some(record.time_ms as u32),"Reference finish {:?} differs from declared {}",finish,record.time_ms);
    let mut f=BufWriter::new(std::fs::OpenOptions::new().write(true).create_new(true).open(&a[4])?);
    for row in &rows {for v in row {f.write_all(&v.to_le_bytes())?;}}f.flush()?;
    println!("{}",serde_json::json!({"mapUid":map.uid,"rows":rows.len(),"seed":record.run.seed,
        "finishMs":finish,"declaredMs":record.time_ms,"checkpoints":checkpoints,
        "format":"little-endian f32 [rows,25]; pre-tick rigid22,effective gas/brake/steer",
        "referenceReproduced":true,"controllerQualified":false}));
    Ok(())
}
