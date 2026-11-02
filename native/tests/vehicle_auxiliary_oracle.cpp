#include "tm2020/recovered_vehicle.hpp"
#include "owned_arithmetic_image.hpp"
#include <cmath>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T,std::size_t N>void put(std::array<std::byte,N>& block,std::size_t offset,const T& value){check(offset+sizeof(T)<=N,"Fixture overflow");std::memcpy(block.data()+offset,&value,sizeof(T));}
int main(int argc,char** argv)try{
 check(argc==3,"Usage: vehicle_auxiliary_oracle original.exe output.json");const std::array<std::array<unsigned,2>,11> ranges{{{0x84da80,0x84de53},{0x845100,0x845108},{0x845210,0x845218},{0x7bdd20,0x7bddc4},{0x7bd4b0,0x7bd522},{0x7bda90,0x7bdc54},{0x7bd310,0x7bd4af},{0x7be690,0x7be6a6},{0x7b9b70,0x7b9bd6},{0x83db50,0x83db72},{0x83db80,0x83dc0b}}};ArithmeticImage image(argv[1],ranges);
 using Run=void(*)(void*,float);const auto original=reinterpret_cast<Run>(image.base+0x84da80);
 std::mt19937_64 rng(0x2026102318);std::uniform_real_distribution<float> u(-1,1);std::size_t changes{};using Center=void(*)(void*,std::uint32_t,const void*);const auto original_center=reinterpret_cast<Center>(image.base+0x7bdd20);
 for(std::size_t n=0;n<20000;n++){
  std::array<std::byte,0x118> root{};std::array<std::byte,0x110> manager{};std::array<std::byte,0x60> model{};std::array<std::byte,0x1c00> vehicle{};std::array<std::byte,0x1f10> config{};std::array<std::byte,0x48> context{};
  RigidState pose{};for(auto& x:pose.rotation)x=u(rng);for(auto& x:pose.position)x=u(rng)*5;
  std::array<float,3> center{},velocity{u(rng)*50,u(rng)*20,6+u(rng)*40};for(auto& x:center)x=u(rng);
  const float a=n%7==0?.1f:std::abs(u(rng)),b=n%5==0?.1f:std::abs(u(rng)),magnitude=n%11==0?1e-5f:u(rng)*20;
  const std::uint32_t sa=rng()%16,sb=rng()%16;const AuxiliaryVehicleForceParameters p{u(rng)*20,std::abs(u(rng)),u(rng)*5,u(rng)*2};
  ForceAccumulator before{};for(auto* v:{&before.linear,&before.angular})for(auto& x:*v)x=u(rng)*5;ForceAccumulator native=before,ported=before;
  if(n%17==0){pose={};center={};before={};native={};ported={};velocity[0]=-0.f;}
  std::array<std::uint32_t,4> index{};auto* mp=model.data();put(root,0x110,manager.data());put(manager,0x10,&mp);put(manager,0x70,&pose);put(manager,0xa0,&native);put(manager,0xb0,index.data());put(model,0x40,center);
  put(context,0,root.data());put(context,8,vehicle.data());put(context,0x28,velocity);put(context,0x40,config.data());put(vehicle,0x10,std::uint32_t(3));put(vehicle,0x98,a);put(vehicle,0x9c,b);put(vehicle,0x176c,sa);put(vehicle,0x1370,sb);
  put(config,0x1efc,p.coefficient_1efc);put(config,0x1f00,p.coefficient_1f00);put(config,0x1f04,p.coefficient_1f04);put(config,0x1f08,p.coefficient_1f08);
  const std::size_t number=n%5;put(vehicle,0x380,std::uint32_t(number));std::array<std::array<std::byte,0x20>,4> wheel_models{};std::array<AuxiliaryWheelForcePoint,4> wheels{};
  for(std::size_t j=0;j<4;j++){for(auto& x:wheels[j].local_point)x=u(rng)*3;wheels[j].flags_70=std::uint32_t(rng()%3);put(wheel_models[j],0x10,wheels[j].local_point);put(vehicle,0x388+j*8,wheel_models[j].data());put(vehicle,0x17f0+j*0xb8,wheels[j].flags_70);}
  original(context.data(),magnitude);apply_auxiliary_vehicle_forces(ported,pose,center,{velocity,a,b,sa,sb},p,std::span(wheels.data(),number),magnitude);
  if(std::memcmp(&native,&ported,sizeof(native))){std::cerr<<"MISMATCH case="<<n<<" v="<<velocity[0]<<','<<velocity[1]<<','<<velocity[2]<<" input="<<magnitude<<" a="<<a<<" b="<<b<<" status="<<sa<<','<<sb<<'\n';for(std::size_t j=0;j<6;j++)std::cerr<<reinterpret_cast<float*>(&native)[j]<<" vs "<<reinterpret_cast<float*>(&ported)[j]<<'\n';throw std::runtime_error("Vehicle force 84da80 candidate mismatch");}
  changes+=std::memcmp(&native,&before,sizeof(native))!=0;
  native=before;ported=before;std::array<float,3> center_force{u(rng)*5,u(rng)*5,u(rng)*5};if(n%23==0)center_force={0,-0.f,0};original_center(manager.data(),3,&center_force);apply_local_force(ported,pose,center_force);check(std::memcmp(&native,&ported,sizeof(native))==0,"Local center force differs from complete original procedure");
 }
 std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_vehicle_auxiliary_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":2,\"bit_exact\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"auxiliary_force_changed_cases\":"<<changes<<",\"wake_queue_disabled\":true,\"completeTireModel\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";report.flush();check(bool(report),"Cannot write auxiliary force oracle report");
 std::cout<<"PASS VEHICLE_AUXILIARY_ORACLE operations=2 cases_each=20000 bit_exact=true changed_cases="<<changes<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
