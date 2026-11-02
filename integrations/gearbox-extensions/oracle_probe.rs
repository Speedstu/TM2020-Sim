// SPDX-License-Identifier: GPL-3.0-or-later
//! Compare patched-engine geometry to numeric outputs of original instructions.
use anyhow::{Result,ensure};
use gearbox_engine::{Vec3,State,World,ShapeId,SphereId,EntryId,ShapeEntryId,Iso,Mat3};
use gearbox_engine::arrays::CookedTriangle;
use gearbox_engine::collision::{Contact,ContactFlags,SphereShape,ContactList,Surface,Geometry,QueryFilter,SkipMaterial};
use serde_json::json;
use std::{fs,path::PathBuf};
mod wake_queue;

struct Input{bytes:Vec<u8>,at:usize}
impl Input{
    fn word(&mut self)->u32{let x=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;x}
    fn float(&mut self)->f32{f32::from_bits(self.word())}
    fn vec(&mut self)->Vec3{Vec3::new(self.float(),self.float(),self.float())}
}
fn input(path:PathBuf,magic:&[u8])->Result<(Input,u32)>{
    let bytes=fs::read(path)?;ensure!(bytes.len()>=12&&&bytes[..8]==magic,"wrong numeric oracle format");
    let mut reader=Input{bytes,at:8};let count=reader.word();ensure!((100..=1000000).contains(&count),"case bound");Ok((reader,count))
}
fn main()->Result<()>{
    let args:Vec<PathBuf>=std::env::args_os().skip(1).map(PathBuf::from).collect();ensure!((2..=3).contains(&args.len()),"oracle_probe GEOMETRY_NUMERIC_FOLDER REPORT [WAKE_CASE_FILE]");
    ensure!(!args[1].exists(),"output exists");
    let (mut rays,ray_count)=input(args[0].join("ray-triangle.cases"),b"TMRAY001")?;
    ensure!(rays.bytes.len()==12+ray_count as usize*124,"ray record size");
    let mut ray_hits=0;let mut two_hits=0;
    for case in 0..ray_count{
        let vertices=[rays.vec(),rays.vec(),rays.vec()];let normal=rays.vec();let offset=rays.float();
        let verts=[rays.word(),rays.word(),rays.word()];let ids=rays.word() as u16;
        let cooked=[CookedTriangle{normal,offset,verts,ids}];
        let origin=rays.vec();let direction=rays.vec();let two=rays.word()!=0;
        let max=rays.float();let _initial_u=rays.float();let _initial_v=rays.float();
        let expected=rays.word()!=0;let expected_fraction=rays.word();let _u=rays.word();let _v=rays.word();
        let mesh=gearbox_engine::shape::Mesh{vertices:&vertices,triangles:&[],cooked:&cooked,nodes:&[]};
        let actual=gearbox_engine::collision::ray_triangle(mesh,gearbox_engine::collision::Ray{origin,direction},0,two,max);
        ensure!(actual.is_some()==expected,"ray overlap case {case}");
        if let Some(fraction)=actual{
            ensure!(fraction.to_bits()==expected_fraction,"ray fraction case {case}: {:08x} != {:08x}",fraction.to_bits(),expected_fraction);
            ray_hits+=1;if two{two_hits+=1;}
        }
    }
    let (mut spheres,sphere_count)=input(args[0].join("sphere-sphere.cases"),b"TMSPH001")?;
    ensure!(spheres.bytes.len()==12+sphere_count as usize*140,"sphere record size");
    let mut sphere_hits=0;
    for case in 0..sphere_count{
        let ac=spheres.vec();let ar=spheres.float();let am=spheres.word() as u16;
        let bc=spheres.vec();let br=spheres.float();let bm=spheres.word() as u16;
        let mut out=Contact{penetration:spheres.vec(),normal:spheres.vec(),point:spheres.vec(),
            material_a:spheres.word() as u16,material_b:spheres.word() as u16,flags:ContactFlags::from_bits(spheres.word()),..Default::default()};
        let expected=spheres.word()!=0;let bits:[u32;12]=std::array::from_fn(|_|spheres.word());
        let a=SphereShape{radius:ar,material:am};let b=SphereShape{radius:br,material:bm};
        let hit=gearbox_engine::collision::narrow::sphere_pair::evaluate(&a,ac,&b,bc,&mut out);
        let actual=[out.penetration.x.to_bits(),out.penetration.y.to_bits(),out.penetration.z.to_bits(),
            out.normal.x.to_bits(),out.normal.y.to_bits(),out.normal.z.to_bits(),
            out.point.x.to_bits(),out.point.y.to_bits(),out.point.z.to_bits(),u32::from(out.material_a),u32::from(out.material_b),out.flags.bits()];
        ensure!(hit==expected&&actual==bits,"sphere defined output case {case}");
        // Exercise the real narrow-phase dispatcher as well as the arithmetic entry.
        let mut state=State::default();state.sphere_shape=vec![a,b];let world=World::default();
        let aid=EntryId::Discrete(ShapeEntryId(0));let bid=EntryId::Discrete(ShapeEntryId(1));
        let sa=Surface{shape:ShapeId::Sphere(SphereId(0)),iso:Iso{pos:ac,..Iso::IDENTITY},..Default::default()};
        let sb=Surface{shape:ShapeId::Sphere(SphereId(1)),iso:Iso{pos:bc,..Iso::IDENTITY},..Default::default()};
        let mut contacts=ContactList::new(1);
        gearbox_engine::collision::narrow::contacts(Geometry::new(&world,&state),aid,&sa,bid,&sb,&mut contacts);
        ensure!(contacts.len()==usize::from(hit),"sphere dispatcher count case {case}");
        if hit{let c=&contacts.as_slice()[0];ensure!(c.a==Some(aid)&&c.b==Some(bid),"sphere ownership");sphere_hits+=1;}
    }
    let (mut meshes,mesh_count)=input(args[0].join("ray-mesh.cases"),b"TMRMS002")?;
    ensure!(meshes.bytes.len()==12+mesh_count as usize*336,"full mesh record size");
    let mut mesh_hits=0;let mut mesh_two_hits=0;
    for case in 0..mesh_count{
        let vertices:[Vec3;9]=std::array::from_fn(|_|meshes.vec());
        let cooked:[CookedTriangle;3]=std::array::from_fn(|_|{
            let normal=meshes.vec();let offset=meshes.float();
            let verts=[meshes.word(),meshes.word(),meshes.word()];let ids=meshes.word() as u16;
            CookedTriangle{normal,offset,verts,ids}
        });
        let rot=Mat3{rows:[meshes.vec(),meshes.vec(),meshes.vec()]};let pos=meshes.vec();
        let origin=meshes.vec();let direction=meshes.vec();let displacement=meshes.vec();
        let skip=meshes.word() as u8;let two=meshes.word()!=0;let expected=meshes.word()!=0;
        let bits:[u32;9]=std::array::from_fn(|_|meshes.word());
        let triangle=cooked.map(|t|gearbox_engine::arrays::Triangle{verts:t.verts,surface:t.ids as u8,gameplay:(t.ids>>8) as u8,tie_break:0});
        let tree=gearbox_engine::shape::Mesh::build_tree(&vertices,&triangle);
        let mesh=gearbox_engine::shape::Mesh{vertices:&vertices,triangles:&triangle,cooked:&cooked,nodes:&tree.nodes};
        let entry=EntryId::Discrete(ShapeEntryId(17));let mut hit=None;
        let filter=QueryFilter{two_sided:two,skip_material:SkipMaterial::from_id(skip),..Default::default()};
        gearbox_engine::collision::ray_mesh(mesh,entry,Iso{rot,pos},gearbox_engine::collision::Ray{origin,direction},displacement,filter,&mut hit);
        ensure!(hit.is_some()==expected,"full mesh classification case {case}");
        if let Some(hit)=hit{
            let actual=[hit.fraction.to_bits(),hit.point.x.to_bits(),hit.point.y.to_bits(),hit.point.z.to_bits(),
                hit.normal.x.to_bits(),hit.normal.y.to_bits(),hit.normal.z.to_bits(),u32::from(hit.material),hit.triangle];
            ensure!(actual==bits,"full mesh defined output case {case}: {actual:x?} != {bits:x?}");
            ensure!(hit.entry==entry,"full mesh ownership case {case}");mesh_hits+=1;if two{mesh_two_hits+=1;}
        }
    }
    let report=json!({"schema":"tm2020_patched_engine_geometry_oracle_v1","rayCases":ray_count,
        "rayHits":ray_hits,"twoSidedHits":two_hits,"rayFractionAndClassificationBitExact":true,
        "sphereCases":sphere_count,"sphereHits":sphere_hits,"sphereDefinedOutputBitsExact":true,
        "sphereDispatcherExercised":true,"sourceGameProcessAccessed":false,"completeExactSimulatorQualified":false});
    let mut report=report;
    report["fullMeshCases"]=json!(mesh_count);report["fullMeshHits"]=json!(mesh_hits);
    report["fullMeshTwoSidedHits"]=json!(mesh_two_hits);report["fullMeshDefinedOutputBitsExact"]=json!(true);
    report["fullMeshTrianglesPerCase"]=json!(3);report["fullMeshGeneralEulerRotations"]=json!(true);
    report["equalFractionTieCasesIncluded"]=json!(true);
    let (mut wakes,wake_count)=input(args.get(2).cloned().unwrap_or_else(||args[0].join("wake-queue.cases")),b"TMWAK001")?;
    ensure!(wakes.bytes.len()==12+wake_count as usize*396,"wake record size");
    fn indices(reader:&mut Input)->[wake_queue::Index;8]{
        std::array::from_fn(|_|{let rest_since=reader.word();let bits=reader.word();
            wake_queue::Index{rest_since,active_index:bits as u16,reserved:(bits>>16) as u8,queued:(bits>>24) as u8}})
    }
    for case in 0..wake_count{
        let enabled=wakes.word()!=0;let mut state=indices(&mut wakes);
        let reverse:[u32;8]=std::array::from_fn(|_|wakes.word());let initial_count=wakes.word() as usize;
        let storage:[u32;12]=std::array::from_fn(|_|wakes.word());ensure!(initial_count<=4,"initial wake prefix");
        let plan:[u32;32]=std::array::from_fn(|_|wakes.word());
        let expected_indices=indices(&mut wakes);let expected_count=wakes.word() as usize;
        let expected_queue:[u32;12]=std::array::from_fn(|_|wakes.word());ensure!(expected_count<=12,"expected wake prefix");
        let mut pending=storage[..initial_count].to_vec();
        for slot in plan{wake_queue::request(enabled,slot as usize,&mut state,&reverse,&mut pending)?;}
        ensure!(state==expected_indices&&pending==expected_queue[..expected_count],"wake enqueue case {case}");
    }
    report["wakeCases"]=json!(wake_count);report["wakeRequests"]=json!(wake_count*32);
    report["wakeQueueLogicalBitsExact"]=json!(true);report["wakeActivationConsumerQualified"]=json!(false);
    fs::write(&args[1],serde_json::to_vec_pretty(&report)?)?;
    println!("PASS PATCHED_ENGINE_ORIGINAL_GEOMETRY ray={ray_count} sphere={sphere_count}");Ok(())
}
