#include "tm2020/recovered_rigid.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
int main(int argc,char** argv)try{
    if(argc!=4)throw std::invalid_argument("Usage: tm2020_rigid_benchmark bodies steps report.json (post-force kernel only)");
    const auto n=std::stoull(argv[1]),steps=std::stoull(argv[2]);
    if(n<1||n>1000000||steps<1||steps>100000)throw std::invalid_argument("Benchmark bounds exceeded");
    RigidWorld world(n);std::vector<RigidState> states(n);std::vector<BodyParameters> parameters(n);
    for(std::size_t i=0;i<n;i++){states[i].linear_velocity={1,2,-100};states[i].angular_velocity={.1f,.2f,.3f};parameters[i].angular_speed_limit=10;}
    world.reset(states,parameters);const auto saved=world.snapshot();const auto start=std::chrono::steady_clock::now();
    for(std::size_t i=0;i<steps;i++)world.step(.01f);
    const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    const auto final=world.states()[0];world.restore(saved);for(std::size_t i=0;i<steps;i++)world.step(.01f);
    if(final.position!=world.states()[0].position||final.quaternion!=world.states()[0].quaternion)throw std::runtime_error("Deterministic rerun failed");
    std::ofstream out(argv[3]);out<<"{\"schema\":\"tm2020_post_force_kernel_benchmark_v1\",\"bodies\":"<<n<<",\"steps\":"<<steps
        <<",\"seconds\":"<<seconds<<",\"body_steps_per_second\":"<<(double(n)*steps/seconds)
        <<",\"game_process_required\":false,\"game_assets_required\":false,\"original_code_required_at_runtime\":false,\"restore_future_identical\":true,\"full_vehicle_physics\":false}\n";
    out.flush();if(!out)throw std::runtime_error("Cannot write benchmark");
    std::cout<<"POST_FORCE_KERNEL body_steps_per_second="<<(double(n)*steps/seconds)<<" autonomous=true full_vehicle_physics=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
