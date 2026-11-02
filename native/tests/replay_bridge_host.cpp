// Native C++ DLL runner: feed the real recorded Trackmania vehicle states
// through the bridge in a separate host (NOT injected into Trackmania).
// Simulates a host API to check latency, 24-map coverage, failure modes and
// ABI compatibility. Does not make the replay a causal physics simulator.
#include "tm2020/bridge.h"
#include "tm2020.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
struct Library {
    HMODULE module{};
    explicit Library(const fs::path& file){
        module=LoadLibraryW(fs::absolute(file).wstring().c_str());
        if(!module)throw std::runtime_error("Bridge DLL could not be loaded");
    }
    ~Library(){if(module)FreeLibrary(module);}
    template <class F> F find(const char* function){
        FARPROC p=GetProcAddress(module,function);
        if(!p)throw std::runtime_error(std::string("Missing ABI: ")+function);
        return reinterpret_cast<F>(p);
    }
};
using Init=int32_t(*)(const tm2020_bridge_config*);
using Sample=int32_t(*)(const tm2020_bridge_observation*,tm2020_bridge_action*);
using Shutdown=void(*)();
using Version=uint32_t(*)();
using GetError=const char*(*)();
int main(int argc,char** argv)try{
    if(argc!=5) {
        std::cerr<<"Usage: tm2020_bridge_bench <bridge.dll> <dataset-folder> <policy.tmbc> <out.csv>\n";
        return 2;
    }
    const fs::path dll=argv[1],data=argv[2],output=argv[4];
    const std::string checkpoint=argv[3];
    Library lib(dll);
    const auto init=lib.find<Init>("tm2020_bridge_init");
    const auto sample=lib.find<Sample>("tm2020_bridge_sample");
    const auto shutdown=lib.find<Shutdown>("tm2020_bridge_shutdown");
    const auto version=lib.find<Version>("tm2020_bridge_version");
    const auto lastError=lib.find<GetError>("tm2020_bridge_last_error");
    if(version()!=TM2020_BRIDGE_API_VERSION)throw std::runtime_error("ABI mismatch");
    fs::create_directories(output.parent_path());
    std::ofstream report(output);
    if(!report)throw std::runtime_error("Cannot write report on H:");
    report<<"tmx_id,frames,active_frames,neutral_failures,steer_mean_abs,gas_mean,"
             "brake_mean,route_dist_mean_m,throughput_actions_s\n";
    uint64_t total=0,active=0,failed=0;
    double totalElapsed=0;
    std::size_t maps=0;
    for(const auto& file:fs::directory_iterator(data)){
        if(file.path().extension()!=".tmreplay")continue;
        const auto replay=tm2020::Replay::load(file.path());
        const auto src=file.path().string();
        tm2020_bridge_config config{};
        config.size_bytes=sizeof(config);
        config.api_version=TM2020_BRIDGE_API_VERSION;
        config.mode=TM2020_BRIDGE_LOCAL_DEMONSTRATION;
        config.replay_tmreplay_utf8=src.c_str();
        config.policy_tmbc_utf8=checkpoint.c_str();
        config.lookahead_m=24.0;
        if(init(&config)!=TM2020_BRIDGE_OK)
            throw std::runtime_error(std::string("Bridge init failed: ")+lastError());
        uint64_t n=0,aCount=0,failCount=0;
        double steerAbs=0,gas=0,brake=0,routeErr=0;
        auto t0=std::chrono::steady_clock::now();
        for(const auto& frame:replay.states){
            if(frame.time_ms>replay.finish_ms)break;
            tm2020_bridge_observation ob{};
            ob.size_bytes=sizeof(ob);
            ob.api_version=TM2020_BRIDGE_API_VERSION;
            ob.tick_index=uint64_t(frame.time_ms/10)+1; // recorded 50ms sample, NOT real 100Hz telemetry
            ob.is_local_offline=1;  // simulated trusted offline host for smoke test only
            ob.is_valid_race_state=1;
            ob.world_position_xyz[0]=frame.position.x;
            ob.world_position_xyz[1]=frame.position.y;
            ob.world_position_xyz[2]=frame.position.z;
            ob.world_velocity_xyz[0]=frame.velocity.x;
            ob.world_velocity_xyz[1]=frame.velocity.y;
            ob.world_velocity_xyz[2]=frame.velocity.z;
            ob.heading_rad=frame.yaw_rad;
            ob.speed_kmh=frame.speed_kmh;
            ob.side_speed=frame.side_speed;
            ob.ground_contact=frame.ground_contact?1u:0u;
            for(int wheel=0;wheel<4;wheel++)ob.wheel_contact_materials[wheel]=frame.contact_materials[wheel];
            tm2020_bridge_action command{};
            command.size_bytes=sizeof(command);
            command.api_version=TM2020_BRIDGE_API_VERSION;
            const auto rc=sample(&ob,&command);
            if(rc!=TM2020_BRIDGE_OK){
                failCount++;
                if(command.active)throw std::runtime_error("Bridge emitted active controls after error");
                continue;
            }
            n++;
            aCount+=command.active;
            if(command.active) {
                if(!(std::isfinite(command.steer) && std::isfinite(command.throttle) &&
                     std::isfinite(command.brake)) || std::abs(command.steer)>1.0 ||
                     command.throttle<0||command.throttle>1||command.brake<0||command.brake>1)
                    throw std::runtime_error("Nonfinite/out-of-bounds policy output");
                steerAbs+=std::abs(command.steer);
                gas+=command.throttle;
                brake+=command.brake;
            }
            routeErr+=command.distance_from_reference_m;
        }
        const double time=std::chrono::duration<double>(
            std::chrono::steady_clock::now()-t0).count();
        shutdown();
        if(n<20 || aCount!=n || failCount>0)
            throw std::runtime_error("Unexpected bridge policy failure on "+file.path().filename().string());
        const std::string id=file.path().stem().string();
        report<<id<<","<<n<<","<<aCount<<","<<failCount<<","
              <<steerAbs/double(aCount)<<","<<gas/double(aCount)<<","
              <<brake/double(aCount)<<","<<routeErr/double(n)<<","
              <<double(n)/time<<"\n";
        total+=n;active+=aCount;failed+=failCount;totalElapsed+=time;
        maps++;
    }
    if(maps<20||total<10000||active!=total||failed)
        throw std::runtime_error("Native bridge sample coverage unexpectedly low");
    std::cout<<"PASS NATIVE_BRIDGE_REPLAY_HOST maps="<<maps
             <<" recorded50msFrames="<<total
             <<" advisoryPredictions="<<active
             <<" actionFailures="<<failed
             <<" predictionsPerSecond="<<double(active)/totalElapsed
             <<" result="<<output.string()
             <<" gameInjected=false counterfactualPhysics=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL bridge replay host: "<<e.what()<<"\n";return 1;}
