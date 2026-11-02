#include "tm2020/realtime_rollout.hpp"
#include <algorithm>
#include <bit>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <stdexcept>
namespace tm2020::rl {
RealtimeResidualRollout::RealtimeResidualRollout(const ActorCritic& policy,std::uint64_t seed):policy_(policy),rng_(seed){
    if(policy.actor.outputs!=1)throw std::invalid_argument("Residual policy requires one steering action");
}
RealtimeResidualRollout::RealtimeResidualRollout(const ActorCritic& policy,const std::mt19937_64& rng):RealtimeResidualRollout(policy){rng_=rng;}
double RealtimeResidualEvaluation::observe(std::span<const double> x,std::uint32_t clock){
    if(policy_.actor.outputs!=1||x.size()!=policy_.actor.inputs||
       !std::all_of(x.begin(),x.end(),[](double v){return std::isfinite(v);}))
        throw std::invalid_argument("Invalid residual evaluation observation/architecture");
    if(last_clock_){
        const auto elapsed=std::bit_cast<std::int32_t>(clock-*last_clock_);
        if(elapsed<0)throw std::invalid_argument("Evaluation clock went backward");
        if(elapsed<100)return correction_;
    }
    last_clock_=clock;correction_=.2*policy_.deterministic(x).action[0];return correction_;
}
double RealtimeResidualRollout::observe(std::span<const double> x,std::uint32_t clock,double progress,double error){
    if(closed_||!std::isfinite(progress)||!std::isfinite(error)||error<0)throw std::invalid_argument("Invalid/closed real-time rollout");
    if(x.size()!=policy_.actor.inputs||!std::all_of(x.begin(),x.end(),[](double value){return std::isfinite(value);}))
        throw std::invalid_argument("Invalid real-time observation");
    if(pending_){
        const auto elapsed=std::bit_cast<std::int32_t>(clock-pending_->clock);
        if(elapsed<0)throw std::invalid_argument("Visual clock went backward during rollout");
        if(elapsed<100)return correction_;
        auto& t=pending_->transition;
        t.elapsed_steps=elapsed/100.;
        t.reward=.05*std::clamp(progress-pending_->progress,-20.,20.)-
                 (.002*error+.001+.001*pending_->action*pending_->action)*t.elapsed_steps;
        t.next_value=policy_.value(x);rows_.push_back(std::move(t));
    }
    const auto d=policy_.sample(x,rng_);
    Pending p{{std::vector<double>(x.begin(),x.end()),d.latent,d.log_probability,d.value,0,0,false,false},clock,progress,d.action[0]};
    pending_=std::move(p);correction_=.2*d.action[0];return correction_;
}
void RealtimeResidualRollout::truncate(){
    if(!rows_.empty())rows_.back().truncated=true;
    pending_.reset();closed_=true;
}
void RealtimeResidualRollout::write_csv(const std::filesystem::path& path) const {
    if(!closed_)throw std::logic_error("Close real-time rollout before exporting");
    std::ofstream out(path);if(!out)throw std::runtime_error("Cannot export real-time rollout");
    out<<"old_log_probability,old_value,reward,next_value,terminated,truncated,elapsed_steps,latent";
    for(std::size_t j=0;j<policy_.actor.inputs;j++)out<<",observation_"<<j;
    out<<'\n'<<std::setprecision(17);
    for(const auto& t:rows_){
        out<<t.old_log_probability<<','<<t.old_value<<','<<t.reward<<','<<t.next_value<<','<<t.terminated<<','<<t.truncated<<','<<t.elapsed_steps<<','<<t.latent[0];
        for(double x:t.observation)out<<','<<x;
        out<<'\n';
    }
    out.flush();if(!out)throw std::runtime_error("Real-time rollout write failed");
}
}
