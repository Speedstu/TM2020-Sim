#include "tm2020/recovered_control_guard.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
int main() try {
    NestedControlRecord r;
    r.vector_7c={0,0,10};r.fallback_f4=10;
    check(nested_drive_gate(r)==0,"Equal target must not accelerate");
    r.fallback_f4=std::nextafter(10.f,11.f);
    check(nested_drive_gate(r)==1,"One-ULP target crossing lost");
    r.priority_4e8=-1;
    check(nested_drive_gate(r)==0,"Nonzero signed short must take priority");
    r.priority_4e8=-32768;
    check(select_nested_control_value(r)==-32768.f,"Signed-short minimum changed");
    r={};r.vector_7c={0,0,-10};r.fallback_f4=1;
    r.quaternion_60={0,0,1,0};
    check(nested_drive_gate(r)==0,"Half-turn must reverse the tested component");
    r.quaternion_60={0,0,-1,0};
    check(nested_drive_gate(r)==0,"Quaternion sign changed the rotation");
    r={};GuardedControlScalars s{-0.f,.75f};
    update_control_guard(s,r,0);
    check(std::bit_cast<std::uint32_t>(s.scalar_98)==0x80000000u,"Inactive guard lost signed zero");
    r.flags_4ec=0x404;r.limit_4ea=-10;
    s={.5f,.75f};update_control_guard(s,r,10);
    check(s.scalar_98==.5f && s.scalar_9c==0,"Shared flags or strict limit equality changed");
    s={.5f,.75f};update_control_guard(s,r,std::nextafter(10.f,11.f));
    check(s.scalar_98==0,"Strict upper limit crossing lost");
    r.flags_f0=2;s={.5f,.75f};update_control_guard(s,r,0);
    check(s.scalar_9c==.75f,"Secondary mode must preserve brake scalar");
    const auto before=s;r.fallback_f4=std::numeric_limits<float>::infinity();
    bool rejected=false;try{update_control_guard(s,r,0);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected && s.scalar_98==before.scalar_98 && s.scalar_9c==before.scalar_9c,"Invalid input was not atomic");
    std::cout<<"PASS CONTROL_GUARD geometry=true aliasing=true strict_thresholds=true invalid_atomic=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
