// Executes ONLY three SHA-pinned pure arithmetic routines in this owned test
// process. No game process, loader entry, imports, startup or patch is invoked.
#include "tm2020/recovered_rigid.hpp"
#include "tm2020/read_only_live.hpp"
#include "owned_arithmetic_image.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <bit>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T>void same(const T& a,const T& b,std::size_t trial,const char* label){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);
    std::size_t offset=0;while(offset<sizeof(T)&&x[offset]==y[offset])offset++;
    std::cerr<<"MISMATCH trial="<<trial<<" field="<<label<<" byte="<<offset<<" expected="<<unsigned(x[offset])<<" actual="<<unsigned(y[offset])<<'\n';
    throw std::runtime_error("Recovered kernel differs from original instructions");
}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: recovered_oracle original-Trackmania.exe report.json");const std::array<std::array<unsigned,2>,4> ranges{{{0x7f4d40,0x7f4f06},{0x194de0,0x194fe2},{0x1886d0,0x188800},{0x805890,0x8058cf}}};ArithmeticImage image(argv[1],ranges);
    using PoseFn=void(*)(const void*,void*,void*,std::uint32_t,float);
    using QuatFn=void(*)(void*,const void*,float);
    using MatrixFn=void(*)(void*,const void*);
    const auto pose=reinterpret_cast<PoseFn>(image.base+integrate_pose_rva);
    const auto quat=reinterpret_cast<QuatFn>(image.base+integrate_quaternion_rva);
    const auto matrix=reinterpret_cast<MatrixFn>(image.base+quaternion_matrix_rva);
    SolverParameters defaults;std::array<std::byte,sizeof(SolverParameters)> native_defaults{};native_defaults.fill(std::byte{0xcd});
    reinterpret_cast<void(*)(void*)>(image.base+0x805890)(native_defaults.data());
    check(std::memcmp(native_defaults.data(),&defaults,sizeof(defaults))==0,"Solver constructor defaults differ from original");
    std::mt19937_64 rng(0x20261021);std::uniform_real_distribution<float> u(-1,1);
    constexpr std::size_t cases=20000;
    for(std::size_t n=0;n<cases;n++){
        RigidState state;for(auto& x:state.position)x=u(rng)*1000;
        for(auto& x:state.quaternion)x=u(rng);
        for(auto& x:state.linear_velocity)x=u(rng)*(n%7?200.f:20000.f);
        for(auto& x:state.angular_velocity)x=u(rng)*40.f;
        if(n%13==0)state.angular_velocity={0,0,0};
        if(n%17==0)state.quaternion={0,0,0,0};
        if(n%19==0)state.angular_velocity={1e-5f,0,0};
        const float dt=n%11==0?0.f:float(n%101)*.0001f;
        BodyParameters p{{u(rng),u(rng),u(rng)},n%5==0?0.f:std::abs(u(rng))*50};
        std::array<float,20> raw_model{};raw_model[7]=p.auxiliary_model_values[0];raw_model[11]=p.auxiliary_model_values[1];
        raw_model[15]=p.auxiliary_model_values[2];raw_model[19]=p.angular_speed_limit;
        const std::array<const void*,3> models{raw_model.data(),raw_model.data(),raw_model.data()};
        std::array<RigidState,3> native{state,state,state},ported=native;
        std::array<AuxiliaryOutput,3> native_out{{{7,8,9,10},{11,12,13,14},{15,16,17,18}}},ported_out=native_out;
        pose(models.data(),native.data(),native_out.data(),1,dt);
        integrate_pose(ported[1],p,ported_out[1],dt);
        same(native,ported,n,"rigid_state_and_untouched_neighbors");same(native_out,ported_out,n,"auxiliary_and_padding");
        auto nq=state.quaternion,pq=nq;quat(nq.data(),state.angular_velocity.data(),dt);integrate_quaternion(pq,state.angular_velocity,dt);
        same(nq,pq,n,"quaternion");
        std::array<float,9> nm{},pm{};matrix(nm.data(),state.quaternion.data());quaternion_to_matrix(pm,state.quaternion);same(nm,pm,n,"matrix");
    }
    // Compose a genuinely autonomous runner and independently compare every
    // one of 1000 future states with the original post-force kernel.
    RigidState initial;initial.position={1200,34,1360};initial.linear_velocity={1,2,-100};initial.angular_velocity={.02f,.3f,.01f};
    BodyParameters params{{1,2,3},10};RigidWorld world(1);world.reset(std::array{initial},std::array{params});
    auto baseline=initial;std::array<float,20> model{};model[7]=1;model[11]=2;model[15]=3;model[19]=10;
    const void* pointer=model.data();AuxiliaryOutput out{};
    auto saved=world.snapshot();for(int j=0;j<1000;j++){pose(&pointer,&baseline,&out,0,.01f);world.step(.01f);same(baseline,world.states()[0],j,"1000_step_rollout");}
    auto final=world.snapshot();world.restore(saved);for(int j=0;j<1000;j++)world.step(.01f);same(final.states[0],world.states()[0],0,"snapshot_restore");
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_recovered_kernel_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_kernel\":"<<cases<<",\"kernels\":3,\"bit_exact\":true,\"rollout_steps\":1000,\"snapshot_restore_exact\":true,"
        <<"\"solver_constructor_bytes_exact\":true,\"game_process_accessed\":false,\"game_entrypoint_executed\":false,\"original_arithmetic_executed_in_owned_test\":true,\"full_vehicle_physics\":false}\n";
    report.flush();check(bool(report),"Cannot save oracle report");
    std::cout<<"PASS RECOVERED_KERNEL_ORACLE cases_per_kernel="<<cases<<" bit_exact=true rollout_steps=1000 snapshot_restore=true game_accessed=false full_vehicle_physics=false\n";
}catch(const std::exception& error){std::cerr<<"RECOVERED_ORACLE_ERROR "<<error.what()<<'\n';return 1;}
