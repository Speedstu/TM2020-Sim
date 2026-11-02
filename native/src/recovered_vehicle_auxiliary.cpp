#include "tm2020/recovered_vehicle.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void scalar(float x){if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Auxiliary vehicle force exceeds finite domain");}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)scalar(x);}
}
void apply_local_force(ForceAccumulator& accumulator,const RigidState& pose,const std::array<float,3>& local){
    bounded(accumulator.linear);bounded(accumulator.angular);bounded(pose.rotation);bounded(local);auto next=accumulator;
    std::array<float,3> force{};for(std::size_t k=0;k<3;k++)force[k]=(local[1]*pose.rotation[3*k+1]+local[0]*pose.rotation[3*k])+local[2]*pose.rotation[3*k+2];
    next.linear[0]=next.linear[0]+force[0];next.linear[1]=force[1]+next.linear[1];next.linear[2]=force[2]+next.linear[2];
    bounded(next.linear);accumulator=next;
}
void apply_auxiliary_vehicle_forces(ForceAccumulator& accumulator,const RigidState& pose,const std::array<float,3>& center,
    const AuxiliaryVehicleForceState& state,const AuxiliaryVehicleForceParameters& config,
    std::span<const AuxiliaryWheelForcePoint> wheels,float magnitude){
    bounded(accumulator.linear);bounded(accumulator.angular);bounded(pose.rotation);bounded(pose.position);bounded(center);bounded(state.local_velocity);
    scalar(state.scalar_98);scalar(state.scalar_9c);scalar(magnitude);bounded(std::array{config.coefficient_1efc,config.coefficient_1f00,config.coefficient_1f04,config.coefficient_1f08});
    if(wheels.size()>4||config.coefficient_1f00<0)throw std::invalid_argument("Auxiliary vehicle force exceeds wheel/denominator domain");
    for(const auto& wheel:wheels)bounded(wheel.local_point);
    if(state.local_velocity[2]<=6||magnitude<1e-5f)return;
    auto next=accumulator;
    const auto sa=state.state_word_176c,sb=state.state_word_1370;
    const bool mode1=(sa&3)==1||(sb&3)==1,mode2=(sa&3)==2||(sb&3)==2,bit4=((sa|sb)&4)!=0;
    const float vx=state.local_velocity[0],vy=state.local_velocity[1],vz=state.local_velocity[2];const float squared=(vy*vy+vx*vx)+vz*vz;float normalized=vx;
    if(squared>1e-10f&&squared<3.4028234663852886e38f)normalized=(1.f/std::sqrt(squared))*vx;
    const bool scalar9c_active=state.scalar_9c>.1f,scalar98_active=state.scalar_98>.1f;
    if(!bit4&&scalar9c_active){const float scale=magnitude*(-.1f);apply_local_force(next,pose,{vx*scale,vy*scale,vz*scale});}
    std::array<float,3> front{},rear{};
    if(!mode1&&(mode2||(scalar98_active&&!scalar9c_active))){
        const float weight=mode2?1.f:state.scalar_98;
        const float absolute=std::abs(normalized),gain=weight*config.coefficient_1f08,denominator=(weight*config.coefficient_1f00)+1.f,slope=absolute*20.f+1.f,vertical=std::abs(vz)+1.f,zden=vertical*vertical;
        front[0]=((config.coefficient_1efc*normalized)/denominator)*magnitude;rear[0]=(((normalized*(-1.f))*config.coefficient_1efc)/denominator)*magnitude;
        front[1]=magnitude*0.f;rear[1]=magnitude*0.f;
        front[2]=(((((gain*1.5f)*absolute)*slope)*config.coefficient_1f04)/zden)*magnitude;
        rear[2]=((((gain*absolute)*slope)*config.coefficient_1f04)/zden)*magnitude;
    }
    for(std::size_t j=0;j<wheels.size();j++)if(!scalar9c_active&&wheels[j].flags_70!=0)apply_local_force_at_point(next,pose,center,j<2?front:rear,wheels[j].local_point);
    bounded(next.linear);bounded(next.angular);accumulator=next;
}
}
