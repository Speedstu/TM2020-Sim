#include "tm2020/recovered_rigid.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* text){if(!b)throw std::invalid_argument(text);}
template<std::size_t N>void finite(const std::array<float,N>& values){
    for(float x:values)require(std::isfinite(x)&&std::abs(x)<=1e10f,"Recovered kernel input out of qualified finite range");
}
void validate(const RigidState& s,const BodyParameters& p){
    finite(s.rotation);finite(s.position);finite(s.quaternion);finite(s.linear_velocity);finite(s.angular_velocity);
    finite(p.auxiliary_model_values);
    require(std::isfinite(p.angular_speed_limit)&&p.angular_speed_limit>=0&&p.angular_speed_limit<=1e10f,"Invalid angular speed limit");
}
void interval_ok(float dt){require(std::isfinite(dt)&&dt>=0&&dt<=1,"Invalid recovered integration interval");}
// Operation order follows scalar SSE instructions; FMA contraction is disabled.
void quaternion_unchecked(std::array<float,4>& q,const std::array<float,3>& o,float dt){
    const float w=q[0],x=q[1],y=q[2],z=q[3],a=o[0],b=o[1],c=o[2];
    float nw=((-a*x-b*y)-c*z)*.5f;
    float nx=((z*b+w*a)-c*y)*.5f;
    float ny=((w*b-z*a)+c*x)*.5f;
    nw=nw*dt+w;nx=nx*dt+x;ny=ny*dt+y;
    float nz=((y*a-b*x)+w*c)*.5f;nz=nz*dt+z;
    const float squared=((nw*nw+nx*nx)+ny*ny)+nz*nz;
    const float inverse=1.f/std::sqrt(squared);
    if(inverse>1e-5f&&inverse<std::numeric_limits<float>::max())q={nw*inverse,nx*inverse,ny*inverse,nz*inverse};
    else q={1,0,0,0};
}
void matrix_unchecked(std::array<float,9>& m,const std::array<float,4>& q){
    const float w=q[0],x=q[1],y=q[2],z=q[3];
    const float tz=z+z,tx=x+x,ty=y+y;
    const float zz=z*tz,wz=w*tz,yz=y*tz,xz=x*tz,wy=w*ty,yy=y*ty,xy=x*ty,wx=w*tx,xx=x*tx;
    m={(1.f-yy)-zz,xy-wz,xz+wy,xy+wz,(1.f-xx)-zz,yz-wx,xz-wy,yz+wx,(1.f-xx)-yy};
}
void pose_unchecked(RigidState& s,const BodyParameters& p,AuxiliaryOutput& out,float dt){
    for(std::size_t i=0;i<3;i++)s.position[i]=dt*s.linear_velocity[i]+s.position[i];
    const auto& o=s.angular_velocity;
    const float squared=(o[0]*o[0]+o[1]*o[1])+o[2]*o[2];
    if(squared>1.000000013351432e-10f)quaternion_unchecked(s.quaternion,o,dt);
    matrix_unchecked(s.rotation,s.quaternion);
    for(std::size_t i=0;i<3;i++)out[i]=p.auxiliary_model_values[i];
    for(auto& v:s.linear_velocity)v=v>=-10000.f?std::min(v,10000.f):-10000.f;
    if(squared>p.angular_speed_limit*p.angular_speed_limit){
        const float scale=p.angular_speed_limit/std::sqrt(squared);
        for(auto& v:s.angular_velocity)v=scale*v;
    }
}
}
void integrate_quaternion(std::array<float,4>& q,const std::array<float,3>& omega,float dt){finite(q);finite(omega);interval_ok(dt);quaternion_unchecked(q,omega,dt);}
void quaternion_to_matrix(std::array<float,9>& matrix,const std::array<float,4>& q){finite(q);matrix_unchecked(matrix,q);}
void integrate_pose(RigidState& s,const BodyParameters& p,AuxiliaryOutput& out,float dt){validate(s,p);finite(out);interval_ok(dt);pose_unchecked(s,p,out,dt);}
namespace {
void validate_forces(const RigidState& s,const ForceAccumulator& forces,const VelocityStepParameters& p,const GravityEnvironment& env,float dt){
    finite(s.linear_velocity);finite(s.angular_velocity);finite(forces.linear);finite(forces.angular);finite(p.coefficients);finite(env.gravity);
    finite(std::array{p.model_gravity_scale,p.item_gravity_offset,p.item_gravity_multiplier,env.small_velocity_threshold,env.small_velocity_multiplier});interval_ok(dt);
}
void forces_unchecked(RigidState& s,ForceAccumulator& forces,const VelocityStepParameters& p,const GravityEnvironment& env,float dt){
    if(p.flags&2)return;
    auto& v=s.linear_velocity;auto& w=s.angular_velocity;
    const float threshold_squared=env.small_velocity_threshold*env.small_velocity_threshold;
    if(env.attenuate_small_velocities){
        // The native SSE sum evaluates Y before X, including angular velocity.
        if(threshold_squared>((v[1]*v[1]+v[0]*v[0])+v[2]*v[2]))for(auto& x:v)x=x*env.small_velocity_multiplier;
        if(threshold_squared>((w[1]*w[1]+w[0]*w[0])+w[2]*w[2]))for(auto& x:w)x=x*env.small_velocity_multiplier;
    }
    if(p.sleeping){v={0,0,0};w={0,0,0};}
    else{
        const float gravity_scale=(p.model_gravity_scale+p.item_gravity_offset)*p.item_gravity_multiplier;
        const float linear_scale=dt*p.coefficients[3];
        for(std::size_t k=0;k<3;k++){
            forces.linear[k]=gravity_scale*env.gravity[k]+forces.linear[k];
            v[k]=forces.linear[k]*linear_scale+v[k];
            w[k]=(forces.angular[k]*p.coefficients[k])*dt+w[k];
        }
    }
    forces={};
}
}
void integrate_forces(RigidState& s,ForceAccumulator& forces,const VelocityStepParameters& p,const GravityEnvironment& env,float dt){
    validate_forces(s,forces,p,env,dt);auto next=s;auto consumed=forces;
    forces_unchecked(next,consumed,p,env,dt);finite(next.linear_velocity);finite(next.angular_velocity);
    s=next;forces=consumed;
}
RigidWorld::RigidWorld(std::size_t count){
    require(count>0&&count<=1000000,"Rigid world body count out of bounds");states_.resize(count);parameters_.resize(count);auxiliary_.resize(count);
}
void RigidWorld::reset(std::span<const RigidState> states,std::span<const BodyParameters> parameters){
    require(states.size()==states_.size()&&parameters.size()==parameters_.size(),"Rigid reset size mismatch");
    for(std::size_t i=0;i<states.size();i++)validate(states[i],parameters[i]);
    std::copy(states.begin(),states.end(),states_.begin());std::copy(parameters.begin(),parameters.end(),parameters_.begin());
    std::fill(auxiliary_.begin(),auxiliary_.end(),AuxiliaryOutput{});tick_=0;
}
void RigidWorld::step(float dt){
    interval_ok(dt);require(tick_!=std::numeric_limits<std::uint64_t>::max(),"Rigid tick overflow");
    for(std::size_t i=0;i<states_.size();i++)pose_unchecked(states_[i],parameters_[i],auxiliary_[i],dt);
    tick_++;
}
void RigidWorld::step_force_then_pose(float dt,std::span<ForceAccumulator> forces,std::span<const VelocityStepParameters> parameters,const GravityEnvironment& env){
    interval_ok(dt);require(tick_!=std::numeric_limits<std::uint64_t>::max(),"Rigid tick overflow");
    require(forces.size()==states_.size()&&parameters.size()==states_.size(),"Force step size mismatch");
    auto next_states=states_;auto next_auxiliary=auxiliary_;std::vector<ForceAccumulator> next_forces(forces.begin(),forces.end());
    for(std::size_t i=0;i<states_.size();i++){
        validate(next_states[i],parameters_[i]);validate_forces(next_states[i],next_forces[i],parameters[i],env,dt);
        forces_unchecked(next_states[i],next_forces[i],parameters[i],env,dt);
        finite(next_states[i].linear_velocity);finite(next_states[i].angular_velocity);
        pose_unchecked(next_states[i],parameters_[i],next_auxiliary[i],dt);validate(next_states[i],parameters_[i]);
    }
    states_.swap(next_states);auxiliary_.swap(next_auxiliary);std::copy(next_forces.begin(),next_forces.end(),forces.begin());
    tick_++;
}
RigidSnapshot RigidWorld::snapshot()const{return {tick_,states_,parameters_,auxiliary_};}
void RigidWorld::restore(const RigidSnapshot& state){
    require(state.states.size()==states_.size()&&state.parameters.size()==parameters_.size()&&state.auxiliary.size()==auxiliary_.size(),"Rigid snapshot size mismatch");
    for(std::size_t i=0;i<states_.size();i++){validate(state.states[i],state.parameters[i]);finite(state.auxiliary[i]);}
    std::copy(state.states.begin(),state.states.end(),states_.begin());std::copy(state.parameters.begin(),state.parameters.end(),parameters_.begin());
    std::copy(state.auxiliary.begin(),state.auxiliary.end(),auxiliary_.begin());tick_=state.tick;
}
}
