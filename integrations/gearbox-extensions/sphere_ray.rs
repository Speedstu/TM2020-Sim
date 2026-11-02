// SPDX-License-Identifier: GPL-3.0-or-later
//! Original 0x1a5580 sphere-ray arithmetic. Caller owns the closest hit.
use super::{FAR,Ray,RayHit};
use crate::collision::{QueryFilter,SphereShape};
use crate::{EntryId,Vec3};

pub fn sphere(shape:&SphereShape,entry:EntryId,center:Vec3,ray:Ray,displacement:Vec3,
    filter:QueryFilter,hit:&mut Option<RayHit>){
    if filter.skip_material.skips(shape.material as u8){return;}
    let delta=ray.origin-center;
    let relative=ray.direction-displacement;
    let radius=shape.radius;
    let c=((delta.y*delta.y+delta.x*delta.x)+delta.z*delta.z)-radius*radius;
    let mut fraction=0.0f32;
    if c>0.0{
        let a=(relative.y*relative.y+relative.x*relative.x)+relative.z*relative.z;
        let dot=(relative.y*delta.y+relative.x*delta.x)+relative.z*delta.z;
        let b=dot+dot;
        if a.abs()<0.00001{
            if b.abs()<0.00001{
                if !(c.abs()<0.00001){return;}
            }else{fraction=-c/b;}
        }else{
            let discriminant=b*b-(a*4.0)*c;
            if discriminant<0.0{return;}
            let root=discriminant.sqrt();
            let scale=0.5/a;
            fraction=scale*(-b-root);
        }
        if fraction<0.0||fraction>1.0{return;}
    }
    let limit=hit.as_ref().map_or(FAR,|h|h.fraction);
    if !(limit>fraction){return;}
    let point=Vec3::new(
        ray.origin.x+ray.direction.x*fraction,
        ray.origin.y+ray.direction.y*fraction,
        ray.origin.z+ray.direction.z*fraction,
    );
    let mut normal=Vec3::new(
        point.x-(center.x+displacement.x*fraction),
        point.y-(center.y+displacement.y*fraction),
        point.z-(center.z+displacement.z*fraction),
    );
    let squared=(normal.y*normal.y+normal.x*normal.x)+normal.z*normal.z;
    if squared>1.0e-10&&squared<f32::MAX{
        let inverse=1.0/squared.sqrt();
        normal=Vec3::new(normal.x*inverse,normal.y*inverse,normal.z*inverse);
    }
    *hit=Some(RayHit{fraction,point,normal,material:shape.material,entry,triangle:0});
}
