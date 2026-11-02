#include "tm2020/recovered_world.hpp"
#include "tm2020/recovered_step.hpp"
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
int main(int argc,char** argv)try{
    if(argc>5)throw std::runtime_error("Usage: tm2020_rigid_mesh_demo [ticks=1000] [trace.csv] [report.json] [sse2|fma]");const auto ticks=argc>1?std::stoul(argv[1]):1000ul;if(ticks<2||ticks>1000000)throw std::runtime_error("Ticks must be in [2,1000000]");
    const std::string math=argc>4?argv[4]:"sse2";if(math!="sse2"&&math!="fma")throw std::invalid_argument("Unknown position math path");
    const std::array<ConvexVector,8> vertices{{{-1,-1,-1},{1,-1,-1},{-1,1,-1},{1,1,-1},{-1,-1,1},{1,-1,1},{-1,1,1},{1,1,1}}};
    const std::array<ConvexVector,3> axes{{{1,0,0},{0,1,0},{0,0,1}}};const std::array<std::array<std::uint32_t,4>,6> indices{{{0,4,6,2},{1,3,7,5},{0,1,5,4},{2,6,7,3},{0,2,3,1},{4,5,7,6}}};
    std::array<ConvexFace,6> faces{};for(std::size_t k=0;k<6;k++)faces[k]={std::uint32_t(k/2),k%2!=0,indices[k]};
    const std::array<ConvexEdge,12> edges{{{0,1,0},{2,3,0},{4,5,0},{6,7,0},{0,2,1},{1,3,1},{4,6,1},{5,7,1},{0,4,2},{1,5,2},{2,6,2},{3,7,2}}};
    const std::array<ConvexVector,4> floor{{{-100,0,-100},{-100,0,100},{100,0,100},{100,0,-100}}};const std::array<IndexedTriangle,2> triangles{{{{0,1,2},78,0},{{0,2,3},78,0}}};
    RigidMeshConfiguration config{};config.model.angular_speed_limit=100;config.velocity.coefficients={.1f,.1f,.1f,1};config.velocity.model_gravity_scale=1;config.velocity.item_gravity_multiplier=1;config.environment={{0,-10,0},false,.01f,.9f};config.velocity_iterations={5,1,5};config.position={0,.1f,.2f};config.position_iterations=4;config.restitution_speed_threshold=1;config.body_surface_id=78;
    config.position_math=math=="fma"?PositionMathPath::fused_avx_fma:PositionMathPath::scalar_sse2;
    RigidMeshWorld world({{vertices,axes,axes},faces,edges},{{0,0,0},{1,1,1},0},floor,triangles,{},config);RigidState initial{};initial.position={0,4,0};initial.linear_velocity={2,0,0};world.reset(initial);
    std::ofstream trace;if(argc>2){trace.open(argv[2]);if(!trace)throw std::runtime_error("Cannot open world trace");trace<<"tick,x,y,z,vx,vy,vz,contacts,patches\n"<<std::setprecision(9);}
    const auto begin=std::chrono::steady_clock::now();ForceAccumulator forces{};RigidMeshSnapshot midpoint{};std::size_t contacts{},patches{};
    for(unsigned long tick=0;tick<ticks;tick++){
        if(tick==ticks/2)midpoint=world.snapshot();const auto report=world.step(native_vehicle_interval,forces);contacts+=report.contacts;patches+=report.patches;
        if(trace.is_open()){const auto& s=world.state();trace<<world.tick();for(float x:s.position)trace<<','<<x;for(float x:s.linear_velocity)trace<<','<<x;trace<<','<<report.contacts<<','<<report.patches<<'\n';}
    }
    const auto expected=world.snapshot();world.restore(midpoint);for(unsigned long tick=ticks/2;tick<ticks;tick++)world.step(native_vehicle_interval,forces);const auto replay=world.snapshot();
    if(std::memcmp(&expected.state,&replay.state,sizeof(RigidState))||expected.tick!=replay.tick)throw std::runtime_error("World snapshot replay mismatch");
    const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
    if(trace.is_open()){trace.flush();if(!trace)throw std::runtime_error("Cannot flush world trace");}
    if(argc>3){std::ofstream report(argv[3]);report<<std::setprecision(9)<<"{\"schema\":\"tm2020_autonomous_rigid_mesh_demo_v1\",\"ticks\":"<<ticks<<",\"interval\":"<<native_vehicle_interval<<",\"intervalBits\":"<<std::bit_cast<std::uint32_t>(native_vehicle_interval)<<",\"positionMathDispatchFlag\":"<<unsigned(config.position_math)<<",\"contacts\":"<<contacts<<",\"patches\":"<<patches<<",\"snapshotReplayBitExact\":true,\"gameRequired\":false,\"originalExecutableRequiredAtRuntime\":false,\"pythonRequiredAtRuntime\":false,\"syntheticGeometryAndTuning\":true,\"completeVehiclePhysics\":false,\"adaptiveCcd\":false,\"elapsedIncludingReplaySeconds\":"<<seconds<<"}\n";if(!report)throw std::runtime_error("Cannot write world report");}
    std::cout<<"PASS AUTONOMOUS_RIGID_MESH ticks="<<ticks<<" contacts="<<contacts<<" patches="<<patches<<" snapshot_replay_bit_exact=true game_required=false complete_vehicle=false elapsed_s="<<seconds<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
