// Neural BC initializer for native PPO, evaluated once on an independent run.
#include "tm2020/rl.hpp"
#include "tm2020/driving_features.hpp"
#include "tm2020/route_controller.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <numeric>
#include <stdexcept>
struct Example{std::array<double,8> x;double steer;};
std::vector<Example> examples(const tm2020::Replay& replay,const tm2020::RoutePlan& route){
    std::vector<Example> rows;
    for(const auto& s:replay.states)if(s.time_ms>=0&&s.time_ms<=replay.finish_ms){
        rows.push_back({tm2020::driving_features(route,s),tm2020::analog_steer_from_raw(replay.input_at(s.time_ms).steer_raw)});
    }
    if(rows.size()<100)throw std::runtime_error("Insufficient race observations");return rows;
}
double mae(const tm2020::rl::ActorCritic& p,const std::vector<Example>& rows,int split=-1){
    double sum=0;std::size_t n=0;
    for(std::size_t i=0;i<rows.size();i++)if(split<0||int(i%5==0)==split){
        sum+=std::abs(p.deterministic(rows[i].x).action[0]-rows[i].steer);n++;
    }
    return sum/n;
}
int main(int argc,char** argv)try{
    if(argc!=6)throw std::invalid_argument("ppo_warmstart reference.tmreplay fit.tmreplay heldout.tmreplay output.tmppo metrics.csv");
    const auto reference=tm2020::Replay::load(argv[1]),fit=tm2020::Replay::load(argv[2]),test=tm2020::Replay::load(argv[3]);
    if(reference.uid!=fit.uid||reference.uid!=test.uid)throw std::invalid_argument("Reference and evaluation must belong to same map UID");
    if(std::filesystem::equivalent(argv[1],argv[2])||std::filesystem::equivalent(argv[2],argv[3])||std::filesystem::equivalent(argv[1],argv[3]))
        throw std::invalid_argument("Reference, fit and heldout must be separate runs");
    const tm2020::RoutePlan route(reference);const auto data=examples(fit,route);
    tm2020::rl::ActorCritic policy(8,1,32,2026),best=policy;
    auto& weights=policy.actor.parameters;std::vector<double> m(weights.size()),v(weights.size());
    std::vector<std::size_t> order;for(std::size_t i=0;i<data.size();i++)if(i%5)order.push_back(i);
    std::mt19937_64 rng(77);std::size_t updates=0,best_epoch=0;double best_validation=mae(policy,data,1);
    for(std::size_t epoch=0;epoch<400;epoch++){
        std::shuffle(order.begin(),order.end(),rng);
        for(std::size_t begin=0;begin<order.size();begin+=64){
            const auto end=std::min(order.size(),begin+64);std::vector<double> g(weights.size());
            for(std::size_t at=begin;at<end;at++){
                const auto& ex=data[order[at]];const auto y=std::tanh(policy.actor.forward(ex.x)[0]);
                const std::array dy{(y-ex.steer)*(1-y*y)/double(end-begin)};
                policy.actor.backward(ex.x,dy,g);
            }
            updates++;const auto b1=1-std::pow(.9,double(updates)),b2=1-std::pow(.999,double(updates));
            for(std::size_t k=0;k<g.size();k++){
                m[k]=.9*m[k]+.1*g[k];v[k]=.999*v[k]+.001*g[k]*g[k];
                weights[k]-=.001*(m[k]/b1)/(std::sqrt(v[k]/b2)+1e-8);
            }
        }
        const auto validation=mae(policy,data,1);
        if(validation<best_validation){best_validation=validation;best=policy;best_epoch=epoch+1;}
    }
    // Heldout data is constructed/evaluated only after model selection.
    const auto heldout=examples(test,route);const double heldout_mae=mae(best,heldout);
    double neutral=0,pursuit=0;std::size_t i=0;
    for(const auto& s:test.states)if(s.time_ms>=0&&s.time_ms<=test.finish_ms){
        neutral+=std::abs(heldout[i].steer);
        pursuit+=std::abs(tm2020::propose_reference_controls(route,s,{40.,-7.5}).steer-heldout[i].steer);i++;
    }
    neutral/=i;pursuit/=i;best.save(argv[4],tm2020::driving_observation_schema);
    std::ofstream out(argv[5]);out<<"fit_samples,heldout_samples,best_epoch,fit_internal_validation_mae,heldout_neural_mae,heldout_pursuit_mae,heldout_neutral_mae,game_performance_verified\n"
        <<data.size()<<','<<heldout.size()<<','<<best_epoch<<','<<best_validation<<','<<heldout_mae<<','<<pursuit<<','<<neutral<<",false\n";
    if(!out)throw std::runtime_error("Cannot write metrics");
    std::cout<<"NATIVE_NEURAL_BC fit="<<data.size()<<" heldout="<<heldout.size()<<" selected_epoch="<<best_epoch
             <<" heldout_steer_mae="<<heldout_mae<<" pursuit_mae="<<pursuit<<" neutral_mae="<<neutral
             <<" no_heldout_model_selection=true no_target_future_inputs=true game_strength_unverified=true\n";
}catch(const std::exception& e){std::cerr<<"BC_WARMSTART_ERROR "<<e.what()<<'\n';return 1;}
