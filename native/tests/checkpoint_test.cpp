#include "tm2020/rl.hpp"
#include "tm2020/realtime_rollout.hpp"
#include <array>
#include <cmath>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::rl;
void check(bool b,const char* message){if(!b)throw std::runtime_error(message);}
std::vector<Transition> collect(const ActorCritic& p,std::mt19937_64& rng){
    std::vector<Transition> rows;
    for(int i=0;i<128;i++){
        std::vector<double> x{(i%13-6)/7.,(i%7-3)/4.};const auto d=p.sample(x,rng);
        const double error=d.action[0]-.6*x[0];
        rows.push_back({x,d.latent,d.log_probability,d.value,1-error*error,0,true,false});
    }return rows;
}
int main(int argc,char** argv)try{
    check(argc==2,"checkpoint_test file.train");const std::filesystem::path path(argv[1]);
    ActorCritic uninterrupted(2,1,16,19);PpoConfig c;c.epochs=3;c.minibatch=19;c.target_kl=10;
    PpoTrainer trainer(uninterrupted,c,31);std::mt19937_64 sampler(43);
    trainer.update(collect(uninterrupted,sampler),1);
    trainer.save_checkpoint(path,"checkpoint_fixture_v1",sampler);
    check(trainer.optimizer_steps()>0,"Fixture never updated Adam");
    ActorCritic resumed(2,1,16,999);PpoTrainer restored(resumed);std::mt19937_64 restored_sampler(999);
    restored.load_checkpoint(path,"checkpoint_fixture_v1",restored_sampler);
    check(trainer.optimizer_steps()==restored.optimizer_steps()&&sampler==restored_sampler,"Counters/RNG not restored");
    for(int round=0;round<3;round++){
        const auto a=collect(uninterrupted,sampler),b=collect(resumed,restored_sampler);
        check(a[127].latent==b[127].latent,"Rollout exploration RNG diverged");
        const auto ma=trainer.update(a,1),mb=restored.update(b,1);
        check(uninterrupted.actor.parameters==resumed.actor.parameters&&uninterrupted.critic.parameters==resumed.critic.parameters&&
            uninterrupted.log_std==resumed.log_std&&ma.approx_kl==mb.approx_kl&&ma.minibatches==mb.minibatches,
            "Resumed PPO differs from uninterrupted optimizer/shuffle sequence");
    }
    const auto original=resumed;const auto original_rng=restored_sampler;const auto original_steps=restored.optimizer_steps();
    auto unchanged=[&]{return resumed.actor.parameters==original.actor.parameters&&resumed.critic.parameters==original.critic.parameters&&
        resumed.log_std==original.log_std&&restored_sampler==original_rng&&restored.optimizer_steps()==original_steps;};
    bool rejected=false;try{restored.load_checkpoint(path,"wrong_schema",restored_sampler);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&unchanged(),"Schema rejection mutated training state");
    ActorCritic wrong(3,1,16);PpoTrainer wrong_trainer(wrong);
    rejected=false;try{wrong_trainer.load_checkpoint(path,"checkpoint_fixture_v1",restored_sampler);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&unchanged(),"Architecture mismatch accepted");
    auto corrupt=path;corrupt+=".corrupt";std::filesystem::copy_file(path,corrupt,std::filesystem::copy_options::overwrite_existing);
    {std::fstream f(corrupt,std::ios::in|std::ios::out|std::ios::binary);f.seekp(190);f.put('\x39');}
    rejected=false;try{restored.load_checkpoint(corrupt,"checkpoint_fixture_v1",restored_sampler);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&unchanged(),"Corruption rejection mutated training state");
    std::filesystem::resize_file(corrupt,50);
    rejected=false;try{restored.load_checkpoint(corrupt,"checkpoint_fixture_v1",restored_sampler);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&unchanged(),"Truncated checkpoint accepted");std::filesystem::remove(corrupt);
    trainer.update(collect(uninterrupted,sampler),1);
    restored.update(collect(resumed,restored_sampler),1);
    check(uninterrupted.actor.parameters==resumed.actor.parameters&&uninterrupted.critic.parameters==resumed.critic.parameters&&
        uninterrupted.log_std==resumed.log_std,"Rejected checkpoint changed hidden optimizer state");
    auto temporary=path;temporary+=".tmp";{std::ofstream f(temporary);f<<"retained crash artifact";}
    rejected=false;try{restored.save_checkpoint(path,"checkpoint_fixture_v1",restored_sampler);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected,"Existing recovery artifact overwritten");std::filesystem::remove(temporary);
    // Actual replacement must also retain the optimizer, not merely the policy.
    restored.save_checkpoint(path,"checkpoint_fixture_v1",restored_sampler);
    trainer.load_checkpoint(path,"checkpoint_fixture_v1",sampler);
    check(trainer.optimizer_steps()==restored.optimizer_steps()&&sampler==restored_sampler,"Atomic replacement lost current state");
    RealtimeResidualEvaluation evaluation(resumed);
    const auto weights=resumed.actor.parameters;
    const auto first=evaluation.observe(std::array{.2,-.1},0xfffffff0u);
    check(first==.2*resumed.deterministic(std::array{.2,-.1}).action[0],"Evaluation sampled stochastic action");
    check(first==evaluation.observe(std::array{-.2,.1},0x40),"Evaluation did not hold decision interval");
    check(evaluation.observe(std::array{-.2,.1},0x90)==.2*resumed.deterministic(std::array{-.2,.1}).action[0],"Evaluation boundary wrong");
    check(weights==resumed.actor.parameters,"Evaluation changed model");
    rejected=false;try{evaluation.observe(std::array{.2,-.1},0x80);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected,"Evaluation accepted backward clock");
    std::cout<<"PASS CHECKPOINT bit_exact_resumed_updates=4 adam_steps="<<restored.optimizer_steps()
        <<" sampler_rng=true shuffle_rng=true atomic_replace=true invalid_load_transactional=true deterministic_evaluation=true\n";
}catch(const std::exception& e){std::cerr<<"CHECKPOINT_TEST_ERROR "<<e.what()<<'\n';return 1;}
