#pragma once
#include <array>
#include <cmath>
#include <cstdint>

namespace tm2020::internal {
struct Controls { float gas{},brake{},steer{}; };
struct PhysicsTick {
    std::uintptr_t manager{},vehicle{},body{};
    std::uint32_t timestamp_ms{};
    float interval{};
    std::array<float,22> rigid{}; // R9, position3, quaternion4, velocity3, omega3
    bool session_verified{},owner_verified{},race_running{};
};
struct CandidateIdentity {std::uintptr_t manager{},vehicle{},body{};std::uint32_t race_start_ms{};};
inline bool qualified_candidate(const CandidateIdentity& prior,const PhysicsTick& s,std::uint32_t start,bool allow_reset)noexcept{
    if(s.manager!=prior.manager||s.body!=prior.body)return false;
    if(s.vehicle==prior.vehicle)return true;
    return allow_reset&&std::int32_t(start-prior.race_start_ms)>0&&std::uint32_t(s.timestamp_ms-start)<3000;
}
inline bool commit_qualified_candidate(CandidateIdentity& prior,const PhysicsTick& s,std::uint32_t start,bool allow_reset)noexcept{
    if(!qualified_candidate(prior,s,start,allow_reset))return false;
    prior={s.manager,s.vehicle,s.body,start};return true;
}
enum class Fault { none,not_armed,not_authorized,owner_changed,bad_state,bad_clock,stopped,policy_failed,bad_controls };
using Infer=bool(*)(void*,const PhysicsTick&,Controls&) noexcept;
inline bool valid(Controls c) noexcept {
    return std::isfinite(c.gas)&&std::isfinite(c.brake)&&std::isfinite(c.steer)&&
        (c.gas==0.f||c.gas==1.f)&&(c.brake==0.f||c.brake==1.f)&&std::abs(c.steer)<=1.f;
}
inline bool valid(const PhysicsTick& s) noexcept {
    if(!s.manager||!s.vehicle||!s.body||!s.owner_verified||!s.race_running||
       !std::isfinite(s.interval)||s.interval<=0.f||s.interval>.010001f)return false;
    for(float value:s.rigid)if(!std::isfinite(value)||std::abs(value)>100000.f)return false;
    for(int row=0;row<3;++row)for(int other=0;other<3;++other){
        float dot{};for(int k=0;k<3;++k)dot+=s.rigid[row*3+k]*s.rigid[other*3+k];
        if(std::abs(dot-(row==other?1.f:0.f))>.02f)return false;
    }
    float qnorm{};for(int k=12;k<16;++k)qnorm+=s.rigid[k]*s.rigid[k];
    return std::abs(qnorm-1.f)<.02f;
}
// A repeated local attempt must reappear at its verified spawn, at race zero,
// with the same physical manager/body. A respawn midrace cannot rearm it.
inline bool qualified_restart(const CandidateIdentity& prior,const PhysicsTick& s,
        std::uint32_t start,const std::array<float,3>& spawn) noexcept {
    if(!s.session_verified||!valid(s)||s.manager!=prior.manager||s.body!=prior.body||
       std::int32_t(start-prior.race_start_ms)<=0||std::uint32_t(s.timestamp_ms-start)>20)return false;
    float distance{};for(int k=0;k<3;++k){const float d=s.rigid[9+k]-spawn[k];distance+=d*d;}
    return distance<2.25f;
}
// Called exclusively by the game's physics consumer, immediately before it
// consumes +0x98/+0x9c/+0xa0. No worker-thread polling or peripheral output.
class Controller {
    PhysicsTick binding_{};Infer infer_{};void* context_{};
    Controls held_{};bool armed_{},has_tick_{};std::uint32_t last_{},decisions_{},ticks_{},decision_ticks_{5};
    Fault fault_=Fault::not_armed;
public:
    bool arm(const PhysicsTick& s,Infer infer,void* context,std::uint32_t decision_ticks=5) noexcept {
        stop();if(!s.session_verified){fault_=Fault::not_authorized;return false;}
        if(decision_ticks!=1&&decision_ticks!=5){fault_=Fault::bad_clock;return false;}
        if(!valid(s)||!infer){fault_=Fault::bad_state;return false;}
        binding_=s;infer_=infer;context_=context;armed_=true;has_tick_=false;
        decisions_=ticks_=0;decision_ticks_=decision_ticks;fault_=Fault::none;return true;
    }
    void stop() noexcept {armed_=false;held_={};fault_=Fault::stopped;}
    Fault fault()const noexcept{return fault_;}
    std::uint32_t decisions()const noexcept{return decisions_;}
    std::uint32_t ticks()const noexcept{return ticks_;}
    const PhysicsTick& binding()const noexcept{return binding_;}
    Controls before_consume(const PhysicsTick& s,bool stop_requested=false) noexcept {
        auto fail=[&](Fault fault){armed_=false;held_={};fault_=fault;return held_;};
        if(!armed_)return {};
        if(stop_requested)return fail(Fault::stopped);
        if(!s.session_verified)return fail(Fault::not_authorized);
        if(s.manager!=binding_.manager||s.vehicle!=binding_.vehicle||s.body!=binding_.body)
            return fail(Fault::owner_changed);
        if(!valid(s))return fail(Fault::bad_state);
        if(has_tick_){
            const auto delta=std::int32_t(s.timestamp_ms-last_);
            if(!delta)return held_; // Adaptive substeps share the macro tick.
            if(delta!=10)return fail(Fault::bad_clock);
        }
        last_=s.timestamp_ms;has_tick_=true;
        if(ticks_%decision_ticks_==0){
            Controls next{};if(!infer_(context_,s,next))return fail(Fault::policy_failed);
            if(!valid(next))return fail(Fault::bad_controls);
            next.steer=std::round(next.steer*127.f)/127.f;held_=next;++decisions_;
        }
        ++ticks_;return held_;
    }
};
}
