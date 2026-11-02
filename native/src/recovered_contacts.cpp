#include "tm2020/recovered_contacts.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* message){if(!b)throw std::invalid_argument(message);}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Contact kernel input exceeds finite domain");}
void prepare(std::span<const RigidState> s,std::span<const VelocityCoefficients> c){
    require(s.size()==c.size()&&s.size()<=1000000,"Contact state/coefficient count mismatch");
    for(std::size_t i=0;i<s.size();i++){bounded(s[i].position);bounded(s[i].linear_velocity);bounded(s[i].angular_velocity);bounded(c[i]);}
}
template<class C>void constraint(const C& c){bounded(c.world_point);bounded(c.normal);bounded(std::array{c.bias,c.effective_coefficient,c.accumulated_impulse});}
auto offset(const std::array<float,3>& p,const RigidState& s){return std::array{p[0]-s.position[0],p[1]-s.position[1],p[2]-s.position[2]};}
auto point_velocity(const RigidState& s,const std::array<float,3>& r){
    const auto& w=s.angular_velocity;const auto& v=s.linear_velocity;
    return std::array{(w[1]*r[2]-w[2]*r[1])+v[0],(w[2]*r[0]-w[0]*r[2])+v[1],(w[0]*r[1]-w[1]*r[0])+v[2]};
}
void apply(RigidState& s,const VelocityCoefficients& c,const std::array<float,3>& r,const std::array<float,3>& impulse){
    for(std::size_t k=0;k<3;k++)s.linear_velocity[k]=impulse[k]*c[3]+s.linear_velocity[k];
    s.angular_velocity[0]=(r[1]*impulse[2]-r[2]*impulse[1])*c[0]+s.angular_velocity[0];
    s.angular_velocity[1]=(r[2]*impulse[0]-r[0]*impulse[2])*c[1]+s.angular_velocity[1];
    s.angular_velocity[2]=(r[0]*impulse[1]-r[1]*impulse[0])*c[2]+s.angular_velocity[2];
}
float projected_impulse(const std::array<float,3>& relative,const std::array<float,3>& normal,float bias,float effective,float old){
    const float speed=(relative[1]*normal[1]+relative[0]*normal[0])+relative[2]*normal[2];
    const float candidate=(-(speed+bias))*effective+old;
    return candidate>=0?candidate:0.f; // SSE MAXSS(0,candidate): preserve -0.
}
void outputs(std::span<const RigidState> states){for(const auto& s:states){bounded(s.linear_velocity);bounded(s.angular_velocity);}}
}
float solve_dynamic_normals(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<DynamicNormalConstraint> constraints){
    prepare(states,coefficients);require(constraints.size()<=1000000,"Too many constraints");
    for(const auto& c:constraints){constraint(c);require(c.body_a<states.size()&&c.body_b<states.size(),"Dynamic constraint index out of range");}
    auto next=std::vector<RigidState>(states.begin(),states.end());auto cs=std::vector<DynamicNormalConstraint>(constraints.begin(),constraints.end());float maximum=0;
    for(auto& c:cs){
        auto& a=next[c.body_a];auto& b=next[c.body_b];const auto ra=offset(c.world_point,a),rb=offset(c.world_point,b);
        const auto va=point_velocity(a,ra),vb=point_velocity(b,rb);
        const std::array relative{va[0]-vb[0],va[1]-vb[1],va[2]-vb[2]};
        const float impulse=projected_impulse(relative,c.normal,c.bias,c.effective_coefficient,c.accumulated_impulse);
        const float delta=impulse-c.accumulated_impulse;c.accumulated_impulse=impulse;
        const std::array positive{c.normal[0]*delta,c.normal[1]*delta,c.normal[2]*delta};
        const float negative_delta=-delta;const std::array negative{negative_delta*c.normal[0],negative_delta*c.normal[1],negative_delta*c.normal[2]};
        apply(a,coefficients[c.body_a],ra,positive);apply(b,coefficients[c.body_b],rb,negative);
        maximum=std::max(maximum,std::abs(delta));
    }
    outputs(next);for(const auto& c:cs)constraint(c);
    std::copy(next.begin(),next.end(),states.begin());std::copy(cs.begin(),cs.end(),constraints.begin());return maximum;
}
float solve_static_normals(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<StaticNormalConstraint> constraints){
    prepare(states,coefficients);require(constraints.size()<=1000000,"Too many constraints");
    for(const auto& c:constraints){constraint(c);require(c.body<states.size(),"Static constraint index out of range");}
    auto next=std::vector<RigidState>(states.begin(),states.end());auto cs=std::vector<StaticNormalConstraint>(constraints.begin(),constraints.end());float maximum=0;
    for(auto& c:cs){
        auto& a=next[c.body];const auto r=offset(c.world_point,a);const auto v=point_velocity(a,r);
        const float impulse=projected_impulse(v,c.normal,c.bias,c.effective_coefficient,c.accumulated_impulse);
        const float delta=impulse-c.accumulated_impulse;c.accumulated_impulse=impulse;
        const std::array positive{c.normal[0]*delta,c.normal[1]*delta,c.normal[2]*delta};apply(a,coefficients[c.body],r,positive);
        maximum=std::max(maximum,std::abs(delta));
    }
    outputs(next);for(const auto& c:cs)constraint(c);
    std::copy(next.begin(),next.end(),states.begin());std::copy(cs.begin(),cs.end(),constraints.begin());return maximum;
}
float select_pose_fraction(const std::array<float,3>& velocity,float limit,float interval){
    bounded(velocity);bounded(std::array{limit,interval});require(limit>=0&&interval>=0&&interval<=1,"Invalid pose subdivision inputs");
    const float x=velocity[0]*interval,y=velocity[1]*interval,z=velocity[2]*interval;
    const float squared=(x*x+y*y)+z*z;const float limit_squared=limit*limit;
    if(squared<=limit_squared)return interval;
    const float fraction=std::sqrt(limit_squared/squared);
    if(fraction<.1f)return .1f*interval;
    return std::min(fraction,1.f)*interval;
}
bool suspension_mode2(const SuspensionParameters& p,const std::array<SuspensionWheelState,4>& wheels,std::size_t selected,float& force){
    require(selected<4,"Invalid suspension wheel");bounded(std::array{p.stiffness,p.damping,p.rest_length});
    for(const auto& w:wheels)bounded(std::array{w.length,w.speed});
    if(p.require_all_contacts)for(const auto& w:wheels)if(!w.contact)return false;
    if(p.mode!=2||!wheels[selected].contact)return false;
    const auto& w=wheels[selected];const float next=(p.rest_length-w.length)*p.stiffness-w.speed*p.damping;
    bounded(std::array{next});force=next;return true;
}
}
