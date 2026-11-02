// Host-side LoadLibrary integration test for the offline-only native bridge.
// This demonstrates a loadable DLL with a stable C ABI; it does NOT inject
// into Trackmania, read its private memory or bypass any game protections.
#include "tm2020/bridge.h"
#include "tm2020.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
namespace fs=std::filesystem;

void require(bool ok,const char* why){if(!ok)throw std::runtime_error(why);}
int main(int argc,char**argv)try{
    if(argc!=4)throw std::invalid_argument("Usage: bridge_test bridge.dll replay.tmreplay policy.tmbc");
    const auto dll=fs::absolute(argv[1]);
    HMODULE module=LoadLibraryW(dll.wstring().c_str());
    if(!module)throw std::runtime_error("Failed to LoadLibraryW test bridge");
    struct Guard {
        HMODULE lib;
        ~Guard(){if(lib)FreeLibrary(lib);}
    } guard{module};
    auto entry=[&](const char* name)->FARPROC{
        auto fn=GetProcAddress(module,name);
        if(!fn)throw std::runtime_error(std::string("Missing C ABI export: ")+name);
        return fn;
    };
    using Init=int32_t (*)(const tm2020_bridge_config*);
    using Sample=int32_t (*)(const tm2020_bridge_observation*,tm2020_bridge_action*);
    using Shutdown=void (*)();
    using Version=uint32_t (*)();
    using LastError=const char* (*)();
    const auto init=reinterpret_cast<Init>(entry("tm2020_bridge_init"));
    const auto step=reinterpret_cast<Sample>(entry("tm2020_bridge_sample"));
    const auto shutdown=reinterpret_cast<Shutdown>(entry("tm2020_bridge_shutdown"));
    const auto version=reinterpret_cast<Version>(entry("tm2020_bridge_version"));
    const auto lastError=reinterpret_cast<LastError>(entry("tm2020_bridge_last_error"));
    require(version()==TM2020_BRIDGE_API_VERSION,"ABI version mismatch");
    const auto replay=tm2020::Replay::load(argv[2]);
    const auto& start=replay.states.front();
    const auto& second=replay.states[1];
    tm2020_bridge_config config{};
    config.size_bytes=sizeof(config);
    config.api_version=TM2020_BRIDGE_API_VERSION;
    config.mode=TM2020_BRIDGE_OBSERVE_ONLY;
    config.lookahead_m=24.0;
    config.replay_tmreplay_utf8=argv[2];
    config.policy_tmbc_utf8=argv[3];
    require(init(&config)==TM2020_BRIDGE_OK,"Failed to initialize observe-only module");
    tm2020_bridge_observation ob{};
    ob.size_bytes=sizeof(ob);
    ob.api_version=TM2020_BRIDGE_API_VERSION;
    ob.tick_index=100;
    ob.is_local_offline=1;
    ob.is_valid_race_state=1;
    ob.world_position_xyz[0]=start.position.x;
    ob.world_position_xyz[1]=start.position.y;
    ob.world_position_xyz[2]=start.position.z;
    ob.world_velocity_xyz[0]=start.velocity.x;
    ob.world_velocity_xyz[1]=start.velocity.y;
    ob.world_velocity_xyz[2]=start.velocity.z;
    ob.heading_rad=start.yaw_rad;
    ob.speed_kmh=start.speed_kmh;
    ob.side_speed=start.side_speed;
    ob.ground_contact=start.ground_contact ? 1u : 0u;
    for(int wheel=0;wheel<4;wheel++)ob.wheel_contact_materials[wheel]=start.contact_materials[wheel];
    tm2020_bridge_action action{};
    auto resetOut=[&](){
        action={};
        action.size_bytes=sizeof(action);
        action.api_version=TM2020_BRIDGE_API_VERSION;
    };
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_OK,"Passive tick failed");
    require(action.active==0 && action.steer==0 && action.throttle==0 && action.brake==0,
            "Observe-only mode MUST output neutral action");
    require(action.route_lookahead_m>0,"Route planner failed in bridge");
    ob.tick_index++;
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_OK,"Second passive tick failed");
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_E_BAD_STATE,"Duplicate tick was not rejected");
    require(action.active==0,"Failed tick was not neutral");
    shutdown();
    config.mode=TM2020_BRIDGE_LOCAL_DEMONSTRATION;
    require(init(&config)==TM2020_BRIDGE_OK,"Failed to initialize demo-only mode");
    ob.tick_index=200;
    ob.is_local_offline=0;
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_E_NOT_LOCAL,
            "CRITICAL: online/non-local observations accepted");
    require(action.active==0 && action.steer==0 && action.throttle==0 && action.brake==0,
            "CRITICAL: online guard produced commands");
    ob.is_local_offline=1;
    ob.is_valid_race_state=0;
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_E_BAD_STATE,"Invalid race state accepted");
    ob.is_valid_race_state=1;
    ob.speed_kmh=std::numeric_limits<double>::infinity();
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_E_BAD_STATE,"Nonfinite state accepted");
    ob.speed_kmh=start.speed_kmh;
    ob.side_speed=start.side_speed;
    ob.ground_contact=start.ground_contact ? 1u : 0u;
    for(int wheel=0;wheel<4;wheel++)ob.wheel_contact_materials[wheel]=start.contact_materials[wheel];
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_OK,"Valid local policy tick failed");
    require(action.active==1 && std::isfinite(action.steer) &&
            std::abs(action.steer)<=1 && action.throttle>=0&&action.throttle<=1 &&
            action.brake>=0&&action.brake<=1, "Local policy output invalid");
    const auto firstSteer=action.steer;
    ob.world_position_xyz[0]=second.position.x;
    ob.world_position_xyz[1]=second.position.y;
    ob.world_position_xyz[2]=second.position.z;
    ob.tick_index++;
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_OK,"Second local prediction failed");
    shutdown();
    resetOut();
    require(step(&ob,&action)==TM2020_BRIDGE_E_NOT_INITIALIZED,
            "SDK accepted calls after shutdown");
    std::cout<<"PASS NATIVE BRIDGE: dll="+dll.string()
             <<" api="<<version()
             <<" observeNeutral=TRUE onlineDenied=TRUE invalidStateDenied=TRUE"
             <<" staleTickDenied=TRUE inProcessLocalInference=TRUE"
             <<" firstSteer="<<firstSteer
             <<" automaticGameInjection=FALSE actualTrackmaniaStateAdapter=NOT_READY\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL native bridge: "<<e.what()<<"\n";return 1;}
