#include "tm2020/route_controller.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
void check(bool b,const char* message){if(!b)throw std::runtime_error(message);}
int main()try{
    tm2020::Replay replay;replay.finish_ms=1000;
    for(int i=0;i<=20;i++){
        tm2020::State s;s.time_ms=i*50;s.position={0,0,i*2.};s.speed_kmh=144;s.controls={0,1,0};
        replay.states.push_back(s);
    }
    const tm2020::RoutePlan route(replay);auto car=replay.states[10];
    auto control=tm2020::propose_tracking_controls(replay,route,car);
    check(std::abs(control.steer)<1e-12&&control.gas==1,"Straight reference equilibrium failed");
    car.position.x=2;const auto right=tm2020::propose_tracking_controls(replay,route,car);
    car.position.x=-2;const auto left=tm2020::propose_tracking_controls(replay,route,car);
    check(right.steer>0&&left.steer<0&&std::abs(right.steer+left.steer)<1e-12,"Cross-track corrective steering signs wrong");
    car=replay.states[10];car.yaw_rad=.1;
    check(tm2020::propose_tracking_controls(replay,route,car).steer>0,"Heading correction turns away from route");
    car=replay.states[10];car.speed_kmh=200;
    control=tm2020::propose_tracking_controls(replay,route,car);
    check(control.gas==0&&control.brake==1,"Overspeed reference guard failed");
    for(auto& sample:replay.states)sample.controls.steer=.5;
    const tm2020::RoutePlan turning(replay);car=replay.states[10];
    const auto fast=tm2020::propose_tracking_controls(replay,turning,car,{0,0,2,true});
    car.speed_kmh=72;const auto slow=tm2020::propose_tracking_controls(replay,turning,car,{0,0,2,true});
    check(std::abs(fast.steer-.5)<1e-12&&std::abs(slow.steer-.125)<1e-12,"Speed-dependent feedforward failed");
    car.speed_kmh=std::numeric_limits<double>::quiet_NaN();bool rejected=false;
    try{(void)tm2020::propose_tracking_controls(replay,turning,car);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected,"Nonfinite tracking speed accepted");
    std::cout<<"PASS REFERENCE_TRACKING lateral_sign=true heading_sign=true overspeed=true speed_scaled_feedforward=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
