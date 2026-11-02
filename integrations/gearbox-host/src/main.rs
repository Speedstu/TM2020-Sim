// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded local IPC for a commit-pinned, asset-loaded external physics engine.
use anyhow::{Context, Result, bail, ensure};
use gearbox_engine::{Controls, Savestate, Session};
use gearbox_net::Course;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{collections::BTreeMap, io::{self, BufRead, Write}, path::PathBuf};

const UPSTREAM: &str = "e0583ee55168e950a65a645778e591bd26b6a0f2";
const SCHEMA: &str = "tm2020_gearbox_geometry233_v1";

#[derive(Deserialize)]
#[serde(tag="op", rename_all="snake_case", deny_unknown_fields)]
enum Command {
    State,
    Step { controls: [f32; 3], ticks: usize },
    Reset,
    Save,
    Restore { id: u64 },
    Release { id: u64 },
    Quit,
}

struct Host {
    session: Session,
    initial: Savestate,
    course: Course,
    saved: BTreeMap<u64, (Savestate, usize)>,
    next_id: u64,
    tick: usize,
    max_ticks: usize,
    failed: bool,
}

impl Host {
    fn state(&self) -> Result<Value> {
        ensure!(!self.failed, "reset or restore is required after an incomplete engine command");
        let state = gearbox_trace::typed::state(&self.session);
        let raw = state.body.floats();
        let obs = gearbox_net::observe(&self.session, &self.course);
        ensure!(raw.iter().chain(obs.iter()).all(|x|x.is_finite()), "nonfinite physics or observation");
        let race = self.session.race();
        let finished = race.as_ref().is_some_and(|r|r.finish.is_some());
        let car = self.session.vehicle();
        let contacts:[u32;4]=std::array::from_fn(|i|car.wheels[i].contact);
        let materials:[u8;4]=std::array::from_fn(|i|car.wheels[i].material);
        let left=self.course.checkpoints_left(&self.session);
        let goal_at=gearbox_net::observe::COURSE_START+if left>0 {0} else {20};
        let goal_distance=(f64::from(obs[goal_at+3])*5.0).exp_m1();
        let model=self.session.config.model(car.model_choice);
        Ok(json!({"tick":self.tick,"raceMs":self.session.race_ms(),
            "position":state.body.position.map(|x|x.get()),
            "quaternionWxyz":state.body.quaternion.map(|x|x.get()),
            "linearVelocity":state.body.linear_velocity.map(|x|x.get()),
            "angularVelocity":state.body.angular_velocity.map(|x|x.get()),
            "rigidWords":raw.map(f32::to_bits),"observation":obs.as_slice(),
            "observationSchema":SCHEMA,"wheelContact":contacts,
            "wheelMaterial":materials,
            "checkpointsPassed":race.as_ref().map_or(0,|r|r.checkpoints.len()),
            "checkpointsLeft":left,"goalDistanceMetres":goal_distance,
            "lapsCompleted":race.as_ref().map_or(0,|r|r.laps),
            "modelChoice":car.model_choice,"assetBodyMass":model.body.mass,
            "gravity":self.session.dyna.gravity.to_array(),
            "finished":finished,"finishTimeMs":race.and_then(|r|r.finish),
            "upstreamTraceState":state,"completeExactPhysicsQualified":false}))
    }

    fn handle(&mut self, command: Command) -> Result<Value> {
        match command {
            Command::State => self.state(),
            Command::Reset => {
                self.session.restore(&self.initial);self.tick=0;self.failed=false;
                self.state()
            }
            Command::Step{controls,ticks} => {
                ensure!(!self.failed,"reset or restore is required");
                ensure!((1..=1000).contains(&ticks) && self.tick.checked_add(ticks).is_some_and(|n|n<=self.max_ticks),"step budget exceeded");
                ensure!(controls.iter().all(|v|v.is_finite()) && (0.0..=1.0).contains(&controls[0])
                    && (0.0..=1.0).contains(&controls[1]) && (-1.0..=1.0).contains(&controls[2]),"invalid normalized controls");
                ensure!(!self.session.race().is_some_and(|r|r.finish.is_some()),"episode already finished; reset first");
                let action=Controls{gas:controls[0],brake:controls[1],steer:controls[2]};
                let before=self.tick;
                for _ in 0..ticks {
                    self.session.step(action);self.tick+=1;
                    if self.session.race().is_some_and(|r|r.finish.is_some()){break;}
                }
                let mut state=match self.state(){Ok(state)=>state,Err(error)=>{self.failed=true;return Err(error);}};
                state["advancedTicks"]=json!(self.tick-before);
                Ok(state)
            }
            Command::Save => {
                ensure!(!self.failed && self.saved.len()<16,"checkpoint limit or failed engine");
                let id=self.next_id;self.next_id+=1;
                self.saved.insert(id,(self.session.save(),self.tick));Ok(json!({"id":id,"tick":self.tick}))
            }
            Command::Restore{id} => {
                let (saved,tick)=self.saved.get(&id).context("unknown checkpoint")?;
                self.session.restore(saved);self.tick=*tick;self.failed=false;self.state()
            }
            Command::Release{id} => {
                ensure!(self.saved.remove(&id).is_some(),"unknown checkpoint");Ok(json!({"released":id}))
            }
            Command::Quit => Ok(json!({"closed":true})),
        }
    }
}

