// SPDX-License-Identifier: GPL-3.0-or-later
use anyhow::{Result,ensure};
use gearbox_packs::packs::PackSet;
use serde_json::json;
use std::{collections::BTreeSet,fs,path::PathBuf};
fn main()->Result<()>{
    let args:Vec<PathBuf>=std::env::args_os().skip(1).map(PathBuf::from).collect();
    ensure!(args.len()==2,"asset_catalog PACKS REPORT");ensure!(!args[1].exists(),"output exists");
    let packs=PackSet::open(&args[0])?;let mut models=BTreeSet::new();let mut bay=BTreeSet::new();let mut items=BTreeSet::new();
    for pack in &packs.paks{for index in 0..pack.files.len(){
        let path=pack.file_path(index);let lower=path.replace('\\',"/").to_lowercase();
        if lower.ends_with(".vehiclephymodel.gbx"){models.insert(path.clone());}
        if lower.contains("baycar")||lower.contains("carbay"){bay.insert(path.clone());}
        if lower.starts_with("vehicles/items/cars/")&&lower.ends_with(".item.gbx"){items.insert(path);}
    }}
    let mut resolved=Vec::new();
    for car in gearbox_world::car::Car::ALL{
        let model=gearbox_packs::car_model::load(&packs,car.pack_name())?;
        resolved.push(json!({"car":car.pack_name(),"modelPath":model.path,"tuningPath":model.tuning_path}));
    }
    let requested:Vec<_>=["BayCar","CarBay"].iter().map(|name|{
        let path=format!("Vehicles/Items/Cars/{name}.Item.Gbx");let result=packs.read_path(&path);
        json!({"name":name,"itemPath":path,"readable":result.is_ok(),"error":result.err().map(|e|format!("{e:#}"))})
    }).collect();
    fs::write(&args[1],serde_json::to_vec_pretty(&json!({"schema":"tm2020_installed_physics_asset_catalog_v1",
        "visibleVehicleModelIndexNames":models,"visibleVehicleItems":items,"bayNamedIndexEntries":bay,
        "resolvedSupportedVehicleModels":resolved,"requestedVehicleItemPaths":requested,
        "scope":"readable installed packs; hashed index entries are not a complete plain-text name catalog",
        "sourceGameProcessAccessed":false,"completeExactSimulatorQualified":false}))?)?;
    println!("CATALOG models={} items={} bay_named={}",models.len(),items.len(),bay.len());Ok(())
}
