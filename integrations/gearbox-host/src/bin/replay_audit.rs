// SPDX-License-Identifier: GPL-3.0-or-later
//! External-engine comparison to recorded game trajectories, never synthetic goldens.
use anyhow::{Context, Result, ensure};
use gearbox_gbx::{Map, Replay, record::CLASS_VEHICLE_VIS};
use gearbox_packs::packs::PackSet;
use gearbox_run::Record;
use serde_json::{Value,json};
use std::{collections::BTreeMap,fs,io::Write,path::{Path,PathBuf}};

fn audit(path:&Path,packs:&PackSet,assets:&mut Option<String>,dataset:Option<&Path>)->Result<Value>{
    let replay=Replay::parse(&fs::read(path)?)?;
    let ghost=replay.ghosts.iter().find(|g|g.race_time_ms.is_some()&&!g.inputs.is_empty()).context("no finished input ghost")?;
    let decoded=ghost.inputs.first().context("no ghost inputs")?.decode()?;
    ensure!(decoded.start_offset_ms<=0,"incomplete replay input history: starts at {} ms; cold replay comparison denied",decoded.start_offset_ms);
    let map=Map::parse(replay.map_gbx.as_deref().context("embedded map required")?)?;
    let record=Record::from_ghost(ghost)?;
    let samples:Vec<_>=ghost.record_entities().filter(|e|e.class_id==CLASS_VEHICLE_VIS)
        .flat_map(|e|&e.samples).filter(|s|s.time_ms>=0&&s.time_ms<=record.time_ms&&s.vehicle.is_some()).collect();
    ensure!(!samples.is_empty(),"no vehicle samples");
    let mut session=record.open(&map,packs).with_context(||format!("world initialization: map car {:?}, recorded ghost car {:?}",map.player_model,ghost.player_model))?;
    let course=gearbox_net::Course::race(&session)?;
    let mut dataset=dataset.map(|path|fs::OpenOptions::new().write(true).create_new(true).open(path)).transpose()?;
    if let Some(out)=&mut dataset{
        for i in 0..gearbox_net::observe::LEN{write!(out,"observation_{i},")?;}
        writeln!(out,"gas,brake,steer,race_ms")?;
    }
    if assets.is_none(){
        let mut dump=format!("Pinned Gearbox decoding of installed local assets. Not independently qualified field semantics.\nGravity: {:?}\n",session.dyna.gravity);
        for (index,model) in session.config.models.iter().enumerate(){
            if let Some(model)=model{dump.push_str(&format!("\nMODEL {index}\nBODY\n{:#?}\nASSETS\n{:#?}\nSPAWN\n{:#?}\n",model.body,model.assets,model.spawn));}
        }
        *assets=Some(dump);
    }
    if !record.respawns.is_empty(){session.track_respawns();}
    let ticks=((record.time_ms-record.run.t0).max(0) as usize).div_ceil(10)+100;
    ensure!(ticks<=100_000,"replay duration bound");
    let mut rows=Vec::new();let mut next=0;let mut finish=None;let mut history=BTreeMap::new();
    for tick in 0..ticks{
        let before_ms=session.race_ms();
        let observation=if dataset.is_some()&&before_ms>=0&&before_ms%50==0 {Some(gearbox_net::observe(&session,&course))}else{None};
        ensure!(record.step(&mut session,tick),"respawn without spawn");
        let now=session.race_ms();
        history.insert(now,session.vehicle().pos.to_array());
        if let (Some(out),Some(observation))=(&mut dataset,observation){
            for value in observation{write!(out,"{value},")?;}
            writeln!(out,"{},{},{},{}",session.applied.gas,session.applied.brake,session.applied.steer,before_ms)?;
        }
        // No time-shift fitting or nearest-trajectory matching: compare equal timestamps only.
        while next<samples.len()&&samples[next].time_ms<=now{
            let sample=samples[next];next+=1;
            if sample.time_ms!=now{continue;}
            let expected=sample.vehicle.as_ref().unwrap().position;
            let actual=session.vehicle().pos.to_array();
            let squared:f64=(0..3).map(|i|(f64::from(actual[i])-f64::from(expected[i])).powi(2)).sum();
            rows.push(json!({"raceMs":now,"recordedPosition":expected,"simulatedPosition":actual,"distanceMetres":squared.sqrt()}));
        }
        finish=session.race().and_then(|r|r.finish);
        if finish.is_some(){break;}
    }
    ensure!(!rows.is_empty(),"no same-time position comparisons");
    let errors:Vec<f64>=rows.iter().map(|r|r["distanceMetres"].as_f64().unwrap()).collect();
    let max=errors.iter().copied().fold(0.0,f64::max);
    let rmse=(errors.iter().map(|e|e*e).sum::<f64>()/errors.len() as f64).sqrt();
    let first_over=rows.iter().find(|r|r["distanceMetres"].as_f64().unwrap()>0.01).cloned();
    // Session::step increments race_ms after tick(). Keep this fixed +10 ms
    // hypothesis separate from the unadjusted comparison; never fit a best lag.
    let shifted:Vec<Value>=samples.iter().filter_map(|s|{
        let actual=history.get(&(s.time_ms+10))?;let expected=s.vehicle.as_ref()?.position;
        let squared:f64=(0..3).map(|i|(f64::from(actual[i])-f64::from(expected[i])).powi(2)).sum();
        Some(json!({"recordedRaceMs":s.time_ms,"simulatorPostStepRaceMs":s.time_ms+10,
            "distanceMetres":squared.sqrt()}))
    }).collect();
    let shifted_errors:Vec<f64>=shifted.iter().map(|v|v["distanceMetres"].as_f64().unwrap()).collect();
    let simulated_cps=session.race().map(|r|r.checkpoints.clone());
    Ok(json!({"path":path,"ok":true,"mapUid":replay.map_uid,"recordedExe":record.build,
        "recordedFinishMs":record.time_ms,"simulatedFinishMs":finish,
        "finishDeltaMs":finish.map(|f|i64::from(f)-i64::from(record.time_ms)),
        "recordedCheckpointsMs":record.checkpoints_ms,"simulatedCheckpointsMs":simulated_cps,
        "replaySeed":record.run.seed,"inputStartMs":record.run.t0,"respawns":record.respawns.len(),
        "sameTimestampComparisons":rows.len(),"positionRmseMetres":rmse,"positionMaximumMetres":max,
        "firstPositionErrorAboveOneCentimetre":first_over,"comparisons":rows,
        "fixedPostStepTimestampHypothesis":{"offsetMs":10,"offsetFitted":false,"comparisons":shifted,
            "positionRmseMetres":(shifted_errors.iter().map(|e|e*e).sum::<f64>()/shifted_errors.len().max(1) as f64).sqrt(),
            "positionMaximumMetres":shifted_errors.iter().copied().fold(0.0,f64::max),
            "timestampSemanticsIndependentlyQualified":false},
        "timestampsFitted":false,"recordedPositionsAreVisualQuantizedSamples":true,
        "bitExactPhysicsStateOracle":false,"completeExactPhysicsQualified":false}))
}

