#include "tm2020/recovered_steering.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool valid,const char* message){if(!valid)throw std::runtime_error(message);}
int main()try{
    check(std::bit_cast<std::uint32_t>(fast_asin(-0.f))==0,"Native inverse-sine signed-zero result changed");
    check(std::bit_cast<std::uint32_t>(fast_asin(1))==0x3fc90fda,"Native inverse-sine endpoint changed");
    check(std::bit_cast<std::uint32_t>(fast_acos(100000))==0x80000000u,"Out-of-range native inverse-cosine sign lost");
    check(vehicle_steering_angle(0,.5f,{2,0},8,0)==0,"Steering disabled-state gate ignored");
    check(vehicle_steering_angle(0,.5f,{0,0},0,0)==0,"Subthreshold steering denominator changed");
    check(std::abs(vehicle_steering_angle(0,.5f,{2,0},0,0)+.2617994f)<1e-6f,"Recovered steering scale inconsistent");
    const std::array<CurvePoint,1> points{{{0,1}}};SurfaceBlendValues material{};material.word_28=1000;
    SurfaceScalarInput input{};input.wheel_contact_34[0]=1;float scalar=.5f;
    update_surface_scalar(scalar,input,material,{points,0},.01f);check(scalar==.49f,"Surface duration response wrong");
    input.word_138c=1;const auto before=scalar;update_surface_scalar(scalar,input,material,{points,0},.01f);check(scalar==before,"Surface state gate modified scalar");
    input.word_138c=0;bool denied=false;
    try{update_surface_scalar(scalar,input,material,{points,0},0);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&scalar==before,"Invalid recovery interval mutated scalar");
    denied=false;try{fast_asin(std::numeric_limits<float>::infinity());}catch(const std::invalid_argument&){denied=true;}
    check(denied,"Nonfinite inverse-trig input accepted");
    std::cout<<"PASS STEERING_SURFACE endpoints=true signed_zero=true status_gates=true recovery_duration=true transactional=true\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
