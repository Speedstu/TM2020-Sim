// SPDX-License-Identifier: GPL-3.0-or-later
// Persistent native physics workers for matched continuous/categorical PPO.
#include "fast_training.h"
#include "../../native/include/tm2020/trajectory_hybrid.hpp"
#include "../../native/include/tm2020/input_statistics.hpp"
#include <dlfcn.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <barrier>
#include <cstring>
#include <cstdlib>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
namespace {
thread_local std::string error;
struct Batch {
    void* library{};std::size_t n{},workers{};uint32_t repeat{5},banks{1},horizon{4000};bool stopping{};
    std::atomic<bool> ready{};bool startup_cancelled{};
    tmfast_env (*open)(const char*,const char*,const char*,uint32_t){};
    tmfast_env (*clone)(tmfast_env){};void (*close)(tmfast_env){};
    int (*reset)(tmfast_env,uint32_t,tmfast_state*){};
    int (*reset_bank)(tmfast_env,uint32_t,uint32_t,tmfast_state*){};
    int (*restore_checkpoint)(tmfast_env,tmfast_env,uint32_t,tmfast_state*){};
    int (*preview)(tmfast_env,double*){};
    int (*step)(tmfast_env,const float*,uint32_t,tmfast_state*){};
    int (*launch_uncertainty)(tmfast_env,float){};
    const char* (*last_error)(){};
    std::vector<tmfast_env> environments;std::vector<tmfast_state> states;
    std::vector<std::array<float,3>> controls;std::vector<std::string> failures;
    std::vector<float> launch_deltas;
    std::vector<uint32_t> hybrid_progress;
    std::vector<tm2020::internal::InputStatistics> input_statistics;
    std::vector<std::array<uint32_t,tm2020::internal::InputStatistics::size>> input_counts;
    std::array<tmfast_env,256> checkpoints{};
    double* preview_output{};
    std::function<void(std::size_t)> whole_race_job;
    std::atomic<std::size_t> next_race{};
    std::unique_ptr<std::barrier<>> start,finish;std::vector<std::thread> threads;
    ~Batch(){
        if(!threads.empty()){stopping=true;start->arrive_and_wait();for(auto& t:threads)t.join();}
        if(close){for(auto checkpoint:checkpoints)if(checkpoint)close(checkpoint);for(auto env:environments)close(env);}
        if(library)dlclose(library);
    }
    template<class T> void bind(T& function,const char* name){
        function=reinterpret_cast<T>(dlsym(library,name));if(!function)throw std::runtime_error(std::string("Missing physics ABI: ")+name);
    }
    void init(const char* dll,const char* map,const char* packs,std::size_t count,uint32_t decision_ticks=5,const char* replay="/dev/null",uint32_t max_ticks=4000){
        if(count<1||count>64)throw std::runtime_error("Vector size outside 1..64");
        if(decision_ticks!=1&&decision_ticks!=5)throw std::runtime_error("Decision interval must be 1 or 5 physics ticks");
        repeat=decision_ticks;
        if(max_ticks<1||max_ticks>100000)throw std::runtime_error("Invalid race horizon");
        horizon=max_ticks;
        n=count;
        library=dlopen(dll,RTLD_LOCAL|RTLD_NOW);if(!library)throw std::runtime_error(dlerror());
        uint32_t (*version)(){},(*reward)(){};bind(version,"tmfast_version");bind(reward,"tmgen_reward_version");
        if(version()!=4||reward()!=3)throw std::runtime_error("Matched experiment requires API4, pure minimum-time reward v3");
        bind(open,"tmfast_open");bind(clone,"tmfast_clone");bind(close,"tmfast_close");bind(reset,"tmfast_reset");
        bind(step,"tmfast_step_controls");bind(last_error,"tmfast_last_error");
        launch_uncertainty=reinterpret_cast<decltype(launch_uncertainty)>(dlsym(library,"tmfast_launch_uncertainty"));
        // Optional extended ABI: legacy libraries and frozen jobs still work.
        restore_checkpoint=reinterpret_cast<decltype(restore_checkpoint)>(dlsym(library,"tmgen_restore_checkpoint"));
        preview=reinterpret_cast<decltype(preview)>(dlsym(library,"tmgen_preview_current"));
        auto root=open(map,packs,replay,horizon);if(!root)throw std::runtime_error(last_error());environments.push_back(root);
        uint32_t (*bank_size)(tmfast_env){};bind(bank_size,"tmfast_bank_size");bind(reset_bank,"tmfast_reset_bank");banks=bank_size(root);
        for(std::size_t i=1;i<n;++i){auto env=clone(root);if(!env)throw std::runtime_error(last_error());environments.push_back(env);}
        states.resize(n);controls.resize(n);failures.resize(n);launch_deltas.resize(n);hybrid_progress.resize(n);
        input_statistics.resize(n);input_counts.resize(n);
        // The simulator remains native CPU physics. Keep the number of heavy
        // physics workers adjustable independently of the CUDA PPO batch.
        // Useful on hot laptop CPUs: lower worker counts reduce concurrent
        // heat without changing the numerical environment or policy.
        auto requested=std::size_t(16);
        if(const char* e=std::getenv("TM2020_PHYSICS_WORKERS");e && *e){
            char* end=nullptr;
            const auto parsed=std::strtol(e,&end,10);
            if(end==e||*end||parsed<1||parsed>16)
                throw std::runtime_error("TM2020_PHYSICS_WORKERS must be integer 1..16");
            requested=static_cast<std::size_t>(parsed);
        }
        workers=std::min(n,requested);
        start=std::make_unique<std::barrier<>>(workers+1);finish=std::make_unique<std::barrier<>>(workers+1);
        try{for(std::size_t w=0;w<workers;++w)threads.emplace_back([this,w]{
            while(!ready.load(std::memory_order_acquire))std::this_thread::yield();
            if(startup_cancelled)return;
            for(;;){start->arrive_and_wait();if(stopping)break;
                if(whole_race_job){
                    for(;;){const auto i=next_race.fetch_add(1,std::memory_order_relaxed);if(i>=n)break;
                        try{whole_race_job(i);}catch(const std::exception& e){failures[i]=e.what();}
                        catch(...){failures[i]="Unknown whole-race worker failure";}
                    }
                    finish->arrive_and_wait();continue;
                }
                for(std::size_t i=w;i<n;i+=workers){
                    if(preview_output){
                        if(states[i].reserved)std::fill_n(preview_output+i*72,72,0.);
                        else if(preview(environments[i],preview_output+i*72))failures[i]=last_error();
                        continue;
                    }
                    if(states[i].terminated||states[i].truncated)continue;
                    if(step(environments[i],controls[i].data(),repeat,&states[i]))failures[i]=last_error();
                }finish->arrive_and_wait();
            }
        });}catch(...){startup_cancelled=true;ready.store(true,std::memory_order_release);for(auto& t:threads)t.join();threads.clear();throw;}
        ready.store(true,std::memory_order_release);
    }
};
}
extern "C" {
const char* tmvec_error(){return error.c_str();}
void* tmvec_open(const char* library,const char* map,const char* packs,uint32_t n){
    try{auto b=std::make_unique<Batch>();b->init(library,map,packs,n);return b.release();}
    catch(const std::exception& e){error=e.what();return nullptr;}
}
void* tmvec_open_period(const char* library,const char* map,const char* packs,const char* replay,uint32_t n,uint32_t repeat){
    try{auto b=std::make_unique<Batch>();b->init(library,map,packs,n,repeat,replay?replay:"/dev/null");return b.release();}
    catch(const std::exception& e){error=e.what();return nullptr;}
}
void* tmvec_open_period_horizon(const char* library,const char* map,const char* packs,const char* replay,uint32_t n,uint32_t repeat,uint32_t horizon){
    try{auto b=std::make_unique<Batch>();b->init(library,map,packs,n,repeat,replay?replay:"/dev/null",horizon);return b.release();}
    catch(const std::exception& e){error=e.what();return nullptr;}
}
uint32_t tmvec_bank_count(void* p){return static_cast<Batch*>(p)->banks;}
const uint32_t* tmvec_hybrid_progress(void* p){return static_cast<Batch*>(p)->hybrid_progress.data();}
const uint32_t* tmvec_hybrid_input_statistics(void* p){
    auto& b=*static_cast<Batch*>(p);
    for(std::size_t i=0;i<b.n;++i)b.input_counts[i]=b.input_statistics[i].snapshot();
    return b.input_counts.front().data();
}
int tmvec_launch_uncertainty(void* p,const float* deltas){
    auto& b=*static_cast<Batch*>(p);if(!deltas){error="Missing launch uncertainty array";return -1;}
    for(std::size_t i=0;i<b.n;++i)if(!std::isfinite(deltas[i])||std::abs(deltas[i])>.1f){error="Launch uncertainty outside +/-0.1 m/s";return -1;}
    if(!b.launch_uncertainty){error="Physics lacks launch uncertainty ABI";return -1;}
    std::copy_n(deltas,b.n,b.launch_deltas.begin());return 0;
}
int tmvec_set_control_mode(void* p,uint32_t mode){
    auto& b=*static_cast<Batch*>(p);
    if(mode>1){error="Invalid control mode";return -1;}
    auto setter=reinterpret_cast<int(*)(tmfast_env,uint32_t)>(dlsym(b.library,"tmfast_set_control_mode"));
    if(!setter){error="Physics lacks explicit internal control mode ABI";return -1;}
    for(const auto& s:b.states)if(s.tick!=0){error="Control mode requires all clones at race zero";return -1;}
    for(auto env:b.environments)if(setter(env,mode)){error=b.last_error();return -1;}
    return 0;
}
int tmvec_preview(void* p,double* output){
    auto& b=*static_cast<Batch*>(p);if(!b.preview||!output){error="Missing preview ABI/output";return -1;}
    b.preview_output=output;b.start->arrive_and_wait();b.finish->arrive_and_wait();b.preview_output=nullptr;
    for(const auto& failure:b.failures)if(!failure.empty()){error=failure;return -1;}return 0;
}
int tmvec_preview_one(void* p,uint32_t i,double* output){
    auto& b=*static_cast<Batch*>(p);if(!b.preview||!output||i>=b.n){error="Invalid single preview";return -1;}
    if(b.states[i].reserved){std::fill_n(output,72,0.);return 0;}
    if(b.preview(b.environments[i],output)){error=b.last_error();return -1;}return 0;
}
int tmvec_save_checkpoint(void* p,uint32_t i,uint32_t slot){
    auto& b=*static_cast<Batch*>(p);
    if(!b.restore_checkpoint||i>=b.n||slot>=b.checkpoints.size()||b.states[i].terminated||b.states[i].truncated){error="Invalid checkpoint source/slot/ABI";return -1;}
    auto checkpoint=b.clone(b.environments[i]);if(!checkpoint){error=b.last_error();return -1;}
    if(b.checkpoints[slot])b.close(b.checkpoints[slot]);b.checkpoints[slot]=checkpoint;return 0;
}
int tmvec_restore_checkpoint(void* p,uint32_t i,uint32_t slot,uint32_t seed){
    auto& b=*static_cast<Batch*>(p);
    if(!b.restore_checkpoint||i>=b.n||slot>=b.checkpoints.size()||!b.checkpoints[slot]){error="Invalid checkpoint restore/ABI";return -1;}
    if(b.restore_checkpoint(b.environments[i],b.checkpoints[slot],seed,&b.states[i])){error=b.last_error();return -1;}
    b.failures[i].clear();return 0;
}
void tmvec_close(void* p){delete static_cast<Batch*>(p);}
tmfast_state* tmvec_states(void* p){return static_cast<Batch*>(p)->states.data();}
int tmvec_reset(void* p,uint32_t i,uint32_t seed){
    auto& b=*static_cast<Batch*>(p);if(i>=b.n){error="Reset index outside vector";return -1;}
    if(b.reset(b.environments[i],seed,&b.states[i])){error=b.last_error();return -1;}
    if(b.launch_uncertainty&&b.launch_uncertainty(b.environments[i],b.launch_deltas[i])){error=b.last_error();return -1;}
    b.failures[i].clear();return 0;
}
int tmvec_reset_bank(void* p,uint32_t i,uint32_t seed,uint32_t bank){
    auto& b=*static_cast<Batch*>(p);if(i>=b.n||bank>=b.banks){error="Reset bank/index outside vector";return -1;}
    if(b.reset_bank(b.environments[i],seed,bank,&b.states[i])){error=b.last_error();return -1;}
    b.failures[i].clear();return 0;
}
int tmvec_step_one(void* p,uint32_t i,const float* controls){
    auto& b=*static_cast<Batch*>(p);if(i>=b.n||!controls){error="Warmup index/action outside vector";return -1;}
    if(b.states[i].terminated||b.states[i].truncated){error="Warmup after termination";return -1;}
    if(b.step(b.environments[i],controls,1,&b.states[i])){error=b.last_error();return -1;}
    return 0;
}
int tmvec_step(void* p,const float* controls){
    auto& b=*static_cast<Batch*>(p);if(!controls){error="Null action batch";return -1;}
    std::memcpy(b.controls.data(),controls,b.n*3*sizeof(float));
    b.start->arrive_and_wait();b.finish->arrive_and_wait();
    for(auto& message:b.failures)if(!message.empty()){error=message;return -1;}
    return 0;
}
// Bounded whole-race evaluation, same native controller as the DLL. No Python
// per-tick roundtrips. Each candidate receives its own explicit gains/case.
int tmvec_hybrid_evaluate_assets(void* p,const char* const* assets,const double* gains,const uint32_t* seeds,
                         const uint32_t* warm,const uint32_t* duration,const float* kicks){
    try{
        auto& b=*static_cast<Batch*>(p);if(b.repeat!=1||!assets||!gains||!seeds||!warm||!duration||!kicks)
            throw std::runtime_error("Invalid 100Hz hybrid evaluation arguments");
        std::vector<tm2020::hybrid::Tracker> trackers;trackers.reserve(b.n);
        for(std::size_t i=0;i<b.n;++i)trackers.push_back(tm2020::hybrid::Tracker::load(assets[i]));
        std::vector<tm2020::hybrid::Cursor> cursors(b.n);
        std::fill(b.input_statistics.begin(),b.input_statistics.end(),tm2020::internal::InputStatistics{});
        std::fill(b.hybrid_progress.begin(),b.hybrid_progress.end(),0);
        for(uint32_t i=0;i<b.n;++i)if(tmvec_reset(p,i,seeds[i]))return -1;
        for(unsigned t=0;t<b.horizon;++t){bool active=false;
            for(std::size_t i=0;i<b.n;++i){
                if(b.states[i].terminated||b.states[i].truncated)continue;active=true;
                auto& tracker=trackers[i];std::copy_n(gains+i*6,6,tracker.gains.begin());
                std::array<float,22> rigid{};std::memcpy(rigid.data(),b.states[i].rigid_words,88);
                tm2020::internal::Controls command{};
                tracker.action(cursors[i],rigid.data(),b.states[i].tick*10,command);
                b.hybrid_progress[i]=std::max(b.hybrid_progress[i],cursors[i].index);
                if(t>=warm[i]&&t<warm[i]+duration[i])command.steer=std::clamp(command.steer+kicks[i],-1.f,1.f);
                command.steer=std::round(command.steer*127.f)/127.f;
                b.input_statistics[i].observe(command.gas,command.brake,command.steer);
                b.controls[i]={command.gas,command.brake,command.steer};
            }
            if(!active)break;
            b.start->arrive_and_wait();b.finish->arrive_and_wait();
            for(const auto& failure:b.failures)if(!failure.empty())throw std::runtime_error(failure);
        }return 0;
    }catch(const std::exception& e){error=e.what();return -1;}
}
int tmvec_hybrid_evaluate(void* p,const char* asset,const double* gains,const uint32_t* seeds,
                         const uint32_t* warm,const uint32_t* duration,const float* kicks){
    const auto& b=*static_cast<Batch*>(p);std::vector<const char*> assets(b.n,asset);
    return tmvec_hybrid_evaluate_assets(p,assets.data(),gains,seeds,warm,duration,kicks);
}
// Each independent race stays on one worker. The original evaluator above is
// retained for complete-state parity checks and matched speed measurements.
int tmvec_hybrid_evaluate_assets_fast(void* p,const char* const* assets,const double* gains,const uint32_t* seeds,
                         const uint32_t* warm,const uint32_t* duration,const float* kicks){
    try{
        auto& b=*static_cast<Batch*>(p);
        if(b.repeat!=1||!assets||!gains||!seeds||!warm||!duration||!kicks)
            throw std::runtime_error("Invalid 100Hz hybrid evaluation arguments");
        std::vector<tm2020::hybrid::Tracker> trackers;trackers.reserve(b.n);
        for(std::size_t i=0;i<b.n;++i){
            trackers.push_back(tm2020::hybrid::Tracker::load(assets[i]));
            if(trackers.back().version==4){
                auto mode=reinterpret_cast<uint32_t(*)(tmfast_env)>(dlsym(b.library,"tmfast_control_mode"));
                if(!mode||mode(b.environments[i])!=0)throw std::runtime_error("Learned v4 controller requires normal recorded input history");
            }
            std::copy_n(gains+i*6,6,trackers.back().gains.begin());
        }
        b.next_race=0;
        std::fill(b.input_statistics.begin(),b.input_statistics.end(),tm2020::internal::InputStatistics{});
        std::fill(b.hybrid_progress.begin(),b.hybrid_progress.end(),0);
        b.whole_race_job=[&](std::size_t i){
            b.failures[i].clear();
            if(b.reset(b.environments[i],seeds[i],&b.states[i])){b.failures[i]=b.last_error();return;}
            if(b.launch_uncertainty&&b.launch_uncertainty(b.environments[i],b.launch_deltas[i])){b.failures[i]=b.last_error();return;}
            tm2020::hybrid::Cursor cursor;
            for(unsigned t=0;t<b.horizon;++t){
                if(b.states[i].terminated||b.states[i].truncated)break;
                std::array<float,22> rigid{};std::memcpy(rigid.data(),b.states[i].rigid_words,88);
                tm2020::internal::Controls command{};
                trackers[i].action(cursor,rigid.data(),b.states[i].tick*10,command);
                b.hybrid_progress[i]=std::max(b.hybrid_progress[i],cursor.index);
                if(t>=warm[i]&&t<warm[i]+duration[i])command.steer=std::clamp(command.steer+kicks[i],-1.f,1.f);
                command.steer=std::round(command.steer*127.f)/127.f;
                const std::array<float,3> controls{command.gas,command.brake,command.steer};
                b.input_statistics[i].observe(command.gas,command.brake,command.steer);
                if(b.step(b.environments[i],controls.data(),1,&b.states[i])){b.failures[i]=b.last_error();return;}
            }
        };
        b.start->arrive_and_wait();b.finish->arrive_and_wait();b.whole_race_job={};
        for(const auto& failure:b.failures)if(!failure.empty())throw std::runtime_error(failure);
        return 0;
    }catch(const std::exception& e){error=e.what();return -1;}
}
int tmvec_hybrid_evaluate_fast(void* p,const char* asset,const double* gains,const uint32_t* seeds,
                         const uint32_t* warm,const uint32_t* duration,const float* kicks){
    const auto& b=*static_cast<Batch*>(p);std::vector<const char*> assets(b.n,asset);
    return tmvec_hybrid_evaluate_assets_fast(p,assets.data(),gains,seeds,warm,duration,kicks);
}
}
