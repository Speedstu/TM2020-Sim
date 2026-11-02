#include "tm2020/recovered_step.hpp"
#include <bit>
#include <cmath>
#include <stdexcept>
namespace tm2020::recovered {
namespace {
constexpr float f(std::uint32_t bits){return std::bit_cast<float>(bits);}
void require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
void bounded(float x){require(std::isfinite(x)&&std::abs(x)<=1e6f,"Step parameter exceeds finite domain");}
}
float approximate_power_of_two(float exponent){
    require(std::isfinite(exponent)&&exponent>=-200.f&&exponent<=100.f,"Exponent outside recovered approximation domain");
    const float sign=exponent<0.f?1.f:0.f;
    const float clamped=exponent>=-126.f?exponent:-126.f;
    const float fraction=(clamped-static_cast<float>(static_cast<std::int32_t>(clamped)))+sign;
    const float shifted=clamped+f(0x42f28c51);
    const float quotient=f(0x41ddd2fe)/(f(0x409af5f8)-fraction);
    const float raw=((quotient+shifted)-fraction*f(0x3fbebc8d))*f(0x4b000000);
    return std::bit_cast<float>(static_cast<std::uint32_t>(static_cast<std::int64_t>(raw)));
}
StepParameters prepare_step_parameters(float interval,const std::array<float,3>& gravity,
    const SolverParameters& solver,std::uint32_t opaque24,std::uint32_t opaque28){
    require(std::isfinite(interval)&&interval>=1e-6f&&interval<=1.f,"Invalid recovered step interval");
    for(float x:gravity)bounded(x);
    for(float x:{solver.depenetration_impulse_factor,solver.allowed_penetration,
        solver.max_depenetration_velocity,solver.min_velocity_for_restitution})bounded(x);
    const float exponent=((interval/f(0x3c23d70b))*f(0xbcb6c518))*f(0x3fb8aa3b);
    const float squared=(gravity[0]*gravity[0]+gravity[1]*gravity[1])+gravity[2]*gravity[2];
    return {interval,1.f/interval,approximate_power_of_two(exponent),std::sqrt(squared),
        solver.depenetration_impulse_factor,solver.allowed_penetration,solver.max_depenetration_velocity,
        solver.use_constraints2,solver.min_velocity_for_restitution,opaque24,opaque28};
}
float scaled_vehicle_substep_motion(const VehicleSubstepMotion& v,float scale,float interval){
    require(std::isfinite(scale)&&scale>=1e-4f&&scale<=100.f,"Vehicle time scale outside qualified domain");
    require(std::isfinite(interval)&&interval>=1e-6f&&interval<=1.f,"Vehicle interval outside qualified domain");
    const auto length=[](const std::array<float,3>& a){
        for(float x:a)require(std::isfinite(x)&&std::abs(x)<=10000.f,"Vehicle motion vector outside qualified domain");
        return std::sqrt((a[0]*a[0]+a[1]*a[1])+a[2]*a[2]);
    };
    float sum=length(v.linear_velocity);
    sum=sum+length(v.angular_velocity);
    sum=sum+length(v.vector_1348);
    sum=sum+length(v.vector_1354);
    const float scaled_interval=scale*interval;
    const float result=sum*scaled_interval;
    require(std::isfinite(result)&&result<=1e9f,"Vehicle scaled motion outside qualified domain");
    return result;
}
VehicleSubstepSelection select_vehicle_substeps(float motion,float limit,float scale,float interval){
    require(std::isfinite(motion)&&motion>=0.f&&motion<=1e9f,"Vehicle scaled motion outside qualified domain");
    require(std::isfinite(limit)&&limit>=1e-6f&&limit<=1e6f,"Vehicle motion limit outside qualified domain");
    require(std::isfinite(scale)&&scale>=1e-4f&&scale<=100.f,"Vehicle time scale outside qualified domain");
    require(std::isfinite(interval)&&interval>=1e-6f&&interval<=1.f,"Vehicle interval outside qualified domain");
    const float ratio=motion/limit;
    require(std::isfinite(ratio)&&ratio<=1e6f,"Vehicle substep ratio outside qualified domain");
    const auto candidate=static_cast<std::uint32_t>(static_cast<std::int64_t>(ratio))+1u;
    const auto count=candidate>1000u?1000u:candidate;
    const float total=scale*interval;
    if(count==1u)return {1u,0.f,0.f,total,0};
    const float unscaled=interval/static_cast<float>(count);
    const float repeated=unscaled*scale;
    const auto nanos=static_cast<std::int64_t>(static_cast<double>(unscaled)*-1e9);
    return {count,unscaled,repeated,total,nanos};
}
VehicleSubstepSelection select_vehicle_substeps(const VehicleSubstepMotion& motion,float limit,float scale,float interval){
    return select_vehicle_substeps(scaled_vehicle_substep_motion(motion,scale,interval),limit,scale,interval);
}
float vehicle_last_substep_interval(const VehicleSubstepSelection& p){
    require(p.substeps>=1&&p.substeps<=1000,"Invalid recovered vehicle substep count");
    require(std::isfinite(p.total_scaled_interval)&&p.total_scaled_interval>0.f&&p.total_scaled_interval<=100.f
            &&std::isfinite(p.repeated_scaled_interval)&&p.repeated_scaled_interval>=0.f
            &&p.repeated_scaled_interval<=p.total_scaled_interval,
            "Nonfinite recovered vehicle interval");
    float remaining=p.total_scaled_interval;
    for(std::uint32_t i=1;i<p.substeps;++i)remaining=remaining-p.repeated_scaled_interval;
    require(std::isfinite(remaining)&&remaining>=0.f,"Recovered vehicle interval residual outside qualified domain");
    return remaining;
}
}
