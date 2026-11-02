#include "tm2020/experimental_sim.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <limits>
namespace tm2020::experimental {
namespace {
void verify(const Pose& s){
    if(!std::isfinite(s.x)||!std::isfinite(s.y)||!std::isfinite(s.z)||
       !std::isfinite(s.yaw)||!std::isfinite(s.speed_ms)||
       s.speed_ms<0||s.speed_ms>500.0)
        throw std::invalid_argument("Invalid sandbox pose");
}
}
Sandbox::Sandbox(std::size_t n):states_(n) {
    if(n==0||n>2'000'000)throw std::invalid_argument("Sandbox count must be 1..2M");
}
void Sandbox::reset(const std::vector<Pose>& initial){
    if(initial.size()!=states_.size())throw std::invalid_argument("Invalid reset batch");
    for(auto s:initial)verify(s);
    states_=initial;
    tick_=0;
}
Snapshot Sandbox::snapshot()const{return {tick_,states_};}
void Sandbox::restore(const Snapshot& state){
    if(state.states.size()!=states_.size())throw std::invalid_argument("Snapshot size mismatch");
    for(auto s:state.states)verify(s);
    states_=state.states;
    tick_=state.tick;
}
void Sandbox::step(std::span<const Action> actions){
    if(actions.size()!=states_.size())throw std::invalid_argument("Action count mismatch");
    if(tick_==std::numeric_limits<std::uint64_t>::max())throw std::overflow_error("Tick counter overflow");
    // Detect invalid actions before touching ANY state: atomic-input behavior.
    for(const auto& a:actions){
        if(!std::isfinite(a.steer)||!std::isfinite(a.gas)||!std::isfinite(a.brake)||
           a.steer<-1.0f||a.steer>1.0f||a.gas<0||a.gas>1||a.brake<0||a.brake>1)
            throw std::invalid_argument("Action controls must be finite and in range");
    }
    // These are heuristic demonstration constants, NOT reverse engineered Trackmania coefficients.
    constexpr double acceleration=8.0;
    constexpr double braking=16.0;
    constexpr double linear_drag=0.018;
    constexpr double steering_gain=0.028;
    constexpr double dt=timestep_s;
    for(std::size_t i=0;i<states_.size();++i){
        auto& s=states_[i];
        const auto& a=actions[i];
        const double accel=acceleration*a.gas-braking*a.brake-linear_drag*s.speed_ms*s.speed_ms;
        s.speed_ms=std::clamp(s.speed_ms+accel*dt,0.0,150.0);
        s.yaw=std::remainder(s.yaw+steering_gain*a.steer*s.speed_ms*dt,6.2831853071795864769);
        s.x+=std::sin(s.yaw)*s.speed_ms*dt;
        s.z+=std::cos(s.yaw)*s.speed_ms*dt;
        // y remains unchanged; absolutely no terrain/collisions in this sandbox.
    }
    ++tick_;
}
}
