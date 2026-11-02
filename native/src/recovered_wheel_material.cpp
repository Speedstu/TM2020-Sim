#include "tm2020/recovered_wheel_material.hpp"
#include "tm2020/recovered_joint_position.hpp"
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
using V=std::array<float,3>;
void require(bool b,const char* why){if(!b)throw std::invalid_argument(why);}
void bounded(float x){require(std::isfinite(x)&&std::abs(x)<=1e6f,"Wheel material scalar exceeds finite domain");}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)bounded(x);}
float f(std::uint32_t bits){return std::bit_cast<float>(bits);}
float magnitude(const V& v){return std::sqrt((v[0]*v[0]+v[1]*v[1])+v[2]*v[2]);}
void normalize(V& v,bool fallback){const float q=(v[0]*v[0]+v[1]*v[1])+v[2]*v[2];if(q>f(0x2edbe6ff)&&q<std::numeric_limits<float>::max()){const float k=1.f/std::sqrt(q);for(float& x:v)x=x*k;}else if(fallback)v={0,1,0};}
std::uint32_t kind(std::uint8_t id){const auto relative=std::uint8_t(id-55);if(relative<=9&&((0x227u>>relative)&1))return 1;if(id==62)return 2;if(id<=63&&((0x8001939000000000ull>>id)&1))return 1;return 0;}
float curve(const VehicleCurveView& c,float x){return evaluate_curve(c.points,x,c.flags);}
}
FastSinCos fast_sin_cos(float angle){
 bounded(angle);
 const float scaled=angle*f(0x3e22f983);const float adjusted=angle>=0?scaled+.5f:scaled-.5f;const auto turns=std::int32_t(adjusted);float x=angle-float(turns)*f(0x40c90fdb),sign=1.f;
 if(x>f(0x3fc90fdb)){x=f(0x40490fdb)-x;sign=-1;}else if(x<f(0xbfc90fdb)){x=f(0xc0490fdb)-x;sign=-1;}
 const float z=x*x;float s=f(0x3638b88e)-z*f(0x32cd365b);s=s*z;s=s-f(0x39500bf1);s=s*z;s=s+f(0x3c088886);s=s*z;s=s-f(0x3e2aaaab);s=s*z;s=s+1.f;s=s*x;
 float c=f(0x37cfb4c2)-z*f(0x348bdd11);c=c*z;c=c-f(0x3ab609aa);c=c*z;c=c+f(0x3d2aaaa3);c=c*z;c=c-.5f;c=c*z;c=c+1.f;c=c*sign;return {s,c};
}
void update_direction_factor(float& factor,const std::array<float,4>& q,const V& velocity,float scalar,const DirectionFactorParameters& p,float interval){
 bounded(factor);bounded(q);for(float x:q)require(std::abs(x)<=16,"Direction factor quaternion exceeds domain");bounded(velocity);bounded(scalar);bounded(p.minimum_328);bounded(interval);require(std::abs(interval)<=1&&p.recovery_duration_324>0,"Invalid direction recovery interval/duration");
 V v=velocity;rotate_vector_quaternion(v,{q[0],-q[1],-q[2],-q[3]});const float sq=(v[1]*v[1]+v[0]*v[0])+v[2]*v[2];
 if(sq>f(0x2edbe6ff)&&sq<std::numeric_limits<float>::max()){const float inverse=1.f/std::sqrt(sq);for(float& x:v)x=x*inverse;}
 const float increment=interval/float(p.recovery_duration_324);float value{};
 if(scalar>.1f){float projection=(v[1]*0.f+v[0]*0.f)+v[2];value=std::abs(projection)-.5f;value=value+value;}
 else value=increment+factor;
 const float next=value<p.minimum_328?p.minimum_328:(value<1.f?value:1.f);bounded(next);factor=next;
}
std::array<float,2> vertical_response(const V& velocity,const VerticalResponseParameters& p){
 bounded(velocity);require(p.begin_19e4>=0&&p.begin_19e4<p.end_19e8&&p.end_19e8<=1&&p.begin_19ec>=0&&p.begin_19ec<p.end_19f0&&p.end_19f0<=1,"Vertical response thresholds must increase within [0,1]");
 std::array<float,2> result{1,1};const float squared=(velocity[0]*velocity[0]+velocity[1]*velocity[1])+velocity[2]*velocity[2];
 if(squared>f(0x2edbe6ff)){const float t=std::abs(velocity[1]/std::sqrt(squared));const std::array<float,2> begins{p.begin_19e4,p.begin_19ec},ends{p.end_19e8,p.end_19f0};
 for(std::size_t k=0;k<2;k++)if(t<begins[k])result[k]=0;else if(t<=ends[k])result[k]=1.f-fast_sin_cos(((t-begins[k])/(ends[k]-begins[k]))*f(0x40490fdb)*.5f).cosine;}
 return result;
}
WheelSurfaceBlend blend_wheel_surfaces(const std::array<WheelMaterialContact,4>& wheels,std::span<const WheelSurfaceParameters> materials,const RigidState& state,const V& curve_velocity,float scalar,bool classify,bool remap){
 require(materials.size()<=80,"Wheel surface table exceeds qualified material domain");bounded(state.rotation);bounded(state.quaternion);for(float x:state.quaternion)require(std::abs(x)<=16,"Material quaternion exceeds domain");bounded(state.linear_velocity);bounded(curve_velocity);bounded(scalar);
 for(const auto& w:wheels)if(w.contact_34){bounded(w.normal_44);const std::size_t id=remap&&w.material_40==14?0:w.material_40;require(id<materials.size(),"Wheel surface ID is outside table");const auto& m=materials[id];bounded(m.values_18_3c);bounded(m.values_44_4c);require(m.word_40<=1000000,"Material integer coefficient exceeds bound");}
 WheelSurfaceBlend out;out.values.values_00_24[7]=-1;out.values.values_00_24[8]=-1;out.values.flags_38=1;std::uint32_t count{},nonzero{};
 for(const auto& w:wheels)if(w.contact_34){const std::size_t index=remap&&w.material_40==14?0:w.material_40;const auto& m=materials[index];count++;nonzero+=m.word_40!=0;
  for(std::size_t k=0;k<7;k++)out.values.values_00_24[k]=k==0?out.values.values_00_24[k]+m.values_18_3c[k]:m.values_18_3c[k]+out.values.values_00_24[k];
  for(std::size_t k=7;k<9;k++)if(m.values_18_3c[k]>0){auto& target=out.values.values_00_24[k];target=target<0?m.values_18_3c[k]:target+m.values_18_3c[k];}
  out.values.values_00_24[9]=m.values_18_3c[9]+out.values.values_00_24[9];out.values.word_28+=m.word_40;for(std::size_t k=0;k<3;k++)out.values.values_2c_34[k]=m.values_44_4c[k]+out.values.values_2c_34[k];out.values.flags_38&=m.flags_50;
  for(std::size_t k=0;k<3;k++)out.transformed_normal[k]=k==2?out.transformed_normal[k]+w.normal_44[k]:w.normal_44[k]+out.transformed_normal[k];
  if(classify)out.last_contact_kind=kind(w.material_40);
  out.has_contact=1;
 }
 if(count){const float inverse=1.f/float(count);for(std::size_t k=0;k<10;k++)if(k<7||k==9||out.values.values_00_24[k]>0)out.values.values_00_24[k]=inverse*out.values.values_00_24[k];out.values.word_28=std::uint32_t(std::round(float(out.values.word_28)*inverse));for(float& x:out.values.values_2c_34)x=inverse*x;if(nonzero<3)out.values.word_28=0;
  normalize(out.transformed_normal,true);const auto n=out.transformed_normal;const auto& r=state.rotation;out.transformed_normal={(n[1]*r[1]+n[0]*r[0])+n[2]*r[2],(n[0]*r[3]+n[1]*r[4])+n[2]*r[5],(n[0]*r[6]+n[1]*r[7])+n[2]*r[8]};
 }
 if(out.values.values_00_24[1]>1.5f){const float speed=magnitude(state.linear_velocity)*3.6f;const float blend=speed<90.f?0.f:(speed>120.f?1.f:(speed-90.f)/30.f);out.values.values_00_24[1]=(out.values.values_00_24[1]-1.5f)*blend+1.5f;}
 V forward{0,0,1};rotate_vector_quaternion(forward,state.quaternion);V direction=state.linear_velocity;
 const float squared=(direction[1]*direction[1]+direction[0]*direction[0])+direction[2]*direction[2];if(squared>f(0x2edbe6ff)&&squared<std::numeric_limits<float>::max()){const float inv=1.f/std::sqrt(squared);for(float& x:direction)x=x*inv;}
 const float facing=1.f-((direction[0]*forward[0]+direction[1]*forward[1])+direction[2]*forward[2]);const float speed=curve_velocity[2]*3.6f;
 for(const auto& w:wheels)if(w.contact_34){const auto& m=materials[remap&&w.material_40==14?0:w.material_40];out.curve_response[0]=curve(m.curve_128,speed)+out.curve_response[0];out.curve_response[1]=curve(m.curve_88,speed)+out.curve_response[1];out.curve_response[2]=curve(m.curve_178,scalar)+out.curve_response[2];out.curve_response[3]=curve(m.curve_1c8,facing)+out.curve_response[3];}
 if(count)for(float& x:out.curve_response)x=x/float(count);else out.curve_response={1,1,1,0};bounded(out.values.values_00_24);bounded(out.values.values_2c_34);bounded(out.transformed_normal);bounded(out.curve_response);return out;
}
}
