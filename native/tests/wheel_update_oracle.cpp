#include "tm2020/recovered_vehicle.hpp"
#include "tm2020/recovered_wheel.hpp"
#include "owned_arithmetic_image.hpp"
#include <cmath>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct Curve {std::uint32_t flags{},pad{};const CurvePoint* points{};std::uint32_t count{},capacity{};};
template<class T,std::size_t N>void put(std::array<std::byte,N>& block,std::size_t offset,const T& value){check(offset+sizeof(T)<=N,"Fixture overflow");std::memcpy(block.data()+offset,&value,sizeof(T));}
int main(int argc,char** argv)try{
 check(argc==3,"Usage: wheel_update_oracle original.exe output.json");const std::array<std::array<unsigned,2>,4> ranges{{{0x844130,0x84471f},{0x42bba0,0x42bdee},{0x195cb14,0x195cd53},{0x186d10,0x186d31}}};ArithmeticImage image(argv[1],ranges);
 DWORD protect{};check(VirtualProtect(image.base+0x1faa000,0x1000,PAGE_READWRITE,&protect)!=0,"Cannot configure private data flag");
 using Run=void(*)(void*,void*,void*,void*,float,float);const auto original=reinterpret_cast<Run>(image.base+0x844130);std::mt19937_64 rng(0x2026102320);std::uniform_real_distribution<float> u(-1,1);std::size_t wrapped{},cache_writes{};
 for(std::size_t trial=0;trial<20000;trial++){
  std::array<std::byte,0x1d00> vehicle{};std::array<std::byte,0x1a60> config{};std::array<std::byte,0x750> manager{};std::array<std::byte,0x30> model{};std::array<std::byte,0xb8> wheel{};std::array<std::array<std::byte,0x100>,16> native_materials{};std::array<std::byte*,16> material_pointers{};
  std::array<std::array<CurvePoint,5>,17> points{};std::array<Curve,17> curves{};
  for(std::size_t k=0;k<curves.size();k++){for(std::size_t j=0;j<5;j++)points[k][j]={float(j)*150.f-20.f,u(rng)*40.f};const auto count=std::uint32_t((trial+k)%6);curves[k]={std::array<std::uint32_t,5>{0,1,2,0x10,0x30}[(trial+k)%5],0,points[k].data(),count,5};}
  WheelKinematicParameters p{std::uint32_t(trial%5),.1f+std::abs(u(rng)),u(rng),std::abs(u(rng))*10,std::abs(u(rng))*.8f,u(rng)*50,std::abs(u(rng))*5,trial%2==0,trial%7==0,{std::span(curves[0].points,curves[0].count),curves[0].flags}};std::array<WheelSteeringMaterial,16> materials{};
  for(std::size_t k=0;k<16;k++){materials[k]={std::abs(u(rng))*5,{std::span(curves[k+1].points,curves[k+1].count),curves[k+1].flags}};put(native_materials[k],0x4c,materials[k].angle_rate_4c);put(native_materials[k],0xd8,curves[k+1]);material_pointers[k]=native_materials[k].data();}
  WheelKinematicState s{u(rng),u(rng),u(rng)*.1f,u(rng)*50000,{u(rng),u(rng),u(rng)},u(rng)*3000,u(rng),u(rng),std::uint32_t(trial%4!=0),std::uint8_t(trial%16)};
  if(trial%11==0)s.normal_44={0,-0.f,0};if(trial%13==0)s.spin_rate_1c=0;
  if(trial%23==0){s.phase_78=1608.4954833984375f;s.spin_rate_1c=0;}if(trial%29==0){s.phase_78=-1608.4954833984375f;s.spin_rate_1c=0;}if(trial%31==0){s.phase_78=-0.f;s.spin_rate_1c=-0.f;}if(trial%37==0)s.normal_44={1e-5f,0,0};if(trial%41==0)s.contact_word_34=0x80000000u;
  const float dt=.001f+std::abs(u(rng))*.05f,speed=u(rng)*100,steering=u(rng),a=std::abs(u(rng))*2,b=std::abs(u(rng))*1.5f;const bool flag=trial%5!=0;
  const std::array<float,3> point{u(rng),u(rng),u(rng)};MeshTransform pose;for(auto& x:pose.rotation)x=u(rng);for(auto& x:pose.translation)x=u(rng);auto ported_pose=pose;
  for(auto& x:wheel)x=std::byte(rng()&255);put(wheel,0,s.length);put(wheel,4,s.speed);put(wheel,8,s.pending_compression);put(wheel,0x1c,s.spin_rate_1c);put(wheel,0x34,s.contact_word_34);put(wheel,0x40,s.material_40);put(wheel,0x44,s.normal_44);put(wheel,0x78,s.phase_78);put(wheel,0x7c,s.angle_7c);put(wheel,0x80,s.target_angle_80);auto ported_wheel=wheel;
  put(vehicle,0,manager.data());put(vehicle,0x88,config.data());put(vehicle,0x1430,steering);put(vehicle,0x1c3c,a);put(vehicle,0x1c44,b);put(manager,0x6b8,material_pointers);put(model,4,std::uint32_t(flag));put(model,0x10,point);auto* model_pointer=model.data();
  put(config,0x238,p.suspension_mode_238);put(config,0x244,p.rest_length_244);put(config,0x250,p.pose_offset_250);put(config,0x258,p.relaxation_258);put(config,0xcd4,p.reference_cd4);put(config,0x118c,p.angle_limit_118c);put(config,0x1190,p.angle_rate_1190);put(config,0x1a48,std::uint32_t(p.material_parameters_1a48));put(config,0x19f8,curves[0]);std::uint32_t remap=p.remap_material14_to0;std::memcpy(image.base+0x1faa04c,&remap,4);
  std::array<std::byte,0x30> cache{};std::array<MeshTransform,8> cached_poses{};const std::uint32_t slot=trial%8;put(model,0x28,slot);put(cache,0x28,cached_poses.data());if(trial%2==0)put(vehicle,0x78,cache.data());
  original(vehicle.data(),&model_pointer,wheel.data(),&pose,speed,dt);update_wheel_kinematics(s,ported_pose,{point,flag,steering,a,b,speed},p,materials,dt);
  put(ported_wheel,0,s.length);put(ported_wheel,4,s.speed);put(ported_wheel,8,s.pending_compression);put(ported_wheel,0x44,s.normal_44);put(ported_wheel,0x78,s.phase_78);put(ported_wheel,0x7c,s.angle_7c);put(ported_wheel,0x80,s.target_angle_80);
  if(wheel!=ported_wheel||std::memcmp(&pose,&ported_pose,sizeof(pose))){std::cerr<<"MISMATCH trial="<<trial<<" mode="<<p.suspension_mode_238<<" material="<<p.material_parameters_1a48<<" flag="<<flag<<" state="<<(wheel!=ported_wheel)<<" pose="<<(std::memcmp(&pose,&ported_pose,sizeof(pose))!=0)<<'\n';for(std::size_t j=0;j<0xb8;j++)if(wheel[j]!=ported_wheel[j])std::cerr<<"byte "<<j<<" native="<<std::to_integer<unsigned>(wheel[j])<<" port="<<std::to_integer<unsigned>(ported_wheel[j])<<'\n';for(std::size_t j=0;j<12;j++)if(std::memcmp(reinterpret_cast<float*>(&pose)+j,reinterpret_cast<float*>(&ported_pose)+j,4))std::cerr<<"pose "<<j<<" native="<<std::hexfloat<<reinterpret_cast<float*>(&pose)[j]<<" port="<<reinterpret_cast<float*>(&ported_pose)[j]<<std::defaultfloat<<'\n';throw std::runtime_error("Wheel update candidate differs");}
  if(trial%2==0){check(std::memcmp(&cached_poses[slot],&pose,sizeof(pose))==0,"Native render-cache copy differs");cache_writes++;}wrapped+=s.phase_78>=0&&s.phase_78<1608.4954833984375f;
 }
 std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_wheel_update_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":1,\"bit_exact\":true,\"entry_rva\":\"0x844130\",\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"phase_in_native_range_cases\":"<<wrapped<<",\"original_render_cache_copies_verified\":"<<cache_writes<<",\"phase_period\":1608.4954833984375,\"suspension_modes\":[0,1,2,3,4],\"material14_remap_qualified\":true,\"global_curve_count_gate_qualified\":true,\"game_process_accessed\":false,\"complete_physics\":false}\n";report.flush();check(bool(report),"Cannot write wheel update oracle report");
 std::cout<<"PASS WHEEL_UPDATE_ORACLE operations=1 cases_each=20000 full_native_function=true phase_in_range="<<wrapped<<" cache_copies="<<cache_writes<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