fn main()->Result<()>{
    let mut args:Vec<PathBuf>=std::env::args_os().skip(1).map(PathBuf::from).collect();
    let datasets=args.last().is_some_and(|v|v==Path::new("--dataset"));if datasets{args.pop();}
    ensure!(args.len()>=3,"replay_audit PACKS OUTPUT_DIR REPLAY... [--dataset]");
    ensure!(!args[1].exists(),"output already exists");fs::create_dir_all(&args[1])?;
    let packs=PackSet::open(&args[0])?;let mut rows=Vec::new();let mut assets=None;
    for path in &args[2..]{
        let csv=args[1].join(format!("{}.observations.csv",path.file_name().unwrap().to_string_lossy()));
        let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||audit(path,&packs,&mut assets,if datasets{Some(&csv)}else{None})));
        let row=match result{
            Ok(Ok(row))=>row,Ok(Err(error))=>json!({"path":path,"ok":false,"error":format!("{error:#}")}),
            Err(_)=>json!({"path":path,"ok":false,"error":"unsupported engine path panicked"})};
        println!("REPLAY_COMPARE {} ok={} finish_delta={} position_rmse={}",path.display(),row["ok"],row["finishDeltaMs"],row["positionRmseMetres"]);
        rows.push(row);
    }
    if let Some(dump)=assets{fs::write(args[1].join("installed-vehicle-assets.private.txt"),dump)?;}
    let report=json!({"schema":"tm2020_external_engine_game_replay_comparison_v1",
        "upstreamRevision":"e0583ee55168e950a65a645778e591bd26b6a0f2","replays":rows,
        "originalGameRecordedVisualTrajectoriesCompared":true,"sourceGameProcessAccessed":false,
        "openplanetUsed":false,"completeExactSimulatorQualified":false});
    let mut file=fs::OpenOptions::new().write(true).create_new(true).open(args[1].join("report.json"))?;
    file.write_all(serde_json::to_string_pretty(&report)?.as_bytes())?;Ok(())
}
