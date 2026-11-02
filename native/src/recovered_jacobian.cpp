#include "tm2020/recovered_jacobian.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void scalar(float x){require(std::isfinite(x)&&std::abs(x)<=1e6f,"Jacobian input/output exceeds finite domain");}
template<std::size_t N>void bounded(const std::array<float,N>& v){for(float x:v)scalar(x);}
void validate(const DynamicJacobian& j){
    bounded(j.angular_a);bounded(j.angular_b);bounded(j.weighted_angular_a);bounded(j.weighted_angular_b);
    for(float x:{j.inverse_mass_a,j.inverse_mass_b,j.effective_coefficient,j.target,j.accumulated_impulse})scalar(x);
}
void validate(const DynamicJacobianConstraint& c,std::size_t n){
    require(c.body_a<n&&c.body_b<n,"Dynamic Jacobian body out of range");bounded(c.direction);validate(c.jacobian);
}
void validate(const StaticJacobianConstraint& c,std::size_t n){
    require(c.body<n,"Static Jacobian body out of range");bounded(c.direction);bounded(c.angular);bounded(c.weighted_angular);
    for(float x:{c.inverse_mass,c.effective_coefficient,c.target,c.accumulated_impulse})scalar(x);
}
void states_valid(std::span<const RigidState> s){
    require(s.size()<=1000000,"Too many Jacobian states");
    for(const auto& b:s){bounded(b.linear_velocity);bounded(b.angular_velocity);}
}
// These addition orders are explicit: the original uses (Y+X)+Z.
float dot(const std::array<float,3>& a,const std::array<float,3>& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
std::array<float,3> cross(const std::array<float,3>& r,const std::array<float,3>& n){
    return {r[1]*n[2]-r[2]*n[1],r[2]*n[0]-r[0]*n[2],r[0]*n[1]-r[1]*n[0]};
}
float clamp_native(float candidate,float lo,float hi){
    // MINSS returns its second operand on equal inputs (including opposite zeros).
    return candidate<lo?lo:(candidate<hi?candidate:hi);
}
bool dynamic_one(RigidState& a,RigidState& b,const std::array<float,3>& direction,DynamicJacobian& j,float lo,float hi){
    const std::array relative{a.linear_velocity[0]-b.linear_velocity[0],a.linear_velocity[1]-b.linear_velocity[1],a.linear_velocity[2]-b.linear_velocity[2]};
    const float speed=(dot(relative,direction)+dot(j.angular_a,a.angular_velocity))-dot(j.angular_b,b.angular_velocity);
    const float impulse=clamp_native((speed-j.target)*j.effective_coefficient+j.accumulated_impulse,lo,hi);
    const float delta=impulse-j.accumulated_impulse;j.accumulated_impulse=impulse;
    if(delta==0)return false;
    const float da=delta*j.inverse_mass_a;
    for(std::size_t k=0;k<3;k++)a.linear_velocity[k]=a.linear_velocity[k]-direction[k]*da;
    for(std::size_t k=0;k<3;k++)a.angular_velocity[k]=a.angular_velocity[k]-j.weighted_angular_a[k]*delta;
    const float db=delta*j.inverse_mass_b;
    for(std::size_t k=0;k<3;k++)b.linear_velocity[k]=direction[k]*db+b.linear_velocity[k];
    for(std::size_t k=0;k<3;k++)b.angular_velocity[k]=j.weighted_angular_b[k]*delta+b.angular_velocity[k];
    return true;
}
bool static_one(RigidState& s,StaticJacobianConstraint& c,float lo,float hi){
    const float speed=dot(c.angular,s.angular_velocity)+dot(c.direction,s.linear_velocity);
    const float impulse=clamp_native((speed-c.target)*c.effective_coefficient+c.accumulated_impulse,lo,hi);
    const float delta=impulse-c.accumulated_impulse;c.accumulated_impulse=impulse;
    if(delta==0)return false;
    const float d=delta*c.inverse_mass;
    for(std::size_t k=0;k<3;k++)s.linear_velocity[k]=s.linear_velocity[k]-c.direction[k]*d;
    for(std::size_t k=0;k<3;k++)s.angular_velocity[k]=s.angular_velocity[k]-c.weighted_angular[k]*delta;
    return true;
}
template<class C,class Validate,class Solve>bool sweep(std::span<RigidState> states,std::span<C> cs,Validate check,Solve solve){
    states_valid(states);require(cs.size()<=1000000,"Too many Jacobian constraints");for(const auto& c:cs)check(c);
    auto next=std::vector<RigidState>(states.begin(),states.end());auto pending=std::vector<C>(cs.begin(),cs.end());bool changed=false;
    for(auto& c:pending)changed=solve(next,c)||changed;
    states_valid(next);for(const auto& c:pending)check(c);
    std::copy(next.begin(),next.end(),states.begin());std::copy(pending.begin(),pending.end(),cs.begin());return changed;
}
}
void prepare_dynamic_jacobian(DynamicJacobian& out,const VelocityCoefficients& a,const VelocityCoefficients& b,
    const std::array<float,3>& ra,const std::array<float,3>& rb,const std::array<float,3>& n,float target){
    bounded(a);bounded(b);bounded(ra);bounded(rb);bounded(n);scalar(target);DynamicJacobian j=out;
    j.angular_a=cross(ra,n);j.angular_b=cross(rb,n);
    for(std::size_t k=0;k<3;k++){j.weighted_angular_a[k]=j.angular_a[k]*a[k];j.weighted_angular_b[k]=j.angular_b[k]*b[k];}
    j.inverse_mass_a=a[3];j.inverse_mass_b=b[3];
    const float denom_a=dot(j.weighted_angular_a,j.angular_a)+a[3];
    const float denom_b=dot(j.weighted_angular_b,j.angular_b)+b[3];
    const float denominator=denom_a+denom_b;
    require(denominator>0&&std::isfinite(denominator),"Invalid Jacobian effective denominator");
    j.effective_coefficient=1.f/denominator;j.target=target;validate(j);out=j;
}
bool solve_dynamic_unilateral(std::span<RigidState> s,std::span<DynamicJacobianConstraint> cs){
    return sweep(s,cs,[&](const auto& c){validate(c,s.size());},[](auto& states,auto& c){
        return dynamic_one(states[c.body_a],states[c.body_b],c.direction,c.jacobian,0,std::numeric_limits<float>::max());});
}
bool solve_static_unilateral(std::span<RigidState> s,std::span<StaticJacobianConstraint> cs){
    return sweep(s,cs,[&](const auto& c){validate(c,s.size());},[](auto& states,auto& c){
        return static_one(states[c.body],c,0,std::numeric_limits<float>::max());});
}
bool solve_dynamic_friction(std::span<RigidState> s,std::span<DynamicFrictionConstraint> cs,std::span<const DynamicJacobianConstraint> normals){
    return sweep(s,cs,[&](const auto& c){validate(c.constraint,s.size());scalar(c.friction);
        require(c.normal_index<normals.size()&&c.friction>=0,"Invalid dynamic friction reference");
        const float impulse=normals[c.normal_index].jacobian.accumulated_impulse;scalar(impulse);require(impulse>=0,"Negative normal impulse");scalar(impulse*c.friction);
    },[&](auto& states,auto& c){auto& d=c.constraint;const float limit=normals[c.normal_index].jacobian.accumulated_impulse*c.friction;
        return dynamic_one(states[d.body_a],states[d.body_b],d.direction,d.jacobian,-limit,limit);});
}
bool solve_static_friction(std::span<RigidState> s,std::span<StaticFrictionConstraint> cs,std::span<const StaticJacobianConstraint> normals){
    return sweep(s,cs,[&](const auto& c){validate(c.constraint,s.size());scalar(c.friction);
        require(c.normal_index<normals.size()&&c.friction>=0,"Invalid static friction reference");
        const float impulse=normals[c.normal_index].accumulated_impulse;scalar(impulse);require(impulse>=0,"Negative normal impulse");scalar(impulse*c.friction);
    },[&](auto& states,auto& c){const float limit=normals[c.normal_index].accumulated_impulse*c.friction;
        return static_one(states[c.constraint.body],c.constraint,-limit,limit);});
}
namespace {
std::array<float,3> sub(const std::array<float,3>& a,const std::array<float,3>& b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
std::array<float,3> point_velocity(const RigidState& s,const std::array<float,3>& r){
    auto v=cross(s.angular_velocity,r);for(std::size_t k=0;k<3;k++)v[k]=v[k]+s.linear_velocity[k];return v;
}
std::array<float,3> translated(const std::array<float,3>& p,const std::array<float,3>& n,float scale){
    return {n[0]*scale+p[0],n[1]*scale+p[1],n[2]*scale+p[2]};
}
std::array<float,3> local_point(const RigidState& s,const std::array<float,3>& p){
    const auto r=sub(p,s.position);std::array<float,3> out{};
    for(std::size_t k=0;k<3;k++)out[k]=(r[1]*s.rotation[3+k]+r[0]*s.rotation[k])+r[2]*s.rotation[6+k];
    return out;
}
std::array<float,3> tangent(const std::array<float,3>& n){
    const float z2=n[2]*n[2];
    if(std::abs(n[0])>std::abs(n[1])){
        const float inverse=1.f/std::sqrt(n[0]*n[0]+z2);
        return {inverse*n[2],inverse*0.f,(-n[0])*inverse};
    }
    const float inverse=1.f/std::sqrt(n[1]*n[1]+z2);
    return {inverse*0.f,inverse*n[2],(-n[1])*inverse};
}
float target_velocity(const ContactPoint& c,float interval,float threshold,float speed){
    const float separation_velocity=(-c.separation)/interval;
    const float penetration=separation_velocity>=0?separation_velocity:0.f;
    if(c.restitution>0&&(-threshold)>speed){
        if((-penetration)>speed)return c.restitution*speed;
        return 0;
    }
    return penetration;
}
void contact_inputs(const ContactPoint& c,std::span<const RigidState> s,std::span<const VelocityCoefficients> coefficients,float interval,float threshold,bool dynamic){
    states_valid(s);require(s.size()==coefficients.size(),"Contact coefficient count mismatch");
    require(c.body_a<s.size()&&(!dynamic||c.body_b<s.size()),"Contact body out of range");
    bounded(c.world_point);bounded(c.normal);scalar(c.separation);scalar(c.friction);scalar(c.restitution);scalar(threshold);
    require(c.friction>=0&&threshold>=0&&interval>0&&interval<=1,"Invalid contact preparation parameters");
    for(const auto& b:s){bounded(b.position);bounded(b.rotation);}
    for(const auto& coeff:coefficients){bounded(coeff);for(float x:coeff)require(x>=0,"Negative velocity coefficient");}
    require(c.normal[0]!=0||c.normal[1]!=0||c.normal[2]!=0,"Zero contact normal");
}
StaticJacobianConstraint static_jacobian(std::uint32_t body,const std::array<float,3>& n,const std::array<float,3>& offset,const VelocityCoefficients& coeff,float target){
    StaticJacobianConstraint out{};out.body=body;out.direction=n;out.angular=cross(offset,n);out.inverse_mass=coeff[3];out.target=target;
    for(std::size_t k=0;k<3;k++)out.weighted_angular[k]=out.angular[k]*coeff[k];
    const float denominator=dot(out.weighted_angular,out.angular)+coeff[3];
    require(denominator>0&&std::isfinite(denominator),"Singular static contact");out.effective_coefficient=1.f/denominator;return out;
}
}
PreparedStaticContact prepare_static_contact(const ContactPoint& c,std::span<const RigidState> states,
    std::span<const VelocityCoefficients> coeff,float interval,float threshold,std::uint32_t normal_index){
    contact_inputs(c,states,coeff,interval,threshold,false);const auto& s=states[c.body_a];
    const std::array n{-c.normal[0],-c.normal[1],-c.normal[2]};
    PreparedStaticContact out{};out.position.body=c.body_a;out.position.normal=n;
    out.position.local_point=local_point(s,translated(c.world_point,n,c.separation*.5f));
    out.position.target_point=translated(c.world_point,n,c.separation*(-.5f));
    const auto r=sub(c.world_point,s.position),velocity=point_velocity(s,r);
    const std::array negative{-velocity[0],-velocity[1],-velocity[2]};
    out.normal=static_jacobian(c.body_a,n,r,coeff[c.body_a],target_velocity(c,interval,threshold,dot(negative,n)));
    if(c.friction>0){
        const auto t=tangent(n);const std::array<std::array<float,3>,2> axes{t,cross(n,t)};out.friction_count=2;
        for(std::size_t k=0;k<2;k++)out.friction[k]={static_jacobian(c.body_a,axes[k],r,coeff[c.body_a],0),normal_index,c.friction};
    }
    bounded(out.position.local_point);bounded(out.position.target_point);validate(out.normal,states.size());
    for(std::size_t k=0;k<out.friction_count;k++)validate(out.friction[k].constraint,states.size());
    return out;
}
PreparedDynamicContact prepare_dynamic_contact(const ContactPoint& c,std::span<const RigidState> states,
    std::span<const VelocityCoefficients> coeff,float interval,float threshold,std::uint32_t normal_index){
    contact_inputs(c,states,coeff,interval,threshold,true);const auto& a=states[c.body_a];const auto& b=states[c.body_b];
    const std::array n{-c.normal[0],-c.normal[1],-c.normal[2]};PreparedDynamicContact out{};
    out.position={c.body_a,c.body_b,local_point(a,translated(c.world_point,n,c.separation*.5f)),local_point(b,translated(c.world_point,n,c.separation*(-.5f))),n};
    const auto ra=sub(c.world_point,a.position),rb=sub(c.world_point,b.position);
    const auto va=point_velocity(a,ra),vb=point_velocity(b,rb);
    const float target=target_velocity(c,interval,threshold,dot(sub(vb,va),n));
    out.normal.body_a=c.body_a;out.normal.body_b=c.body_b;out.normal.direction=n;
    prepare_dynamic_jacobian(out.normal.jacobian,coeff[c.body_a],coeff[c.body_b],ra,rb,n,target);
    if(c.friction>0){
        const auto t=tangent(n);const std::array<std::array<float,3>,2> axes{t,cross(n,t)};out.friction_count=2;
        for(std::size_t k=0;k<2;k++){
            auto& f=out.friction[k];f.constraint.body_a=c.body_a;f.constraint.body_b=c.body_b;f.constraint.direction=axes[k];f.normal_index=normal_index;f.friction=c.friction;
            prepare_dynamic_jacobian(f.constraint.jacobian,coeff[c.body_a],coeff[c.body_b],ra,rb,axes[k],0);
        }
    }
    bounded(out.position.local_a);bounded(out.position.local_b);validate(out.normal,states.size());return out;
}
}
