// SPDX-License-Identifier: GPL-3.0-or-later
// Whole-file train/validation/test split; expert targets never enter inference.
#include "fast_training.h"
#include "tm2020/rl.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <sstream>
#include <stdexcept>
struct Example{std::array<double,TMFAST_OBSERVATIONS> x;double steer,baseline;};
double input_scale(size_t i){
    if((i>=3&&i<6)||(i>=21&&i<24))return 10.;
    if((i>=9&&i<12)||i==33)return 5.;
    if(i>=12&&i<15)return 2.;
    return 1.;
}
void export_policy(const tm2020::rl::ActorCritic& trained,const std::filesystem::path& path,const std::string& schema){
    auto deployed=trained;
    for(size_t i=0;i<deployed.actor.hidden;++i)for(size_t j=0;j<deployed.actor.inputs;++j)
        deployed.actor.parameters[i*deployed.actor.inputs+j]*=input_scale(j);
    deployed.save(path,schema);
}
std::vector<Example> load(const std::filesystem::path& file){
    std::ifstream in(file);std::string line;std::getline(in,line);
    if(!line.starts_with("observation_0,"))throw std::runtime_error("Unknown demonstration CSV");
    std::vector<Example> result;
    while(std::getline(in,line)){
        std::stringstream stream(line);std::string token;std::vector<double> values;
        while(std::getline(stream,token,',')){auto value=std::stod(token);if(!std::isfinite(value))throw std::runtime_error("Nonfinite demonstration");values.push_back(value);}
        if(values.size()!=TMFAST_OBSERVATIONS+3)throw std::runtime_error("Demonstration dimension differs");
        Example x{};std::copy_n(values.begin(),TMFAST_OBSERVATIONS,x.x.begin());x.steer=values[TMFAST_OBSERVATIONS];x.baseline=values[TMFAST_OBSERVATIONS+1];
        if(x.baseline!=x.x[31])throw std::runtime_error("Demonstration baseline differs");
        // Prevent an offline autoregressive shortcut: copying the expert's
        // previous steer or memorizing its clock is fragile in closed loop.
        for(size_t index:{24u,25u,26u,30u})x.x[index]=0.;
        for(size_t index=0;index<x.x.size();++index)x.x[index]*=input_scale(index);
        result.push_back(x);
    }
    if(result.size()<100)throw std::runtime_error("Not enough demonstration states");return result;
}
double loss(const tm2020::rl::ActorCritic& policy,const std::vector<Example>& rows,double residual){
    double sum=0;for(auto& row:rows){const auto a=policy.deterministic(row.x).action[0];
        const auto steer=std::clamp(row.baseline+residual*a,-1.,1.);sum+=(steer-row.steer)*(steer-row.steer);}
    return sum/rows.size();
}
int main(int argc,char**argv)try{
    if(argc!=7)throw std::runtime_error("fast_warmstart FIT.csv VALIDATION.csv TEST.csv OUTPUT RESIDUAL EPOCHS");
    for(int i=1;i<=3;++i)for(int j=i+1;j<=3;++j)if(std::filesystem::equivalent(argv[i],argv[j]))
        throw std::runtime_error("Use independent replay files");
    const std::filesystem::path output(argv[4]);if(std::filesystem::exists(output))throw std::runtime_error("Output must be new");
    const double residual=std::stod(argv[5]);const size_t epochs=std::stoul(argv[6]);
    if(residual<=0||residual>2||epochs==0||epochs>10000)throw std::runtime_error("Invalid bounded initializer");
    const auto fit=load(argv[1]),validation=load(argv[2]);
    std::filesystem::create_directories(output/"candidates");
    const auto schema=std::string(TMFAST_SCHEMA)+"|policy_actions=steering_residual1";
    tm2020::rl::ActorCritic policy(TMFAST_OBSERVATIONS,1,64,2026);
    const auto head=policy.actor.hidden*(policy.actor.inputs+1);
    std::fill(policy.actor.parameters.begin()+head,policy.actor.parameters.end(),0.);
    for(size_t i=0;i<policy.actor.hidden;++i)for(size_t index:{24u,25u,26u,30u})
        policy.actor.parameters[i*policy.actor.inputs+index]=0.;
    policy.log_std={-3.9};auto best=policy;double selected=loss(policy,validation,residual),initial=selected;size_t best_epoch=0;
    auto& weights=policy.actor.parameters;std::vector<double> m(weights.size()),v(weights.size());
    std::vector<size_t> order(fit.size());std::iota(order.begin(),order.end(),0);std::mt19937_64 rng(2026);
    size_t updates=0;
    for(size_t epoch=0;epoch<epochs;++epoch){
        std::shuffle(order.begin(),order.end(),rng);
        for(size_t at=0;at<order.size();at+=64){
            const auto end=std::min(at+64,order.size());std::vector<double> gradient(weights.size());
            for(size_t index=at;index<end;++index){
                const auto& row=fit[order[index]];const auto y=std::tanh(policy.actor.forward(row.x)[0]);
                const auto raw=row.baseline+residual*y,steer=std::clamp(raw,-1.,1.);
                const double derivative=std::abs(raw)<1.?(steer-row.steer)*residual*(1-y*y)/double(end-at):0.;
                const std::array upstream{derivative};policy.actor.backward(row.x,upstream,gradient);
            }
            updates++;const auto b1=1-std::pow(.9,double(updates)),b2=1-std::pow(.999,double(updates));
            for(size_t k=0;k<weights.size();++k){const auto g=gradient[k];m[k]=.9*m[k]+.1*g;v[k]=.999*v[k]+.001*g*g;
                weights[k]-=.0005*(m[k]/b1)/(std::sqrt(v[k]/b2)+1e-8);}
        }
        const auto current=loss(policy,validation,residual);
        if(current<selected){selected=current;best=policy;best_epoch=epoch+1;}
        if((epoch+1)%40==0)export_policy(policy,output/"candidates"/("epoch-"+std::to_string(epoch+1)+".tmppo"),schema);
    }
    const auto test=load(argv[3]);const auto heldout=loss(best,test,residual);
    export_policy(best,output/"policy.tmppo",schema);
    std::ofstream out(output/"report.json");out<<std::setprecision(17)<<"{\"fitRows\":"<<fit.size()<<",\"validationRows\":"<<validation.size()
        <<",\"testRows\":"<<test.size()<<",\"selectedEpoch\":"<<best_epoch<<",\"initialValidationSteerMse\":"<<initial
        <<",\"validationSteerMse\":"<<selected<<",\"testSteerMse\":"<<heldout<<",\"testUsedForSelection\":false,\"learnedActor\":true"
        <<",\"previousActionAndClockMaskedDuringImitation\":true,\"inputScalesFoldedIntoExportedActorWeights\":true}\n";
    std::cout<<"FAST_WARMSTART selected_epoch="<<best_epoch<<" validation="<<selected<<" test="<<heldout<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
