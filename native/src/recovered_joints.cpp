#include "tm2020/recovered_joints.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
using V=std::array<float,3>;
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
template<std::size_t N>void valid(const std::array<float,N>& a){for(float x:a)require(std::isfinite(x)&&std::abs(x)<=1e6f,"Joint input/output exceeds finite domain");}
void scalar(float x){valid(std::array{x});}
void setup(std::span<const RigidState> s,std::span<const VelocityCoefficients> c,std::size_t count){
    require(s.size()==c.size()&&s.size()<=1000000&&count<=1000000,"Joint batch count exceeds domain");
    for(std::size_t j=0;j<s.size();j++){valid(s[j].position);valid(s[j].linear_velocity);valid(s[j].angular_velocity);valid(c[j]);}
}
void outputs(std::span<const RigidState> s){for(const auto& b:s){valid(b.linear_velocity);valid(b.angular_velocity);}}
V subtract(const V& a,const V& b){return {a[0]-b[0],a[1]-b[1],a[2]-b[2]};}
float dot(const V& a,const V& b){return (a[1]*b[1]+a[0]*b[0])+a[2]*b[2];}
V point_velocity(const RigidState& s,const V& point){
    const auto r=subtract(point,s.position);const auto& w=s.angular_velocity;return {(w[1]*r[2]-w[2]*r[1])+s.linear_velocity[0],(w[2]*r[0]-w[0]*r[2])+s.linear_velocity[1],(w[0]*r[1]-w[1]*r[0])+s.linear_velocity[2]};
}
void apply_point(RigidState& s,const VelocityCoefficients& c,const V& point,const V& direction,float delta){
    const V impulse{delta*direction[0],delta*direction[1],delta*direction[2]};
    s.linear_velocity[1]=impulse[1]*c[3]+s.linear_velocity[1];s.linear_velocity[0]=c[3]*impulse[0]+s.linear_velocity[0];s.linear_velocity[2]=impulse[2]*c[3]+s.linear_velocity[2];
    const auto r=subtract(point,s.position);
    s.angular_velocity[0]=(r[1]*impulse[2]-r[2]*impulse[1])*c[0]+s.angular_velocity[0];
    s.angular_velocity[2]=(r[0]*impulse[1]-r[1]*impulse[0])*c[2]+s.angular_velocity[2];
    s.angular_velocity[1]=(r[2]*impulse[0]-r[0]*impulse[2])*c[1]+s.angular_velocity[1];
}
}
float solve_point_constraints(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<PointConstraint> constraints){
    setup(states,coefficients,constraints.size());for(const auto& c:constraints){
        require(c.body_a<states.size()&&(c.body_b==fixed_constraint_body||c.body_b<states.size()),"Invalid point constraint body");
        valid(c.world_point_a);valid(c.world_point_b);valid(c.direction);valid(std::array{c.bias,c.softness,c.effective_coefficient,c.accumulated_impulse});
    }
    auto next=std::vector<RigidState>(states.begin(),states.end());auto cs=std::vector<PointConstraint>(constraints.begin(),constraints.end());float maximum=0;
    for(auto& c:cs){
        V relative=point_velocity(next[c.body_a],c.world_point_a);if(c.body_b!=fixed_constraint_body)relative=subtract(relative,point_velocity(next[c.body_b],c.world_point_b));
        const float old=c.accumulated_impulse;const float change=(-((dot(relative,c.direction)+c.bias)+old*c.softness))*c.effective_coefficient;
        const float candidate=change+old;const float updated=c.softness==0?(candidate>=0?candidate:0.f):candidate;const float delta=updated-old;
        apply_point(next[c.body_a],coefficients[c.body_a],c.world_point_a,c.direction,delta);
        if(c.body_b!=fixed_constraint_body)apply_point(next[c.body_b],coefficients[c.body_b],c.world_point_b,c.direction,-delta);
        c.accumulated_impulse=updated;scalar(updated);maximum=std::max(maximum,std::abs(delta));
    }
    outputs(next);std::copy(next.begin(),next.end(),states.begin());std::copy(cs.begin(),cs.end(),constraints.begin());return maximum;
}
float solve_angular_constraints(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<AngularConstraint> constraints){
    setup(states,coefficients,constraints.size());for(const auto& c:constraints){
        require((c.body_a==fixed_constraint_body||c.body_a<states.size())&&(c.body_b==fixed_constraint_body||c.body_b<states.size()),"Invalid angular constraint body");valid(c.direction);valid(std::array{c.bias,c.softness,c.effective_coefficient,c.accumulated_impulse});
    }
    auto next=std::vector<RigidState>(states.begin(),states.end());auto cs=std::vector<AngularConstraint>(constraints.begin(),constraints.end());float maximum=0;
    for(auto& c:cs){
        V relative{};if(c.body_a!=fixed_constraint_body)relative=next[c.body_a].angular_velocity;if(c.body_b!=fixed_constraint_body)relative=subtract(relative,next[c.body_b].angular_velocity);
        const float old=c.accumulated_impulse;const float change=(-((dot(relative,c.direction)+c.bias)+old*c.softness))*c.effective_coefficient;
        const float updated=change+old,delta=updated-old;
        const auto apply=[&](std::uint32_t body,float impulse){if(body!=fixed_constraint_body){const float scaled=impulse*coefficients[body][3];for(std::size_t k=0;k<3;k++)next[body].angular_velocity[k]=scaled*c.direction[k]+next[body].angular_velocity[k];}};
        apply(c.body_a,delta);apply(c.body_b,-delta);c.accumulated_impulse=updated;scalar(updated);maximum=std::max(maximum,std::abs(delta));
    }
    outputs(next);std::copy(next.begin(),next.end(),states.begin());std::copy(cs.begin(),cs.end(),constraints.begin());return maximum;
}
void solve_angular_couplings(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<const AngularCouplingConstraint> constraints){
    setup(states,coefficients,constraints.size());for(const auto& c:constraints){
        require(c.body_a<states.size()&&c.body_b<states.size(),"Invalid angular coupling body");valid(c.axis_a);valid(c.axis_b);valid(c.coefficient_weights_a);valid(c.coefficient_weights_b);scalar(c.ratio);
    }
    auto next=std::vector<RigidState>(states.begin(),states.end());
    for(const auto& c:constraints){
        float a=dot(next[c.body_a].angular_velocity,c.axis_a),b=dot(next[c.body_b].angular_velocity,c.axis_b);
        const float projected=(-c.ratio)*a,error=projected-b;const float threshold=std::max(1.f,std::max(std::abs(projected),std::abs(b)))*.001f;
        if(threshold<std::abs(error)){
            const auto weight=[&](std::uint32_t body,const V& weights){return std::abs((coefficients[body][0]*weights[0]+coefficients[body][1]*weights[1])+coefficients[body][2]*weights[2]);};
            const float da=weight(c.body_a,c.coefficient_weights_a),db=weight(c.body_b,c.coefficient_weights_b);
            require(da>0&&db>0,"Singular angular coupling weights");const float ia=1.f/da,ib=1.f/db,denominator=(-c.ratio)*ib-ia;
            require(std::isfinite(denominator)&&denominator!=0,"Singular angular coupling ratio");const float correction=error/denominator;
            b=b-correction*ia;a=a-correction*ib;
            for(std::size_t k=0;k<3;k++)next[c.body_a].angular_velocity[k]=c.axis_a[k]*a;
            for(std::size_t k=0;k<3;k++)next[c.body_b].angular_velocity[k]=b*c.axis_b[k];
        }
    }
    outputs(next);std::copy(next.begin(),next.end(),states.begin());
}
}
