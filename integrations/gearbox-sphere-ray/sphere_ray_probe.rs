// SPDX-License-Identifier: GPL-3.0-or-later
//! Check the patched Rust engine against numeric outputs from original code.
use anyhow::{Result,ensure};
use gearbox_engine::{Vec3,EntryId,ShapeEntryId};
use gearbox_engine::collision::{Ray,RayHit,SphereShape,QueryFilter,SkipMaterial,ray_sphere};
use serde_json::json;
use std::{fs,path::PathBuf};
struct Input{bytes:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let value=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn f(&mut self)->f32{f32::from_bits(self.word())}
    fn v(&mut self)->Vec3{Vec3::new(self.f(),self.f(),self.f())}
}
fn main()->Result<()>{
    let args:Vec<PathBuf>=std::env::args_os().skip(1).map(PathBuf::from).collect();
    ensure!(args.len()==2,"sphere_ray_probe NUMERIC_CASES NEW_REPORT");
    ensure!(!args[1].exists(),"Never overwrite sphere ray oracle output");
    let bytes=fs::read(&args[0])?;
    ensure!(bytes.len()==12+20000*128&&&bytes[..8]==b"TMRSP001","Unknown sphere ray evidence");
    let mut input=Input{bytes,at:8};ensure!(input.word()==20000,"Unexpected count");
    let entry=EntryId::Discrete(ShapeEntryId(0));let mut hits=0;
    for case in 0..20000{
        let center=input.v();let radius=input.f();let material=input.word() as u16;
        let ray=Ray{origin:input.v(),direction:input.v()};let displacement=input.v();let skip=input.word() as u8;
        let initial=RayHit{fraction:input.f(),point:input.v(),normal:input.v(),material:input.word() as u16,entry,triangle:9};
        let expected_hit=input.word()!=0;
        let bits:[u32;8]=std::array::from_fn(|_|input.word());
        let mut current=Some(initial);let mut filter=QueryFilter::default();filter.skip_material=SkipMaterial::from_id(skip);
        ray_sphere(&SphereShape{radius,material},entry,center,ray,displacement,filter,&mut current);
        let actual=current.unwrap();let classified=actual.triangle==0;
        ensure!(classified==expected_hit,"ray sphere classification case {case}");
        let out=[actual.fraction.to_bits(),actual.point.x.to_bits(),actual.point.y.to_bits(),actual.point.z.to_bits(),
            actual.normal.x.to_bits(),actual.normal.y.to_bits(),actual.normal.z.to_bits(),u32::from(actual.material)];
        ensure!(out==bits,"ray sphere defined bits case {case}");
        if classified{hits+=1;}
    }
    let report=json!({"schema":"tm2020_rust_original_sphere_ray_oracle_v1","cases":20000,
        "hits":hits,"classificationAndDefinedBitsExact":true,"patchedEngineQueryFunctionExercised":true,
        "officialServerUsed":false,"completeExactSimulatorQualified":false});
    fs::write(&args[1],serde_json::to_vec_pretty(&report)?)?;
    println!("PASS SPHERE_RAY_RUST cases=20000 hits={hits}");Ok(())
}
