#include "tm2020/recovered_step.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
int main(int argc,char**argv)try{
    check(argc==3,"Usage: step_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,2> ranges{{{0x7f3ec0,0x7f3f3a},{0x8020a0,0x802186}}};
    ArithmeticImage image(argv[1],ranges);
    using Power=float(*)(float);
    using Constructor=StepParameters*(*)(StepParameters*,const float*,float,std::uint32_t,std::uint32_t,const SolverParameters*);
    const auto power=reinterpret_cast<Power>(image.base+0x7f3ec0);
    const auto constructor=reinterpret_cast<Constructor>(image.base+0x8020a0);
    std::mt19937_64 rng(0x2026102501);std::uniform_real_distribution<float> unit(-1.f,1.f),exponent(-200.f,100.f),dt(1e-6f,1.f);
    const std::array<float,16> special{-200,-126,std::nextafter(-126.f,0.f),-100,-1,std::nextafter(-1.f,0.f),-0.f,0.f,std::nextafter(0.f,1.f),.5f,1,10,50,99,100,std::nextafter(100.f,0.f)};
    for(std::size_t n=0;n<20000;n++){
        const float x=n%3?exponent(rng):special[(n/3)%special.size()];
        check(std::bit_cast<std::uint32_t>(power(x))==std::bit_cast<std::uint32_t>(approximate_power_of_two(x)),"Complete native exponent approximation differs");
        std::array<float,3> gravity{};for(float&v:gravity)v=unit(rng)*1e6f;
        if(n%17==0)gravity={-0.f,0.f,-0.f};if(n%19==0)gravity={0,-9.81f,0};
        SolverParameters solver{};solver.depenetration_impulse_factor=unit(rng);solver.allowed_penetration=unit(rng)*100;
        solver.max_depenetration_velocity=unit(rng)*100;solver.min_velocity_for_restitution=unit(rng)*100;
        solver.use_constraints2=std::uint32_t(rng());solver.velocity_bias_mode=std::uint32_t(rng());
        const auto before=solver;const auto gravity_before=gravity;
        const float interval=n%7==0?std::array{1e-6f,.001f,.01f,native_vehicle_interval,.02f,1.f}[(n/7)%6]:dt(rng);
        const auto opaque24=std::uint32_t(rng()),opaque28=std::uint32_t(rng());
        struct Output{std::array<std::uint32_t,4> pre;StepParameters step;std::array<std::uint32_t,4> post;} native;
        std::memset(&native,0xcd,sizeof(native));const auto guarded=native;
        check(constructor(&native.step,gravity.data(),interval,opaque24,opaque28,&solver)==&native.step,"Original constructor return differs");
        const auto ported=prepare_step_parameters(interval,gravity,solver,opaque24,opaque28);
        if(std::memcmp(&native.step,&ported,sizeof(ported))){std::cerr<<"STEP_MISMATCH case="<<n<<" dt="<<interval<<'\n';throw std::runtime_error("Complete step parameter bytes differ");}
        check(native.pre==guarded.pre&&native.post==guarded.post&&std::memcmp(&before,&solver,sizeof(solver))==0&&std::memcmp(&gravity_before,&gravity,sizeof(gravity))==0,"Original constructor mutated inputs or guards");
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_step_parameter_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":2,\"bit_exact\":true,\"entry_rvas\":[\"0x7f3ec0\",\"0x8020a0\"],\"exponent_domain\":[-200,100],\"interval_domain\":[0.000001,1],\"all_44_output_bytes_checked\":true,\"input_and_output_guards_unchanged\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"game_process_accessed\":false,\"complete_scheduler\":false}\n";report.flush();check(bool(report),"Cannot save step parameter report");
    std::cout<<"PASS STEP_PARAMETER_ORACLE operations=2 cases_each=20000 bit_exact=true all_44_bytes=true unmodified_callees=true\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
