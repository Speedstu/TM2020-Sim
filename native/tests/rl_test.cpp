#include "tm2020/rl.hpp"
#include "tm2020/realtime_rollout.hpp"
#include "tm2020/visual_state.hpp"
#include "tm2020/observation_history.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
void check(bool b,const char* msg){if(!b)throw std::runtime_error(msg);}
int main(int argc,char** argv)try{
    if(argc!=2)throw std::invalid_argument("rl_test output.tmppo");
    {
        tm2020::rl::ObservationHistory history(2,3);const std::array a{1.,2.},b{3.,4.},c{5.,6.};
        history.reset(a);history.push(b);history.push(c);
        check(history.values==std::vector<double>({1.,2.,3.,4.,5.,6.}),"Causal frame order differs");
        history.reset(c);check(history.values==std::vector<double>({5.,6.,5.,6.,5.,6.}),"History leaked across resets");
        tm2020::rl::ObservationHistory single(2,1);single.reset(a);single.push(b);
        check(single.values==std::vector<double>({3.,4.}),"Legacy history-one behavior changed");
        tm2020::rl::ObservationHistory five(2,5);five.reset(a);five.push(b);five.push(c);
        check(five.values==std::vector<double>({1.,2.,1.,2.,1.,2.,3.,4.,5.,6.}),"Five-frame order differs");
        check(tm2020::rl::observation_frames(240)==5,"Policy history shape differs");
        bool rejected=false;try{history.push(std::array{1.});}catch(const std::invalid_argument&){rejected=true;}
        check(rejected,"Wrong observation width accepted");
    }
    std::mt19937_64 rng(17);
    tm2020::rl::Network net(3,4,2,rng);
    const std::array x{.2,-.7,1.1};
    const std::array dy{.4,-.3};
    std::vector<double> gradient(net.parameters.size());net.backward(x,dy,gradient);
    double maximum_error=0;
    for(std::size_t i=0;i<gradient.size();i++){
        const double old=net.parameters[i],epsilon=1e-6;
        net.parameters[i]=old+epsilon;auto hi=net.forward(x);
        net.parameters[i]=old-epsilon;auto lo=net.forward(x);net.parameters[i]=old;
        const double numerical=((hi[0]-lo[0])*dy[0]+(hi[1]-lo[1])*dy[1])/(2*epsilon);
        maximum_error=std::max(maximum_error,std::abs(numerical-gradient[i]));
    }
    check(maximum_error<1e-8,"MLP finite difference gradient failed");
    std::vector<tm2020::rl::Transition> boundary(4);
    for(auto& t:boundary){t.reward=1;t.old_value=2;t.next_value=3;}
    boundary[0].terminated=true;boundary[1].truncated=true;
    const auto gae=tm2020::rl::generalized_advantage(boundary,2,.9,.8);
    check(std::abs(gae[0].target-1)<1e-12,"Termination bootstrapped");
    check(std::abs(gae[1].target-3.7)<1e-12,"Truncation lost final bootstrap or leaked reset advantage");
    check(std::abs(gae[2].target-3.7)<1e-12,"Rollout last observation bootstrap failed");
    boundary[1].elapsed_steps=2.;
    const auto timed_gae=tm2020::rl::generalized_advantage(boundary,2,.9,.8);
    check(std::abs(timed_gae[1].target-3.43)<1e-12,"Real-time duration discount failed");
    {
        tm2020::rl::ActorCritic behavior(1,1,16,31);
        tm2020::rl::RealtimeResidualRollout collector(behavior,53);
        const auto first=collector.observe(std::array{.1},0xfffffff0u,0,0);
        const auto held=collector.observe(std::array{.2},0x40,1,0);
        check(first==held&&collector.transitions().empty(),"Residual action was resampled before decision boundary");
        (void)collector.observe(std::array{.2},0x90,2,1);
        check(collector.transitions().size()==1,"Completed real-time interval was lost");
        const auto& t=collector.transitions()[0];
        check(std::abs(t.elapsed_steps-1.6)<1e-12&&t.observation[0]==.1&&
            std::abs(t.next_value-behavior.value(std::array{.2}))<1e-12,"Timed bootstrap observation/duration wrong");
        check(std::abs(t.old_log_probability-behavior.log_probability(t.observation,t.latent))<1e-12,"Behavior policy likelihood lost");
        collector.truncate();check(collector.transitions().size()==1&&collector.transitions()[0].truncated&&
            !collector.transitions()[0].terminated,"Partial real-time rollout was mislabeled terminal");
        tm2020::rl::PpoTrainer behavior_trainer(behavior);behavior_trainer.update(collector.transitions(),1);
    }
    // A complete reflected fixture and malformed values; no live game needed.
    std::array<std::byte,tm2020::live::visual_state_bytes> raw{};
    auto put=[&](std::size_t at,auto value){std::memcpy(raw.data()+at,&value,sizeof(value));};
    put(0x50,1200.f);put(0x54,34.f);put(0x58,1360.f);put(0x5c,2.f);put(0x64,-10.f);
    put(0x88,(1u<<20)|(1u<<23));put(0x1a4,std::int32_t(2));put(0x14,1.f);
    put(0x2c,1.f);put(0x3c,1.f);put(0x4c,1.f);
    auto state=tm2020::live::decode_visual_state(raw);
    check(state&&state->ground_contact&&state->engine_on&&state->gear==2&&state->position.z==1360&&state->world_velocity.z==-10,"Reflected decoder offsets/masks failed");
    check(state->rotation_matrix_is_orthonormal,"Visual rotation matrix validation failed");
    put(0x10,std::numeric_limits<float>::quiet_NaN());
    check(!tm2020::live::decode_visual_state(raw),"NaN visual state accepted");
    tm2020::rl::ActorCritic policy(1,1,16,5);
    {
        const std::array observation{.3},latent{.6};const double epsilon=1e-6;
        const double mu=policy.actor.forward(observation)[0];
        const double expected=(latent[0]-mu)*std::exp(-2*policy.log_std[0]);
        auto& bias=policy.actor.parameters.back();const double old=bias;
        bias=old+epsilon;const auto hi=policy.log_probability(observation,latent);
        bias=old-epsilon;const auto lo=policy.log_probability(observation,latent);bias=old;
        check(std::abs((hi-lo)/(2*epsilon)-expected)<1e-7,"Squashed Gaussian score gradient failed");
        std::array<double,1> output{};double value{};policy.predict_into(observation,output,value);
        check(output==std::array{policy.deterministic(observation).action[0]}&&value==policy.value(observation),"Allocation-free inference parity failed");
    }
    tm2020::rl::PpoConfig config;config.learning_rate=.001;config.epochs=6;config.minibatch=64;config.target_kl=.03;
    tm2020::rl::PpoTrainer trainer(policy,config,42);
    auto mse=[&](){double sum=0;for(int i=0;i<101;i++){
        const double target=-.8+1.6*i/100.;const auto a=policy.deterministic(std::array{target}).action[0];sum+=(a-target)*(a-target);
    }return sum/101.;};
    const double before=mse();std::uniform_real_distribution<double> context(-.8,.8);
    double last_kl=0;std::size_t iterations=0;
    for(;iterations<50&&mse()>.01;iterations++){
        std::vector<tm2020::rl::Transition> rollout;
        for(int i=0;i<1024;i++){
            std::vector<double> observation{context(rng)};const auto d=policy.sample(observation,rng);
            const double error=d.action[0]-observation[0];
            rollout.push_back({observation,d.latent,d.log_probability,d.value,1-error*error,0,true,false});
        }
        const auto result=trainer.update(rollout,16);last_kl=result.approx_kl;
        check(std::isfinite(last_kl)&&result.minibatches>0,"PPO update failed");
    }
    const double after=mse();check(after<before*.15&&after<.03,"PPO did not learn bounded contextual control");
    policy.save(argv[1],"synthetic_context_control_v1");std::string schema;
    auto reloaded=tm2020::rl::ActorCritic::load(argv[1],&schema);
    check(schema=="synthetic_context_control_v1","Model observation schema lost");
    check(policy.deterministic(std::array{.45}).action==reloaded.deterministic(std::array{.45}).action,"Checkpoint prediction changed");
    auto decision=policy.sample(std::array{.1},rng);
    std::vector<tm2020::rl::Transition> stale{{{.1},decision.latent,decision.log_probability+.1,decision.value,1,0,true,false}};
    bool rejected=false;try{trainer.update(stale,1);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected,"Off-policy data was accepted by PPO");
    const auto corrupt=std::filesystem::path(argv[1]).string()+".corrupt";
    std::filesystem::copy_file(argv[1],corrupt,std::filesystem::copy_options::overwrite_existing);
    {std::fstream f(corrupt,std::ios::in|std::ios::out|std::ios::binary);f.seekp(50);f.put('\x77');}
    rejected=false;try{auto bad=tm2020::rl::ActorCritic::load(corrupt);(void)bad;}catch(const std::invalid_argument&){rejected=true;}
    check(rejected,"Corrupt policy model accepted");std::filesystem::remove(corrupt);
    std::cout<<"PASS NATIVE_PPO gradient_max_error="<<maximum_error<<" bandit_mse_before="<<before
             <<" bandit_mse_after="<<after<<" iterations="<<iterations<<" last_kl="<<last_kl
             <<" termination_truncation=true checkpoint_parity=true corruption_denied=true game_performance_verified=false\n";
}catch(const std::exception& e){std::cerr<<"RL_TEST_ERROR "<<e.what()<<'\n';return 1;}
