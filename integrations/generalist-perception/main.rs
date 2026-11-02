// SPDX-License-Identifier: GPL-3.0-or-later
// Prototype: current vehicle + local collision geometry, with no replay path.
use anyhow::{Result,ensure};
use gearbox_engine::{Controls,Session,Vec3};
use serde_json::{Value,json};
use std::{path::Path,time::Instant};

fn ray(session:&Session,local_origin:[f32;3],local_delta:[f32;3])->Value{
    let body=session.body();
    let origin=body.pos+body.rot*Vec3::from(local_origin);
    let direction=body.rot*Vec3::from(local_delta);
    match session.pick_static(origin,direction){
        None=>json!({"hit":false,"fraction":1.0,"pointLocal":null,"normalLocal":null,"material":null}),
        Some(hit)=>json!({"hit":true,"fraction":hit.fraction,
            "pointLocal":body.rot.transpose_mul_vec(hit.point-body.pos).to_array(),
            "normalLocal":body.rot.transpose_mul_vec(hit.normal).to_array(),
            "material":hit.material}),
    }
}

fn snapshot(session:&Session)->Value{
    let body=session.body();let car=session.vehicle();
    let mut ground=Vec::new();
    for z in [0.,5.,10.,20.,35.,50.,75.,100.]{
        for x in [-12.,-6.,0.,6.,12.]{
            ground.push(json!({"originLocal":[x,6.,z],"deltaLocal":[0.,-24.,0.],
                "result":ray(session,[x,6.,z],[0.,-24.,0.])}));
        }
    }
    let mut obstacles=Vec::new();
    for level in [0.5,2.]{
        for index in 0..13{
            let angle=(index as f32-6.)*std::f32::consts::PI/12.;
            let delta=[80.*angle.sin(),0.,80.*angle.cos()];
            obstacles.push(json!({"originLocal":[0.,level,0.],"deltaLocal":delta,
                "result":ray(session,[0.,level,0.],delta)}));
        }
    }
    let wheels:Vec<_>=car.wheels.iter().map(|w|json!({"contact":w.contact!=0,
        "surfaceRaw":w.surface,"materialRaw":w.material,"slip":w.slip,
        "steeringAngle":w.steering_angle,"suspensionLength":w.suspension_length})).collect();
    let waypoints:Vec<_>=session.waypoint_triggers().iter().map(|w|{
        let center=Vec3::from(std::array::from_fn(|k|(w.min[k]+w.max[k])*0.5));
        json!({"kind":w.kind,"order":session.waypoint_order(w.waypoint),
            "centerLocal":body.rot.transpose_mul_vec(center-body.pos).to_array(),
            "halfExtentWorld":std::array::from_fn::<_,3,_>(|k|(w.max[k]-w.min[k])*0.5)})
    }).collect();
    json!({"schema":"tm2020_route_free_perception_prototype_v1",
        "vehicle":{"model":car.model_choice,
            "velocityLocal":body.rot.transpose_mul_vec(body.vel).to_array(),
            "angularVelocityLocal":body.rot.transpose_mul_vec(body.ang_vel).to_array(),
            "worldUpLocal":body.rot.transpose_mul_vec(Vec3::from([0.,1.,0.])).to_array(),
            "steering":car.steering,"rpm":car.rpm,"gear":car.gear,"wheels":wheels,
            "turboActive":car.turbo_active!=0,"bodyContact":car.body_contact!=0,
            "driftDirection":car.drift_direction},
        "groundRays":ground,"obstacleRays":obstacles,"waypoints":waypoints})
}

fn main()->Result<()>{
    let a:Vec<_>=std::env::args().collect();
    ensure!(a.len()==4,"tm2020-map-perception MAP PACKS OUTPUT.json (no replay argument)");
    ensure!(!Path::new(&a[3]).exists(),"output must be new");
    let begin=Instant::now();let bytes=std::fs::read(&a[1])?;let map=gearbox_gbx::Map::parse(&bytes)?;
    let mut session=gearbox_world::open_file(Path::new(&a[1]),Path::new(&a[2]),
        gearbox_world::OpenOptions{t0:-1500,seed:Some(2026),car:None})?;
    for _ in 0..150{session.step(Controls::default());}
    ensure!(session.race_ms()==0,"missing race zero");
    let before=session.save();let words_before=format!("{:?}",session.body());
    let observation=snapshot(&session);
    ensure!(words_before==format!("{:?}",session.body()),"perception changed actual body");
    session.restore(&before);let repeated=snapshot(&session);
    ensure!(observation==repeated,"perception is not deterministic across complete restore");
    let report=json!({"mapMetadata":{"uid":map.uid,"name":map.name,"blocks":map.blocks.len(),"items":map.items.len()},
        "observation":observation,"replayRequired":false,"expertTrajectoryRead":false,
        "uidOrNameInObservation":false,"readOnlyPerceptionRepeatedExactly":true,
        "groundRayCount":40,"obstacleRayCount":26,"seconds":begin.elapsed().as_secs_f64(),
        "navigationSolved":false,"learnedPolicyIncluded":false,"liveSdkParityQualified":false,
        "limitations":["rays use collision geometry; surface IDs still require a stable categorical schema",
            "checkpoint order alone does not solve routing, jumps, cuts or overlapping roads",
            "no input history, tyre effect timers or recurrent state contract yet"]});
    let encoded=serde_json::to_vec_pretty(&report)?;
    std::fs::OpenOptions::new().write(true).create_new(true).open(&a[3])?
        .write_all(&encoded)?;
    println!("ROUTE_FREE_PERCEPTION {} rays=66 restore_exact=true",a[1]);Ok(())
}
use std::io::Write;
