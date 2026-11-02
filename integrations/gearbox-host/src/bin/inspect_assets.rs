// SPDX-License-Identifier: GPL-3.0-or-later
//! Local-only decoding of installed vehicle assets. No physics exactness claim.
use anyhow::{Result,ensure};
use gearbox_engine::{State,World};
use gearbox_packs::{car_model,packs::PackSet};
use gearbox_world::car::{Car,CarAssets};
use serde_json::json;
use std::{fs,path::PathBuf};

fn main()->Result<()>{
    let args:Vec<PathBuf>=std::env::args_os().skip(1).map(PathBuf::from).collect();
    ensure!(args.len()==2,"inspect_assets PACKS OUTPUT_DIR");ensure!(!args[1].exists(),"output exists");
    fs::create_dir_all(&args[1])?;let packs=PackSet::open(&args[0])?;let mut rows=Vec::new();
    for car in Car::ALL{
        let name=car.pack_name();let source=car_model::load(&packs,name)?;
        let bytes=packs.read_path(&source.tuning_path)?;
        let raw_name=format!("{name}.tuning.private.Gbx");fs::write(args[1].join(&raw_name),&bytes)?;
        let decoded=CarAssets::load(&packs,car,&mut World::default(),&mut State::default())?;
        let dump_name=format!("{name}.decoded.private.txt");fs::write(args[1].join(&dump_name),format!("{decoded:#?}"))?;
        let tuning=decoded.tuning();
        rows.push(json!({"car":name,"modelPath":source.path,"tuningPath":source.tuning_path,
            "activeTuning":decoded.active_tuning,"tuningCount":decoded.tunings.len(),
            "rawTuningLocalFile":raw_name,"decodedLocalFile":dump_name,"rawTuningBytes":bytes.len(),
            "bodyMass":decoded.body.mass,"bodyCenter":[decoded.body.center_x,decoded.body.center_y,decoded.body.center_z],
            "bodySubstepDistance":decoded.body.substep_distance,"modelKind":tuning.model_kind,
            "suspensionKind":tuning.suspension_kind,"suspensionStiffness":tuning.suspension_stiffness,
            "suspensionDamping":tuning.suspension_damping,"suspensionRestLength":tuning.suspension_rest_length,
            "suspensionRecoveryRate":tuning.suspension_recovery_rate,
            "maximumSpeed":tuning.maximum_speed,"airLinearDrag":tuning.air_linear_drag,
            "groundGravityMultiplier":tuning.ground_gravity,"airGravityMultiplier":tuning.air_gravity,
            "contactRestitutionParameter":tuning.contact_restitution,
            "gearRatios":tuning.gear_ratios.0,"upshiftRatios":tuning.upshift_ratios.0,
            "downshiftRatios":tuning.downshift_ratios.0,
            "fieldNamesAreUpstreamInterpretations":true,"independentPhysicsValidation":false}));
        println!("DECODED {name} tunings={} mass={}",decoded.tunings.len(),decoded.body.mass);
    }
    fs::write(args[1].join("report.json"),serde_json::to_vec_pretty(&json!({
        "schema":"tm2020_installed_vehicle_asset_decoding_v1",
        "upstreamRevision":"e0583ee55168e950a65a645778e591bd26b6a0f2","cars":rows,
        "sourceGameProcessAccessed":false,"openplanetUsed":false,"rawAssetsAreLocalOnly":true,
        "completeExactSimulatorQualified":false}))?)?;Ok(())
}
