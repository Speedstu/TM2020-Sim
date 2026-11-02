#include "tm2020/recovered_wheel_material.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b){if(!b)throw std::runtime_error("Wheel material semantic test failed");}
template<class F>void rejects(F f){try{f();}catch(const std::invalid_argument&){return;}throw std::runtime_error("Invalid material input accepted");}
int main()try{
 const auto zero=fast_sin_cos(-0.f);check(std::signbit(zero.sine)&&zero.cosine==1);
 const auto quarter=fast_sin_cos(1.5707963705062866f);check(std::abs(quarter.sine-1)<1e-6f&&std::abs(quarter.cosine)<1e-6f);
 rejects([]{fast_sin_cos(1000001);});
 float factor=.2f;update_direction_factor(factor,{1,0,0,0},{0,0,3},1,{100,.3f},.01f);check(factor==1);
 update_direction_factor(factor,{1,0,0,0},{3,0,0},1,{100,.3f},.01f);check(factor==.3f);
 factor=.2f;update_direction_factor(factor,{1,0,0,0},{0,0,1},0,{2,.1f},.5f);check(factor==.45f);
 rejects([&]{update_direction_factor(factor,{1,0,0,0},{},0,{0,0},.1f);});check(factor==.45f);
 check(vertical_response({0,0,0},{0,1,0,1})==std::array{1.f,1.f});check(vertical_response({1,0,0},{.2f,.8f,.2f,.8f})==std::array{0.f,0.f});
 const auto full=vertical_response({0,1,0},{.2f,.8f,.2f,.8f});check(full==std::array{1.f,1.f});
 const std::array<CurvePoint,1> a{{{0,2}}},b{{{0,3}}},c{{{0,4}}},d{{{0,5}}};
 std::array<WheelSurfaceParameters,80> materials{};for(auto& m:materials){m.values_18_3c.fill(2);m.values_18_3c[7]=-2;m.values_18_3c[8]=0;m.word_40=1;m.flags_50=3;m.curve_128={a,0};m.curve_88={b,0};m.curve_178={c,0};m.curve_1c8={d,0};}
 std::array<WheelMaterialContact,4> wheels{};RigidState state{};
 auto out=blend_wheel_surfaces(wheels,materials,state,{},0,false,false);check(out.curve_response==std::array{1.f,1.f,1.f,0.f}&&!out.has_contact&&out.values.values_00_24[7]==-1&&out.values.flags_38==1);
 wheels[0]={1,55,{0,1,0}};wheels[1]={1,62,{0,1,0}};
 out=blend_wheel_surfaces(wheels,materials,state,{},0,true,false);check(out.last_contact_kind==2&&out.values.word_28==0&&out.values.values_00_24[7]==-1&&out.values.values_00_24[8]==-1);check(out.values.values_00_24[1]==1.5f&&out.curve_response==std::array{2.f,3.f,4.f,5.f});check(out.transformed_normal==std::array{0.f,1.f,0.f});
 wheels[2]={0x80000000u,63,{0,1,0}};state.linear_velocity={0,0,50};out=blend_wheel_surfaces(wheels,materials,state,{},0,true,false);check(out.values.word_28==1&&out.last_contact_kind==1&&out.values.values_00_24[1]==2);
 wheels={};wheels[0]={1,14,{}};materials[0].values_18_3c[0]=7;materials[14].values_18_3c[0]=9;
 check(blend_wheel_surfaces(wheels,materials,state,{},0,false,true).values.values_00_24[0]==7);check(blend_wheel_surfaces(wheels,materials,state,{},0,false,false).values.values_00_24[0]==9);
 wheels[3]={1,80,{}};rejects([&]{blend_wheel_surfaces(wheels,materials,state,{},0,false,false);});
 std::cout<<"PASS WHEEL_MATERIAL independent_curves=true native_integer_and_flags=true last_contact_classification=true material_remap=true sentinel_and_speed_blend=true validated_domains=true full_tire_model=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
