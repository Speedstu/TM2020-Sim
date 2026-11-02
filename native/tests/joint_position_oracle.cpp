#include "tm2020/recovered_joint_position.hpp"
#include "owned_arithmetic_image.hpp"
#include <cmath>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
using V=std::array<float,3>;using Q=std::array<float,4>;
template<class T>struct Span{T* data;std::uint32_t count;std::uint32_t reserved{};};
template<class T>void same(const T& a,const T& b,std::size_t n,const char* field){if(std::memcmp(&a,&b,sizeof(T))==0)return;const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);std::size_t at{};while(at<sizeof(T)&&x[at]==y[at])++at;std::cerr<<"MISMATCH case="<<n<<" field="<<field<<" byte="<<at<<'\n';throw std::runtime_error("Joint pose candidate differs");}
int main(int argc,char** argv)try{
 check(argc==3,"Usage: joint_position_oracle original.exe report.json");const std::array<std::array<unsigned,2>,3> ranges{{{0x7f6110,0x7f679e},{0x7f6a50,0x7f6eb6},{0x1955c0,0x1956e0}}};ArithmeticImage image(argv[1],ranges);
 using Plain=void(*)(void*,const void*);using Anchor=void(*)(void*,void*,const void*);using Rotate=void(*)(void*,const void*);
 const auto native_simple=reinterpret_cast<Plain>(image.base+0x7f63f0),native_orientation=reinterpret_cast<Plain>(image.base+0x7f6a50);const auto native_anchor=reinterpret_cast<Anchor>(image.base+0x7f6590);const auto native_rotate=reinterpret_cast<Rotate>(image.base+0x1955c0);
 std::mt19937_64 rng(0x2026102322);std::uniform_real_distribution<float> u(-1,1);const auto v=[&](float scale=1.f){return V{u(rng)*scale,u(rng)*scale,u(rng)*scale};};
 for(std::size_t n=0;n<20000;n++){
  std::array<RigidState,3> initial{};for(auto& s:initial){s.position=v(3);s.linear_velocity=v(2);s.angular_velocity=v();for(float& x:s.quaternion)x=u(rng);for(float& x:s.rotation)x=u(rng);if(n%23==0)for(float& x:s.quaternion)x=x*1e6f;}
  std::array<ProjectionPositionConstraint,4> sc{};std::array<AnchoredPositionConstraint,4> ac{};std::array<QuaternionAxisConstraint,4> oc{};
  for(std::size_t j=0;j<4;j++){const std::uint32_t a=j%3,b=n%7==0?0xffffffffu:n%17==0?a:(j+1)%3;sc[j]={a,b,u(rng),v(2),v()};ac[j]={a,b,v(2),v(2),u(rng),v(2),v()};oc[j]={n%31==0?0xffffffffu:a,0,v(),0,{u(rng),u(rng),u(rng),u(rng)}};if(n%13==0)oc[j].axis={0,-0.f,0};if(n%19==0)oc[j].reference={1,0,0,0};}
  const std::uint32_t count=n%29==0?0:4;Span<ProjectionPositionConstraint> ss{sc.data(),count};Span<AnchoredPositionConstraint> as{ac.data(),count};Span<QuaternionAxisConstraint> os{oc.data(),count};auto ns=initial,ps=initial;
  native_simple(ns.data(),&ss);solve_projection_positions(ps,std::span(sc.data(),count));same(ns,ps,n,"simple positions");ns=initial;ps=initial;native_anchor(nullptr,ns.data(),&as);solve_anchor_positions(ps,std::span(ac.data(),count));same(ns,ps,n,"anchored positions");ns=initial;ps=initial;native_orientation(ns.data(),&os);solve_quaternion_axes(ps,std::span(oc.data(),count));same(ns,ps,n,"quaternion projection");
  V rotated=v(3),ported=rotated;Q reference{u(rng),u(rng),u(rng),u(rng)};native_rotate(&rotated,&reference);rotate_vector_quaternion(ported,reference);same(rotated,ported,n,"quaternion vector");
 }
 std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_joint_position_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":4,\"bit_exact\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"rotation_matrix_preservation_compared\":true,\"fixed_and_aliased_bodies_qualified\":true,\"large_quaternion_fallback_cases_injected\":true,\"game_process_accessed\":false,\"complete_physics\":false}\n";report.flush();check(bool(report),"Cannot write joint position report");
 std::cout<<"PASS JOINT_POSITION_ORACLE operations=4 cases_each=20000 bit_exact=true full_functions=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
