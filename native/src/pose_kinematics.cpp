#include "tm2020/pose_kinematics.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace tm2020 {
namespace {
double dist(Vec3 a, Vec3 b) {
    return std::hypot(a.x-b.x,std::hypot(a.y-b.y,a.z-b.z));
}
bool finite(Vec3 a){
    return std::isfinite(a.x)&&std::isfinite(a.y)&&std::isfinite(a.z);
}
}
PoseKinematics::PoseKinematics(double ms,VelocityEstimateMethod mode):max_window_ms_(ms),method_(mode){
    if(!std::isfinite(ms)||ms<10||ms>500)throw std::invalid_argument("Pose window must be 10..500ms");
}
void PoseKinematics::reset() noexcept{history_.clear();}
PoseEstimate PoseKinematics::observe(double t,Vec3 p){
    if(!std::isfinite(t)||!finite(p))
        throw std::invalid_argument("Nonfinite pose/time");
    PoseEstimate result;
    result.position=p;
    if(!history_.empty()) {
        const double dt=t-history_.back().t;
        // Duplicated timestamp, backwards clock and large gaps require a
        // discontinuity instead of inferring absurd or stale speed.
        if(dt<=0||dt>max_window_ms_) {
            reset();
            result.presumed_teleport=true;
        } else {
            const double speed=dist(p,history_.back().p)/(dt/1000.0);
            if(speed>400.0) {
                reset();
                result.presumed_teleport=true;
            }
        }
    }
    history_.push_back({t,p});
    while(history_.size()>2 &&
          t-history_.front().t>max_window_ms_)
        history_.pop_front();
    result.history_count=static_cast<int>(history_.size());
    if(history_.size()<2)return result;
    if(method_==VelocityEstimateMethod::TwoPointSecant){
        const auto& a=history_[history_.size()-2];
        const auto& b=history_.back();
        const double invDt=1000./(b.t-a.t);
        result.observed_velocity_ms={(b.p.x-a.p.x)*invDt,(b.p.y-a.p.y)*invDt,(b.p.z-a.p.z)*invDt};
    } else {
    // Causal weighted least-squares slope: no future information.
    // O(N) with a bounded observed history; accurate for mostly-linear
    // motion, but latency in acceleration is unavoidable without physics.
    double wsum=0,tsum=0,t2sum=0;
    Vec3 psum{},ptsum{};
    for(const auto& s:history_){
        const double age=std::max(0.0,t-s.t);
        const double time=(s.t-t)/1000.0;
        const double weight=1.0/(1.0+age/40.0);
        wsum+=weight;
        tsum+=weight*time;
        t2sum+=weight*time*time;
        psum.x+=weight*s.p.x;psum.y+=weight*s.p.y;psum.z+=weight*s.p.z;
        ptsum.x+=weight*time*s.p.x;
        ptsum.y+=weight*time*s.p.y;
        ptsum.z+=weight*time*s.p.z;
    }
    const double denom=wsum*t2sum-tsum*tsum;
    if(denom<1e-12)return result;
    auto slope=[&](double ps,double pts){return (wsum*pts-tsum*ps)/denom;};
    result.observed_velocity_ms={
        slope(psum.x,ptsum.x),slope(psum.y,ptsum.y),slope(psum.z,ptsum.z)};
    }
    result.speed_kmh=3.6*std::hypot(
        result.observed_velocity_ms.x,
        std::hypot(result.observed_velocity_ms.y,result.observed_velocity_ms.z));
    result.path_heading_rad=std::atan2(result.observed_velocity_ms.z,result.observed_velocity_ms.x);
    result.sample_age_ms=t-history_.front().t;
    result.velocity_observable=std::isfinite(result.speed_kmh)&&result.speed_kmh<=1500.0;
    return result;
}
}
