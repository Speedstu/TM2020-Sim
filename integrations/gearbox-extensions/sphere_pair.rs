// SPDX-License-Identifier: GPL-3.0-or-later
// Port of original 0x1a17f0. Independently checked against pinned instructions.
use super::super::{Contact, ContactFlags, ContactSink, SphereShape, Surface};
use crate::{EntryId, Vec3};

fn overlap(a:&SphereShape,ac:Vec3,b:&SphereShape,bc:Vec3)->bool{
    let delta=bc-ac;let squared=(delta.y*delta.y+delta.x*delta.x)+delta.z*delta.z;
    let radius=a.radius+b.radius;squared<radius*radius
}

pub fn evaluate(a:&SphereShape,ac:Vec3,b:&SphereShape,bc:Vec3,out:&mut Contact)->bool{
    let delta=bc-ac;
    let squared=(delta.y*delta.y+delta.x*delta.x)+delta.z*delta.z;
    let radius=a.radius+b.radius;
    if squared>=radius*radius{return false;}
    let distance=squared.sqrt();
    if distance>0.00001{
        let inverse=1.0/distance;
        let direction=Vec3::new(inverse*delta.x,inverse*delta.y,inverse*delta.z);
        let penetration=(a.radius+b.radius)-distance;
        out.normal=-direction;
        out.penetration=Vec3::new(out.normal.x*penetration,out.normal.y*penetration,out.normal.z*penetration);
        out.point=Vec3::new(direction.x*a.radius+ac.x,direction.y*a.radius+ac.y,direction.z*a.radius+ac.z);
        out.flags.set(ContactFlags::FACE,false);out.flags.set(ContactFlags::OTHER_POINT,false);
    }else{
        out.normal=Vec3::new(0.0,-1.0,0.0);
        let penetration=-b.radius;
        out.penetration=Vec3::new(penetration*0.0,penetration,penetration*0.0);
        out.point=ac;
    }
    out.material_a=a.material;out.material_b=b.material;true
}

pub fn contacts(a:&SphereShape,ar:EntryId,ap:&Surface,b:&SphereShape,br:EntryId,bp:&Surface,out:&mut impl ContactSink){
    if !overlap(a,ap.iso.pos,b,bp.iso.pos){return;}
    let contact=out.take_contact();
    evaluate(a,ap.iso.pos,b,bp.iso.pos,contact);
    contact.a=Some(ar);contact.b=Some(br);
}
