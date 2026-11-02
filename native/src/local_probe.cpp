#include "tm2020/read_only_live.hpp"
#include "tm2020/local_input.hpp"
#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <thread>
int main(int argc,char** argv)try{
    if(argc!=7 || std::string(argv[1])!="--confirm-local-solo")throw std::invalid_argument(
        "Usage: tm2020_local_probe --confirm-local-solo manifest-v3 output.csv observe|keyboard|gamepad ViGEmClient.dll seconds");
    tm2020::live::ReadOnlyObserver observer(argv[2]);
    const std::string backend=argv[4];
    if(backend!="observe"&&backend!="keyboard"&&backend!="gamepad"&&backend!="reset"&&backend!="calibrate")throw std::invalid_argument("Unknown backend");
    const auto seconds=std::stod(argv[6]);
    if(!std::isfinite(seconds)||seconds<1||seconds>30)throw std::invalid_argument("Duration must be 1..30 seconds");
    std::ofstream out(argv[3]);if(!out)throw std::runtime_error("Cannot open capture CSV");
    out<<"elapsed_ms,copy,valid,x,y,z,vx,vy,vz,front_speed,gas,steer,brake,gear,ground,discontinuity,command_gas,raw_header0,raw_header1,raw_header2,raw_header3,command_steer\n";
    out<<std::fixed<<std::setprecision(6);
    std::unique_ptr<tm2020::live::LocalInput> input;
    if(backend!="observe")input=std::make_unique<tm2020::live::LocalInput>(observer.process_id(),
        backend=="keyboard"||backend=="reset"?tm2020::live::InputBackend::Keyboard:tm2020::live::InputBackend::ViGEmXbox360,
        std::filesystem::absolute(argv[5]));
    if(backend=="reset"){
        input->restart();std::cout<<"NORMAL_LOCAL_RACE_RESTART controls_neutral=true\n";return 0;
    }
    if(backend=="calibrate"){
        input->restart();std::this_thread::sleep_for(std::chrono::milliseconds(600));
        std::cout<<"REACQUIRED_REFLECTED_VISUAL_PAGES="<<observer.discover_visual_states()<<std::endl;
    }
    using Clock=std::chrono::steady_clock;
    const auto start=Clock::now();std::size_t rows{},valid{};double maximum=0;
    const auto initial=observer.poll_fresh_visual();if(!initial)throw std::runtime_error("No reflected visual state quorum");
    auto last_consensus=start;
    for(std::size_t tick=0;;tick++){
        const auto now=Clock::now();const double elapsed=std::chrono::duration<double>(now-start).count();
        if(elapsed>=seconds)break;
        const double gas=backend!="calibrate"&&elapsed>=.5 && elapsed<seconds-.5?1.:0.;
        constexpr double sweep[]={0,.05,.1,.15,.2,.25,.3,.4,.5,.6,.75,1,0,-.05,-.1,-.15,-.2,-.25,-.3,-.4,-.5,-.6,-.75,-1,0};
        const double steer=backend=="calibrate"?sweep[std::min(std::size_t(elapsed),std::size(sweep)-1)]:0.;
        if(input){
            if(observer.poll_fresh_visual())last_consensus=now;
            else {
                input->neutral();
                if(now-last_consensus>std::chrono::milliseconds(150))
                    throw std::runtime_error("Position consensus lost for 150ms: controls released");
            }
            if(now==last_consensus)input->apply({steer,gas,0});
        }
        const auto copies=observer.poll_visual_copies();
        for(std::size_t i=0;i<copies.size();i++){
            out<<elapsed*1000<<','<<i<<','<<bool(copies[i]);rows++;
            if(copies[i]){
                valid++;const auto& s=*copies[i];
                maximum=std::max(maximum,std::hypot(s.position.x-initial->state.position.x,s.position.z-initial->state.position.z));
                out<<','<<s.position.x<<','<<s.position.y<<','<<s.position.z
                   <<','<<s.world_velocity.x<<','<<s.world_velocity.y<<','<<s.world_velocity.z
                   <<','<<s.front_speed<<','<<s.input_gas<<','<<s.input_steer<<','<<s.input_brake
                   <<','<<s.gear<<','<<s.ground_contact<<','<<unsigned(s.discontinuity_count);
            }else out<<",,,,,,,,,,,,,,";
            out<<','<<gas;
            if(copies[i])for(auto word:copies[i]->raw_header_words)out<<','<<word;
            else out<<",,,,";
            out<<','<<steer<<'\n';
        }
        std::this_thread::sleep_until(start+std::chrono::milliseconds((tick+1)*10));
    }
    if(input)input->neutral();
    out.flush();if(!out)throw std::runtime_error("Failed writing CSV");
    std::cout<<"LOCAL_PROBE backend="<<backend<<" rows="<<rows<<" decoded="<<valid
             <<" maximum_candidate_motion_m="<<maximum<<" authoritative_physics=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"LOCAL_PROBE_ERROR "<<e.what()<<'\n';return 1;}
