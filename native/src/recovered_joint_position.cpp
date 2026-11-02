#include "tm2020/recovered_joint_position.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
using V=std::array<float,3>;using Q=std::array<float,4>;
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
template<std::size_t N>void bounded(const std::array<float,N>& a,float limit=1e6f){for(float x:a)require(std::isfinite(x)&&std::abs(x)<=limit,"Joint position exceeds finite domain");}
void valid_states(std::span<const RigidState> states){require(states.size()<=1000000,"Too many joint position states");for(const auto& s:states){bounded(s.position);bounded(s.rotation);bounded(s.quaternion);}}
float dot(const V& a,const V& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
V sub(const V& a,const V& b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
V transformed(const RigidState& s,const V& p){V out{};for(std::size_t k=0;k<3;k++)out[k]=((p[1]*s.rotation[k*3+1]+p[0]*s.rotation[k*3])+p[2]*s.rotation[k*3+2])+s.position[k];return out;}
void rotate_unchecked(V& v,const Q& q){
 const auto p=v;const float a=(p[2]*q[2]-p[1]*q[3])+p[0]*q[0],b=(p[0]*q[3]-q[1]*p[2])+q[0]*p[1],c=(q[1]*p[1]-p[0]*q[2])+q[0]*p[2];
 const float z=b*q[1]-a*q[2],x=c*q[2]-b*q[3],y=a*q[3]-c*q[1];v={x+x+p[0],y+y+p[1],z+z+p[2]};
}
void projection_unchecked(std::span<RigidState> states,std::span<const ProjectionPositionConstraint> constraints){for(const auto& c:constraints){
 float projection=dot(sub(c.world_point,states[c.body_a].position),c.direction);if(c.body_b!=0xffffffffu)projection=projection-dot(sub(c.world_point,states[c.body_b].position),c.direction);float error=c.projection_limit-projection;
 if(error<0){if(c.body_b!=0xffffffffu)error=error*.5f;for(std::size_t k=0;k<3;k++)states[c.body_a].position[k]=states[c.body_a].position[k]-c.direction[k]*error;if(c.body_b!=0xffffffffu)for(std::size_t k=0;k<3;k++)states[c.body_b].position[k]=error*c.direction[k]+states[c.body_b].position[k];}
}}
void anchored_unchecked(std::span<RigidState> states,std::span<const AnchoredPositionConstraint> constraints){for(const auto& c:constraints){
 V offset{};for(std::size_t k=0;k<3;k++)offset[k]=c.local_a[k]*.949999988079071f;
 float projection=dot(sub(c.world_point,transformed(states[c.body_a],offset)),c.direction);if(c.body_b!=0xffffffffu)projection=projection-dot(sub(c.world_point,transformed(states[c.body_b],c.local_b)),c.direction);float error=c.projection_target-projection;
 if(c.body_b!=0xffffffffu)error=error*.1f;
 for(std::size_t k=0;k<3;k++)states[c.body_a].position[k]=states[c.body_a].position[k]-c.direction[k]*error;
 if(c.body_b!=0xffffffffu)for(std::size_t k=0;k<3;k++)states[c.body_b].position[k]=error*c.direction[k]+states[c.body_b].position[k];
}}
void orientation_unchecked(std::span<RigidState> states,std::span<const QuaternionAxisConstraint> constraints){for(const auto& c:constraints)if(c.body!=0xffffffffu){
 const Q inverse{c.reference[0],-c.reference[1],-c.reference[2],-c.reference[3]},q=states[c.body].quaternion;V axis=c.axis;rotate_unchecked(axis,inverse);
 const float w=inverse[0]*q[0]-((inverse[1]*q[1]+inverse[2]*q[2])+inverse[3]*q[3]);
 const float x=((inverse[0]*q[1]+inverse[1]*q[0])+inverse[2]*q[3])-inverse[3]*q[2],y=((inverse[0]*q[2]+inverse[2]*q[0])+inverse[3]*q[1])-inverse[1]*q[3],z=((inverse[0]*q[3]+inverse[3]*q[0])+inverse[1]*q[2])-inverse[2]*q[1];
 const float projection=(x*axis[0]+y*axis[1])+z*axis[2];
 if(std::abs(projection)>=1e-5f){
  Q out{w,axis[0]*projection,axis[1]*projection,axis[2]*projection};const float squared=((out[0]*out[0]+out[1]*out[1])+out[2]*out[2])+out[3]*out[3],normalization=1.f/std::sqrt(squared);
  if(normalization<=1e-5f||normalization>=3.4028234663852886e38f)out={1,0,0,0};else{for(std::size_t k=1;k<4;k++)out[k]=out[k]*normalization;out[0]=w*normalization;}
  if(projection<0)for(float& f:out)f=f*(-1.f);
  const auto& r=c.reference;
  states[c.body].quaternion={r[0]*out[0]-((r[1]*out[1]+r[2]*out[2])+r[3]*out[3]),((r[1]*out[0]+r[0]*out[1])+r[2]*out[3])-r[3]*out[2],((r[0]*out[2]+r[2]*out[0])+r[3]*out[1])-r[1]*out[3],((r[0]*out[3]+r[3]*out[0])+r[1]*out[2])-r[2]*out[1]};
 }
}}

template<class C,class Check,class Run>void sweep(std::span<RigidState> states,std::span<const C> constraints,Check check,Run run){
    valid_states(states);require(constraints.size()<=1000000,"Too many joint position constraints");for(const auto& c:constraints)check(c);
    auto next=std::vector<RigidState>(states.begin(),states.end());run(next,constraints);valid_states(next);std::copy(next.begin(),next.end(),states.begin());
}
}
void rotate_vector_quaternion(V& vector,const Q& quaternion){bounded(vector);bounded(quaternion,16);auto next=vector;rotate_unchecked(next,quaternion);bounded(next);vector=next;}
void solve_projection_positions(std::span<RigidState> states,std::span<const ProjectionPositionConstraint> constraints){
    sweep(states,constraints,[&](const auto& c){require(c.body_a<states.size()&&(c.body_b==fixed_constraint_body||c.body_b<states.size()),"Invalid projection position body");bounded(c.world_point);bounded(c.direction);bounded(std::array{c.projection_limit});},projection_unchecked);
}
void solve_anchor_positions(std::span<RigidState> states,std::span<const AnchoredPositionConstraint> constraints){
    sweep(states,constraints,[&](const auto& c){require(c.body_a<states.size()&&(c.body_b==fixed_constraint_body||c.body_b<states.size()),"Invalid anchored position body");bounded(c.local_a);bounded(c.local_b);bounded(c.world_point);bounded(c.direction);bounded(std::array{c.projection_target});},anchored_unchecked);
}
void solve_quaternion_axes(std::span<RigidState> states,std::span<const QuaternionAxisConstraint> constraints){
    sweep(states,constraints,[&](const auto& c){require(c.body==fixed_constraint_body||c.body<states.size(),"Invalid quaternion-axis body");bounded(c.axis,16);bounded(c.reference,16);},orientation_unchecked);
}
void solve_position_islands(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<const PositionIsland> islands,std::uint32_t iterations,const PositionParameters& parameters,PositionMathPath math){
    require(states.size()==coefficients.size()&&islands.size()<=1024&&iterations<=128,"Position island scheduler exceeds domain");
    std::size_t total{};for(const auto& i:islands){total+=i.dynamic_orientation.size()+i.static_orientation.size()+i.dynamic_anchors.size()+i.static_anchors.size()+i.dynamic_projection.size()+i.static_projection.size()+i.dynamic_contacts.size()+i.static_contacts.size();require(total<=1000000,"Too many position island constraints");}
    if(!iterations)return;
    auto next=std::vector<RigidState>(states.begin(),states.end());
    for(std::uint32_t iteration=0;iteration<iterations;iteration++)for(const auto& i:islands){
        solve_quaternion_axes(next,i.dynamic_orientation);solve_quaternion_axes(next,i.static_orientation);
        solve_anchor_positions(next,i.dynamic_anchors);solve_anchor_positions(next,i.static_anchors);
        solve_projection_positions(next,i.dynamic_projection);solve_projection_positions(next,i.static_projection);
        solve_dynamic_positions(next,coefficients,i.dynamic_contacts,parameters,math);solve_static_positions(next,coefficients,i.static_contacts,parameters,math);
    }
    std::copy(next.begin(),next.end(),states.begin());
}
}
