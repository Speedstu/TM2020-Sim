#include "tm2020/route_controller.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020 {
Controls propose_reference_controls(
    const RoutePlan& reference,const State& observed,
    const PurePursuitConfig& config){
    if(!std::isfinite(config.lookahead_m)||config.lookahead_m<2||
       config.lookahead_m>200||!std::isfinite(config.heading_gain)||
       config.heading_gain < -100 || config.heading_gain >100)
        throw std::invalid_argument("Invalid track-following controller parameters");
    if(!std::isfinite(observed.position.x)||!std::isfinite(observed.position.y)||
       !std::isfinite(observed.position.z)||!std::isfinite(observed.yaw_rad))
        throw std::invalid_argument("Missing verified vehicle pose/heading input");
    const auto target=reference.target(observed.position,observed.yaw_rad,config.lookahead_m);
    const double dx=target.waypoint.x-observed.position.x;
    const double dz=target.waypoint.z-observed.position.z;
    // Trackmania yaw convention inferred from GBX Euler heading in stored replays:
    // +pi roughly corresponds to motion along world -Z for this map.
    const double futureHeading=std::atan2(dx,dz);
    const double error=std::remainder(futureHeading-observed.yaw_rad,2.*3.14159265358979323846);
    const double steer=std::clamp(config.heading_gain*error,-1.0,1.0);
    // Very simple offline advisory: no modeled braking or longitudinal physics.
    return {steer,1.0,0.0};
}
Controls propose_tracking_controls(const Replay& replay,const RoutePlan& route,const State& state,const ReferenceTrackingConfig& config){
    if(!std::isfinite(config.heading_gain)||std::abs(config.heading_gain)>100||
       !std::isfinite(config.lateral_gain)||config.lateral_gain<0||config.lateral_gain>1||
       config.smoothing_radius>10||!std::isfinite(state.speed_kmh)||state.speed_kmh<0||
       replay.states.size()<route.waypoint_count())throw std::invalid_argument("Invalid reference tracking parameters");
    const auto target=route.target(state.position,state.yaw_rad,0);
    const auto& ref=replay.states.at(target.nearest_sample);
    const double heading=std::remainder(ref.yaw_rad-state.yaw_rad,2*3.14159265358979323846);
    const double lateral=std::cos(state.yaw_rad)*(ref.position.x-state.position.x)-
                         std::sin(state.yaw_rad)*(ref.position.z-state.position.z);
    double ff=0,weight=0;const auto radius=static_cast<std::int64_t>(config.smoothing_radius);
    for(auto delta=-radius;delta<=radius;delta++){
        const auto index=static_cast<std::int64_t>(target.nearest_sample)+delta;
        if(index<0||index>=static_cast<std::int64_t>(route.waypoint_count()))continue;
        const double w=double(radius+1-std::abs(delta));
        ff+=w*replay.states[static_cast<std::size_t>(index)].controls.steer;weight+=w;
    }
    const double ratio=config.scale_feedforward_with_speed?std::clamp(state.speed_kmh/std::max(30.,ref.speed_kmh),.2,1.3):1.;
    Controls action{std::clamp(ff/weight*ratio*ratio+config.heading_gain*heading-config.lateral_gain*lateral,-1.,1.),ref.controls.gas,ref.controls.brake};
    if(target.nearest_sample<route.waypoint_count()/20&&state.speed_kmh<3.6){action.gas=1;action.brake=0;}
    if(state.speed_kmh>ref.speed_kmh+25){action.gas=0;action.brake=1;}
    return action;
}
}
