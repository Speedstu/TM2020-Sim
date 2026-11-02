// Configured initial distribution, not a learned or race-qualified policy.
#include "tm2020/rl.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <iostream>
#include <random>
#include <stdexcept>

void initialize(tm2020::rl::ActorCritic& policy){
    auto& actor=policy.actor;
    if(actor.outputs!=3)throw std::invalid_argument("Headless controls require three actions");
    const auto base=actor.hidden*(actor.inputs+1);
    std::fill(actor.parameters.begin()+base,actor.parameters.end(),0.0);
    const std::array means{2.0,-2.0,0.0};
    for(std::size_t i=0;i<3;++i)actor.parameters.at(base+actor.outputs*actor.hidden+i)=means[i];
    policy.log_std={-1.5,-1.5,-2.3};
}

int main(int argc,char**argv)try{
    const bool test=argc==2&&std::string(argv[1])=="--self-test";
    if(!test&&argc!=7)throw std::invalid_argument("init_headless_policy observations actions hidden seed schema output.checkpoint");
    const auto nx=test?233:std::stoul(argv[1]),na=test?3:std::stoul(argv[2]),hidden=test?128:std::stoul(argv[3]);
    const auto seed=test?2026:std::stoull(argv[4]);
    if(!nx||nx>4096||na!=3||hidden<8||hidden>256)throw std::invalid_argument("Invalid headless architecture");
    tm2020::rl::ActorCritic policy(nx,na,hidden,seed);initialize(policy);
    for(double input:{0.0,1.0,-3.0}){
        const auto result=policy.deterministic(std::vector<double>(nx,input));
        if(std::abs(result.action[0]-std::tanh(2.0))>1e-14||std::abs(result.action[1]+std::tanh(2.0))>1e-14||result.action[2]!=0)
            throw std::runtime_error("Initial action distribution differs");
    }
    if(test){std::cout<<"PASS HEADLESS_INITIAL_DISTRIBUTION configured_means=true learned=false\n";return 0;}
    if(std::filesystem::exists(argv[6]))throw std::invalid_argument("Initializer never overwrites a checkpoint");
    tm2020::rl::PpoTrainer trainer(policy,{},seed);std::mt19937_64 sampler(seed);
    trainer.save_checkpoint(argv[6],argv[5],sampler);
    std::cout<<"SAVED CONFIGURED INITIAL DISTRIBUTION optimizer_steps=0 learned=false\n";
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
