// Separate native host regression for TM2020 bridge ABI v3 local-follower mode.
// No game process access, anti-cheat interaction, input injection or physics
// simulation. Only public stored replay observations + a known reference route.
#include "tm2020.hpp"
#include "tm2020/bridge.h"
#include "tm2020/route_controller.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
namespace fs=std::filesystem;
struct DLL {
    HMODULE value{};
    explicit DLL(const fs::path& p):value(LoadLibraryW(fs::absolute(p).wstring().c_str())){
        if(!value)throw std::runtime_error("Unable to load C++ bridge library");
    }
    ~DLL(){if(value)FreeLibrary(value);}
    template<class F>F entry(const char* name){
        auto address=GetProcAddress(value,name);
        if(!address)throw std::runtime_error(std::string("Missing ABI function: ")+name);
        return reinterpret_cast<F>(address);
    }
};
static void check(bool condition,const char* failure){
    if(!condition)throw std::runtime_error(failure);
}
int main(int argc,char**argv)try{
    if(argc!=4)throw std::invalid_argument(
        "Usage: campaign_bridge_follower_test <dll> <route-ref.tmreplay> <heldout.tmreplay>");
    DLL dll(argv[1]);
    const auto version=dll.entry<uint32_t(*)()>("tm2020_bridge_version");
    const auto init=dll.entry<int32_t(*)(const tm2020_bridge_config*)>("tm2020_bridge_init");
    const auto sample=dll.entry<int32_t(*)(const tm2020_bridge_observation*,tm2020_bridge_action*)>("tm2020_bridge_sample");
    const auto shutdown=dll.entry<void(*)()>("tm2020_bridge_shutdown");
    const auto err=dll.entry<const char*(*)()>("tm2020_bridge_last_error");
    check(version()==3,"C ABI v3 expected");
    const auto ref=tm2020::Replay::load(argv[2]);
    const auto eval=tm2020::Replay::load(argv[3]);
    check(ref.uid==eval.uid,"Map UID mismatch");
    const auto referencePath=std::string(argv[2]);
    tm2020_bridge_config config{};
    config.size_bytes=sizeof(config);
    config.api_version=TM2020_BRIDGE_API_VERSION;
    config.mode=TM2020_BRIDGE_LOCAL_REFERENCE_FOLLOWER;
    config.replay_tmreplay_utf8=referencePath.c_str();
    config.policy_tmbc_utf8=nullptr; // Policy MUST NOT need a Python/BC model.
    config.lookahead_m=40;
    config.heading_gain=-7.5;
    check(init(&config)==TM2020_BRIDGE_OK,"Could not start native reference follower");
    tm2020::RoutePlan route(ref);
    tm2020_bridge_observation ob{};
    ob.size_bytes=sizeof(ob);
    ob.api_version=TM2020_BRIDGE_API_VERSION;
    ob.is_valid_race_state=1;
    ob.is_local_offline=0; // Default untrusted; must fail safely.
    ob.tick_index=1;
    tm2020_bridge_action act{};
    act.size_bytes=sizeof(act);
    act.api_version=TM2020_BRIDGE_API_VERSION;
    check(sample(&ob,&act)==TM2020_BRIDGE_E_NOT_LOCAL &&
          act.active==0 && act.steer==0,
          "CRITICAL: observer returned active controls in online mode");
    double errorSum=0,baselineSum=0,mirrorDelta=0;
    unsigned n=0;
    for(const auto& state:eval.states){
        if(state.time_ms>eval.finish_ms)break;
        ob.is_local_offline=1; // Simulated trusted local host, no real server mode detection.
        ob.tick_index=uint64_t(state.time_ms/10)+2;
        ob.world_position_xyz[0]=state.position.x;
        ob.world_position_xyz[1]=state.position.y;
        ob.world_position_xyz[2]=state.position.z;
        ob.world_velocity_xyz[0]=state.velocity.x;
        ob.world_velocity_xyz[1]=state.velocity.y;
        ob.world_velocity_xyz[2]=state.velocity.z;
        ob.heading_rad=state.yaw_rad;
        ob.speed_kmh=state.speed_kmh;
        ob.side_speed=state.side_speed;
        ob.ground_contact=state.ground_contact?1:0;
        for(int wheel=0;wheel<4;wheel++)
            ob.wheel_contact_materials[wheel]=state.contact_materials[wheel];
        act={};
        act.size_bytes=sizeof(act);
        act.api_version=TM2020_BRIDGE_API_VERSION;
        if(sample(&ob,&act)!=TM2020_BRIDGE_OK)
            throw std::runtime_error(std::string("Bridge rejected valid heldout replay: ")+err());
        check(act.active==1&&std::isfinite(act.steer)&&std::abs(act.steer)<=1
              &&act.throttle>=0 &&act.throttle<=1 &&act.brake>=0&&act.brake<=1,
              "Pure pursuit generated invalid action");
        const auto independent=tm2020::propose_reference_controls(route,state,{40,-7.5});
        mirrorDelta+=std::abs(independent.steer-act.steer);
        errorSum+=std::abs(act.steer-state.controls.steer);
        baselineSum+=std::abs(state.controls.steer);
        n++;
    }
    shutdown();
    check(n>350,"Insufficient race state frames");
    check(mirrorDelta<1e-8*n,"DLL output differs from direct native C++ control");
    check(errorSum<baselineSum*0.8,"Native bridge follower did not beat zero-steering baseline");
    std::cout<<std::fixed<<std::setprecision(6)
             <<"PASS CXX_DLL_CAMPAIGN_FOLLOWER ABI="<<version()
             <<" samples="<<n
             <<" steerMAE="<<errorSum/n
             <<" zeroSteerMAE="<<baselineSum/n
             <<" directCppParityMAE="<<mirrorDelta/n
             <<" modelFileRequired=false"
             <<" onlineGuardDenied=true"
             <<" actualGameDriving=false"
             <<" headlessPhysics=false\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"FAIL CXX_DLL_FOLLOWER "<<e.what()<<"\n";return 1;
}
