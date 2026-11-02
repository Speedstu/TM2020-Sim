#include "tm2020/recovered_collision.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
bool collide_spheres(const Sphere& a,const Sphere& b,SphereContact& output){
    for(const auto* sphere:{&a,&b}){
        if(!std::isfinite(sphere->radius)||sphere->radius<0||sphere->radius>1e6f)throw std::invalid_argument("Invalid sphere radius");
        for(float x:sphere->center)if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Invalid sphere center");
    }
    const std::array delta{b.center[0]-a.center[0],b.center[1]-a.center[1],b.center[2]-a.center[2]};
    const float squared=(delta[1]*delta[1]+delta[0]*delta[0])+delta[2]*delta[2];
    const float radius=a.radius+b.radius;if(squared>=radius*radius)return false;
    auto next=output;const float distance=std::sqrt(squared);
    if(distance>9.999999747378752e-6f){
        const float inverse=1.f/distance;const std::array direction{inverse*delta[0],inverse*delta[1],inverse*delta[2]};
        const float penetration=(a.radius+b.radius)-distance;
        for(std::size_t k=0;k<3;k++){
            next.normal[k]=-direction[k];next.penetration_vector[k]=next.normal[k]*penetration;
            next.surface_point_a[k]=direction[k]*a.radius+a.center[k];
        }
        next.flags&=~3u;
    }else{
        next.normal={0,-1,0};const float penetration=-b.radius;
        next.penetration_vector={penetration*0.f,penetration,penetration*0.f};next.surface_point_a=a.center;
    }
    next.surface_id_a=a.surface_id;next.surface_id_b=b.surface_id;output=next;return true;
}
}
