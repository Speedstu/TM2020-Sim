#include "tm2020/recovered_resistance.hpp"
#include "tm2020/recovered_joint_position.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void bounded(float x){require(std::isfinite(x)&&std::abs(x)<=1e6f,"Vehicle resistance exceeds finite domain");}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)bounded(x);}
}
void apply_local_torque(ForceAccumulator& f,const RigidState& s,const std::array<float,3>& t){
 bounded(f.linear);bounded(f.angular);bounded(s.rotation);bounded(t);auto next=f;
 const auto& r=s.rotation;const std::array<float,3> world{(t[1]*r[1]+t[0]*r[0])+t[2]*r[2],(t[0]*r[3]+t[1]*r[4])+t[2]*r[5],(t[1]*r[7]+t[0]*r[6])+t[2]*r[8]};for(std::size_t k=0;k<3;k++)next.angular[k]=world[k]+next.angular[k];bounded(next.angular);f=next;
}
void apply_vehicle_resistance(ForceAccumulator& accumulator,VehicleResistanceState& input,const RigidState& pose,const std::array<float,3>& v,const VehicleResistanceParameters& c,std::uint32_t tick,float blend){
 bounded(accumulator.linear);bounded(accumulator.angular);bounded(pose.rotation);bounded(pose.quaternion);for(float x:pose.quaternion)require(std::abs(x)<=16,"Resistance quaternion exceeds domain");bounded(pose.angular_velocity);bounded(v);bounded(blend);
 bounded(std::array{input.scalar_98,input.scalar_9c,input.multiplier_1c44,input.curve_input_13a4,input.manager_a5c,input.scalar_1760,c.constant_17a8,c.linear_17ac});
 bool contact=false;for(auto flag:input.wheel_contacts)contact|=flag!=0;
 if(std::uint32_t(c.variant_1790)-4u<2&&input.word_138c&&!contact)return;
 auto forces=accumulator;auto state=input;
 const auto curve=[](const VehicleCurveView& c,float x){return evaluate_curve(c.points,x,c.flags);};
 const bool mode1=((input.state_word_176c&3)==1||(input.state_word_1370&3)==1),mode2=((input.state_word_176c&3)==2||(input.state_word_1370&3)==2);
 const float scalar=input.word_1600?input.scalar_9c:input.scalar_98;
 if(!mode2&&(scalar<1e-5f||mode1)){
  const float q=(v[1]*v[1]+v[0]*v[0])+v[2]*v[2];if(q>1e-10f&&q<3.4028234663852886e38f){
   const float inverse=1.f/std::sqrt(q);std::array<float,3> force{};for(std::size_t k=0;k<3;k++){force[k]=(inverse*v[k])*(-c.constant_17a8);if(!mode1)force[k]=v[k]*(-c.linear_17ac)+force[k];}
   const float parameter=curve(c.curve_9f8,input.curve_input_13a4);float gate=input.manager_a5c*input.scalar_1760;gate=gate<0?0:(gate<1?gate:1);const float scale=(gate*input.multiplier_1c44)*parameter,remaining=1.f-blend;
   for(float& x:force)x=(x*scale)*remaining;apply_local_force(forces,pose,force);
  }
 }
 bool braking=false;std::array<float,3> brake{};
 if(c.variant_1790<4){if(input.word_1408){const float value=-evaluate_curve(c.curve_17b8.points,v[2]*3.6f,1);for(std::size_t k=0;k<3;k++)brake[k]=(value*v[k])*input.multiplier_1c44;braking=true;}}
 else{
  auto timer=input.timer_1410;bool in_time=true;
  if(input.word_1408){timer=tick;state.timer_1410=tick;}else if(tick<timer)in_time=false;
  if(in_time&&tick-timer<c.duration_1bdc){const float speed=std::sqrt((v[0]*v[0]+v[1]*v[1])+v[2]*v[2]);if(speed>1e-5f){const float inverse=1.f/speed,value=-curve(c.curve_17b8,speed*3.6f);for(std::size_t k=0;k<3;k++)brake[k]=((v[k]*inverse)*value)*input.multiplier_1c44;braking=true;}}
 }
 if(braking)apply_local_force(forces,pose,brake);
 if(!contact){auto direction=pose.angular_velocity;const float squared=(direction[1]*direction[1]+direction[0]*direction[0])+direction[2]*direction[2];float speed=0;
  if(squared>1e-10f&&squared<3.4028234663852886e38f){speed=std::sqrt(squared);const float inverse=1.f/speed;for(float& x:direction)x=x*inverse;}
  const float factor=(-curve(c.curve_2060,speed*speed))*speed;for(float& x:direction)x=x*factor;
  const auto& q=pose.quaternion;rotate_vector_quaternion(direction,{q[0],-q[1],-q[2],-q[3]});apply_local_torque(forces,pose,direction);
 }
 accumulator=forces;input=state;
}
}
