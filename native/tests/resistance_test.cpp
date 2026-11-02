#include "tm2020/recovered_resistance.hpp"
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b){if(!b)throw std::runtime_error("Vehicle resistance semantic test failed");}
int main()try{
 const std::array<CurvePoint,1> one{{{0,1}}},half{{{0,.5f}}},two{{{0,2}}};
 VehicleResistanceParameters p{0,2,3,10,{one,0},{two,0},{half,0}};
 VehicleResistanceState s{};s.manager_a5c=s.scalar_1760=s.multiplier_1c44=1;
 RigidState pose{};pose.angular_velocity={0,2,0};ForceAccumulator f{};
 apply_vehicle_resistance(f,s,pose,{0,0,10},p,0,0);check(f.linear[2]==-32&&f.angular[1]==-1);
 s.state_word_1370=1;s.wheel_contacts[3]=0x80000000u;f={};apply_vehicle_resistance(f,s,pose,{0,0,10},p,0,0);check(f.linear[2]==-2&&f.angular==std::array{0.f,0.f,0.f});
 p.variant_1790=4;s={};s.word_138c=1;s.word_1408=1;s.timer_1410=7;f={};apply_vehicle_resistance(f,s,pose,{0,0,10},p,99,0);check(s.timer_1410==7&&f.linear==std::array{0.f,0.f,0.f});
 s.word_138c=0;s.state_word_176c=2;s.manager_a5c=s.scalar_1760=s.multiplier_1c44=1;pose.angular_velocity={};f={};apply_vehicle_resistance(f,s,pose,{0,0,10},p,0xffffffffu,0);check(s.timer_1410==0xffffffffu&&f.linear[2]==-2);
 s.word_1408=0;s.timer_1410=100;f={};apply_vehicle_resistance(f,s,pose,{0,0,10},p,99,0);check(f.linear[2]==0);
 s.word_1408=1;s.timer_1410=7;pose.angular_velocity={0,2,0};const std::array<CurvePoint,2> invalid{{{0,1},{0,2}}};p.curve_2060={invalid,0};const auto before=s;f={};bool rejected=false;
 try{apply_vehicle_resistance(f,s,pose,{0,0,10},p,120,0);}catch(const std::invalid_argument&){rejected=true;}
 check(rejected&&s.timer_1410==before.timer_1410&&f.linear==std::array{0.f,0.f,0.f});
 ForceAccumulator torque{};apply_local_torque(torque,{}, {1,2,3});check(torque.linear==std::array{0.f,0.f,0.f}&&torque.angular==std::array{1.f,2.f,3.f});
 std::cout<<"PASS VEHICLE_RESISTANCE constant_linear_force=true airborne_torque=true dual_status_words=true early_skip=true unsigned_timer=true late_failure_transactional=true complete_tire_model=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
