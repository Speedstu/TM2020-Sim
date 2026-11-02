#include "tm2020/recovered_steering.hpp"
#include <bit>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
constexpr float f(std::uint32_t bits){return std::bit_cast<float>(bits);}
void require(bool ok,const char* message){if(!ok)throw std::invalid_argument(message);}
void bounded(float x,float limit=1e6f){require(std::isfinite(x)&&std::abs(x)<=limit,"Steering/surface input exceeds finite domain");}
float inverse_trig_base(float x){
    bounded(x,100000.f);const float a=std::bit_cast<float>(std::bit_cast<std::uint32_t>(x)&0x7fffffffu);
    const float difference=1.f-a,root=std::sqrt(difference>0?difference:0.f);
    float p=f(0x3bda90c5)-a*f(0x3aa57a2c);
    p=p*a-f(0x3c8bfc66);p=p*a+f(0x3cfd10f8);p=p*a-f(0x3d4d8392);
    p=p*a+f(0x3db63a9e);p=p*a-f(0x3e5bbfca);p=p*a+f(0x3fc90fda);
    return root*p;
}
}
float fast_asin(float x){const float value=inverse_trig_base(x);return x<0?value-f(0x3fc90fda):f(0x3fc90fda)-value;}
float fast_acos(float x){const float value=inverse_trig_base(x);return x<0?f(0x40490fda)-value:value;}
float vehicle_steering_angle(float z,float steering,const SteeringAngleParameters& c,std::uint32_t status_a,std::uint32_t status_b){
    for(float x:{z,steering,c.offset_1808,c.speed_slope_180c})bounded(x);
    const float absolute=std::bit_cast<float>(std::bit_cast<std::uint32_t>(z)&0x7fffffffu);
    const float denominator=absolute*c.speed_slope_180c+c.offset_1808;
    const float angle=denominator>=1e-5f?fast_asin(1.f/denominator):0.f;
    if(((status_a|status_b)&8)!=0)return 0.f;
    const float negative=std::bit_cast<float>(std::bit_cast<std::uint32_t>(steering)^0x80000000u);
    return negative*angle;
}
void update_surface_scalar(float& scalar,const SurfaceScalarInput& input,const SurfaceBlendValues& material,VehicleCurveView curve,float interval){
    bounded(scalar);bounded(input.scalar_98);bounded(input.scalar_9c);bounded(material.values_2c_34[0]);
    for(float x:input.velocity)bounded(x,10000.f);
    require(std::isfinite(interval)&&interval>=1e-6f&&interval<=1.f,"Invalid surface recovery interval");
    bool contact=false;for(auto x:input.wheel_contact_34)contact=contact||x!=0;
    if(!contact||input.word_138c)return;
    float decrement=material.word_28?1.f/(static_cast<float>(material.word_28)/(interval*1000.f)):0.f;
    const float z=input.velocity[2];
    if(input.scalar_9c>.1f&&z>1e-5f)decrement=decrement+(material.values_2c_34[0]*interval)*input.scalar_9c;
    else if(input.scalar_98>.1f&&z< -1e-5f)decrement=decrement+(material.values_2c_34[0]*interval)*input.scalar_98;
    const auto& v=input.velocity;const float speed=std::sqrt((v[0]*v[0]+v[1]*v[1])+v[2]*v[2]);
    const float response=evaluate_curve(curve.points,speed*3.6f,curve.flags);
    const float next=scalar-response*decrement;
    scalar=next<0?0.f:(next>=1.f?1.f:next);
}
}