fn send(value:&Value) -> Result<()> {
    let stdout=io::stdout();let mut out=stdout.lock();
    serde_json::to_writer(&mut out,value)?;out.write_all(b"\n")?;out.flush()?;Ok(())
}

fn run() -> Result<()> {
    let mut map=None;let mut packs=None;let mut max_ticks=100_000usize;let mut seed=2026u32;
    let mut args=std::env::args().skip(1);
    while let Some(arg)=args.next() {
        let value=args.next().with_context(||format!("missing value for {arg}"))?;
        match arg.as_str() {
            "--map" => map=Some(PathBuf::from(value)),
            "--packs" => packs=Some(PathBuf::from(value)),
            "--max-ticks" => max_ticks=value.parse()?,
            "--seed" => seed=value.parse()?,
            _ => bail!("unknown argument {arg}"),
        }
    }
    ensure!((1..=100_000).contains(&max_ticks),"invalid tick limit");
    let map=map.context("--map is required")?;let packs=packs.context("--packs is required")?;
    let options=gearbox_world::OpenOptions{t0:-1500,seed:Some(seed),car:None};
    let mut session=gearbox_world::open_file(&map,&packs,options)?;
    let course=Course::race(&session)?;
    for _ in 0..150 {session.step(Controls::default());}
    ensure!(session.race_ms()==0,"countdown did not reach race start");
    let initial=session.save();
    let mut host=Host{session,initial,course,saved:BTreeMap::new(),next_id:1,tick:0,max_ticks,failed:false};
    let ready=host.state()?;
    send(&json!({"ok":true,"event":"ready","protocol":"tm2020_gearbox_host_v1",
        "upstreamRevision":UPSTREAM,"backendLicense":"GPL-3.0-or-later",
        "sourceGameProcessAccessed":false,"openplanetUsed":false,
        "coldMapLoadedFromInstalledAssets":true,"completeExactPhysicsQualified":false,
        "observationSchema":SCHEMA,"observationCount":gearbox_net::observe::LEN,"state":ready}))?;
    for line in io::stdin().lock().lines() {
        let line=line?;
        if line.len()>65536 {send(&json!({"ok":false,"error":"command size bound"}))?;continue;}
        let packet:Value=match serde_json::from_str(&line){
            Ok(value)=>value,Err(error)=>{send(&json!({"ok":false,"error":error.to_string()}))?;continue;}
        };
        let allowed:&[&str]=match packet.get("op").and_then(Value::as_str){
            Some("step")=>&["op","controls","ticks"],
            Some("restore"|"release")=>&["op","id"],
            _=>&["op"],
        };
        if !packet.as_object().is_some_and(|object|object.keys().all(|key|allowed.contains(&key.as_str()))){
            send(&json!({"ok":false,"error":"unexpected command fields"}))?;continue;
        }
        let command:Command=match serde_json::from_value(packet) {
            Ok(value)=>value,Err(error)=>{send(&json!({"ok":false,"error":error.to_string()}))?;continue;}
        };
        let quit=matches!(command,Command::Quit);
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(||host.handle(command))) {
            Ok(Ok(result))=>send(&json!({"ok":true,"result":result}))?,
            Ok(Err(error))=>send(&json!({"ok":false,"error":format!("{error:#}"),"failed":host.failed}))?,
            Err(payload)=>{
                host.failed=true;
                let error=payload.downcast_ref::<String>().cloned().or_else(||payload.downcast_ref::<&str>().map(|s|s.to_string())).unwrap_or_else(||"engine panic".into());
                send(&json!({"ok":false,"error":error,"failed":true,"unsupportedEnginePath":true}))?;
            }
        }
        if quit {break;}
    }
    Ok(())
}

fn main() {
    if let Err(error)=run() {
        let _=send(&json!({"ok":false,"event":"startup_error","error":format!("{error:#}")}));
        eprintln!("{error:#}");std::process::exit(1);
    }
}
