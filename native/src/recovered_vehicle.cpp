#include "tm2020/recovered_vehicle.hpp"
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
void scalar(float x){if(!std::isfinite(x)||std::abs(x)>1e6f)throw std::invalid_argument("Vehicle kernel exceeds finite domain");}
template<std::size_t N>void bounded(const std::array<float,N>& a){for(float x:a)scalar(x);}
std::array<float,3> rotate(const std::array<float,9>& r,const std::array<float,3>& p){
    std::array<float,3> out{};for(std::size_t k=0;k<3;k++)out[k]=(r[k*3]*p[0]+r[k*3+1]*p[1])+r[k*3+2]*p[2];return out;
}
float hermite(std::span<const CurvePoint> p,std::size_t left,float t,bool zero_end){
    const auto right=left+1,previous=left?left-1:left,next=right+1<p.size()?right+1:right;
    const float width=p[right].x-p[left].x;
    const float slope_a=((p[right].y-p[previous].y)/(p[right].x-p[previous].x))*width;
    float slope_b=((p[next].y-p[left].y)/(p[next].x-p[left].x))*width;
    if(zero_end&&right+1==p.size())slope_b=0;
    const float squared=t*t;
    const float first=(p[left].y-p[right].y)+(p[left].y-p[right].y);
    const float cubic=(first+slope_a)+slope_b;
    const float quadratic=((p[right].y-p[left].y)*3.f-(slope_a+slope_a))-slope_b;
    return (quadratic*squared+(slope_a*t+p[left].y))+cubic*(squared*t);
}
}
float evaluate_curve(std::span<const CurvePoint> points,float x,std::uint32_t flags){
    scalar(x);if(points.size()>1000000)throw std::invalid_argument("Too many curve points");
    for(std::size_t k=0;k<points.size();k++){scalar(points[k].x);scalar(points[k].y);if(k&&!(points[k].x>points[k-1].x))throw std::invalid_argument("Curve abscissae must increase strictly");}
    if(points.empty())return 0;
    constexpr float epsilon=9.999999747378752e-6f;
    if(points.size()==1||!(points.front().x+epsilon<=x))return points.front().y;
    if(x>points.back().x-epsilon)return points.back().y;
    std::size_t right=1;while(points[right].x+epsilon<x)++right;
    const auto left=right-1;const float width=points[right].x-points[left].x;
    if(epsilon>std::abs(width)||(flags&1))return points[left].y;
    float t=(x-points[left].x)/width;
    if(flags&2)t=(t*3.f)*t-((t+t)*t)*t;
    else if(flags&0x10){const float result=hermite(points,left,t,(flags&0x20)!=0);scalar(result);return result;}
    const float result=(1.f-t)*points[left].y+t*points[right].y;scalar(result);return result;
}
void apply_local_force_at_point(ForceAccumulator& accumulator,const RigidState& pose,
    const std::array<float,3>& center,const std::array<float,3>& local_force,const std::array<float,3>& local_point){
    bounded(accumulator.linear);bounded(accumulator.angular);bounded(pose.rotation);bounded(pose.position);bounded(center);bounded(local_force);bounded(local_point);
    auto next=accumulator;const auto force=rotate(pose.rotation,local_force);auto point=rotate(pose.rotation,local_point);
    std::array<float,3> lever{};
    for(std::size_t k=0;k<3;k++){
        point[k]=point[k]+pose.position[k];
        const float center_world=((center[1]*pose.rotation[k*3+1]+center[0]*pose.rotation[k*3])+center[2]*pose.rotation[k*3+2])+pose.position[k];
        lever[k]=point[k]-center_world;
        next.linear[k]=force[k]+next.linear[k];
    }
    const std::array torque{lever[1]*force[2]-lever[2]*force[1],lever[2]*force[0]-lever[0]*force[2],lever[0]*force[1]-lever[1]*force[0]};
    for(std::size_t k=0;k<3;k++)next.angular[k]=torque[k]+next.angular[k];
    bounded(next.linear);bounded(next.angular);accumulator=next;
}
bool apply_suspension_mode2(ForceAccumulator& accumulator,const RigidState& pose,
    const std::array<float,3>& center,const std::array<float,3>& point,const SuspensionParameters& parameters,
    const std::array<SuspensionWheelState,4>& wheels,std::size_t selected){
    float force{};if(!suspension_mode2(parameters,wheels,selected,force))return false;
    apply_local_force_at_point(accumulator,pose,center,{0,force,0},point);return true;
}
}
