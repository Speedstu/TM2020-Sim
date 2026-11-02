// SPDX-License-Identifier: GPL-3.0-or-later
// Persistent in-process vector environments and native PPO; no Python runtime.
#include "fast_training.h"
#include "tm2020/rl.hpp"
#include <algorithm>
#include <array>
#include <atomic>
#include <barrier>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <numeric>
#include <random>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static_assert(sizeof(tmfast_state)==544);
void require(bool ok,const std::string& message){if(!ok)throw std::runtime_error(message);}
struct Api{
    void* library{};
#define API(name) decltype(&tmfast_##name) name{};
    API(version) API(last_error) API(open) API(clone) API(configure) API(configure_planner) API(reset) API(reset_bank) API(bank_size) API(step) API(step_controls) API(close)
#undef API
    explicit Api(const fs::path& p){
        library=dlopen(fs::absolute(p).c_str(),RTLD_NOW|RTLD_LOCAL);
        require(library!=nullptr,"Cannot load native physics library");
#define LOAD(name) name=reinterpret_cast<decltype(name)>(dlsym(library,"tmfast_" #name));require(name!=nullptr,"Missing tmfast_" #name);
        LOAD(version) LOAD(last_error) LOAD(open) LOAD(clone) LOAD(configure) LOAD(configure_planner) LOAD(reset) LOAD(reset_bank) LOAD(bank_size) LOAD(step) LOAD(step_controls) LOAD(close)
#undef LOAD
        require(version()==TMFAST_API_VERSION,"Physics ABI differs");
    }
    ~Api(){if(library)dlclose(library);}
    void check(int code){if(code)throw std::runtime_error(last_error());}
};
struct Environment{
    Api* api{};tmfast_env handle{};
    Environment(Api& a,tmfast_env h):api(&a),handle(h){require(h!=nullptr,a.last_error());}
    ~Environment(){api->close(handle);}
    Environment(const Environment&)=delete;
};
using Action=std::array<double,3>;
class Workers{
    Api& api;std::vector<std::unique_ptr<Environment>>& envs;std::vector<Action>& actions;
    std::vector<tmfast_state>& states;std::vector<std::string> errors;
    const size_t count;const uint32_t repeat;std::barrier<> start,finish;
    bool stop=false;std::vector<std::jthread> threads;
public:
    Workers(Api& a,std::vector<std::unique_ptr<Environment>>& e,std::vector<Action>& ac,
            std::vector<tmfast_state>& s,size_t n,uint32_t r):api(a),envs(e),actions(ac),states(s),errors(e.size()),
            count(std::min(n,e.size())),repeat(r),start(count+1),finish(count+1){
        for(size_t w=0;w<count;++w)threads.emplace_back([this,w]{
            for(;;){start.arrive_and_wait();if(stop)break;
                for(size_t i=w;i<envs.size();i+=count){
                    const auto code=api.step(envs[i]->handle,actions[i].data(),repeat,&states[i]);
                    errors[i]=code?api.last_error():"";
                }
                finish.arrive_and_wait();
            }
        });
    }
    ~Workers(){stop=true;start.arrive_and_wait();for(auto& thread:threads)thread.join();}
    void step(){start.arrive_and_wait();finish.arrive_and_wait();for(auto& e:errors)require(e.empty(),"Physics worker: "+e);}
};
struct Args{
    std::map<std::string,std::string> values;
    Args(int argc,char**argv){
        for(int i=1;i<argc;i+=2){require(i+1<argc,"Every option needs a value");
            std::string key=argv[i];require(key.starts_with("--"),"Expected --option");
            require(values.emplace(key,argv[i+1]).second,"Duplicate option");}
        const std::vector<std::string> allowed{"--library","--map","--packs","--route","--output","--mode",
            "--environments","--threads","--updates","--rollout","--horizon","--repeat","--hidden","--seed",
            "--lookahead","--gain","--residual","--resume","--model","--actions","--epochs","--learning-rate","--trials","--eval-every",
            "--curriculum","--bank-probability","--bank-decay","--planner","--noise"};
        for(auto& [k,v]:values)require(std::find(allowed.begin(),allowed.end(),k)!=allowed.end(),"Unknown option "+k);
    }
    std::string get(const std::string& k,const std::string& fallback="")const{
        auto i=values.find(k);return i==values.end()?fallback:i->second;
    }
    size_t number(const std::string& k,size_t fallback)const{return std::stoull(get(k,std::to_string(fallback)));}
    double real(const std::string& k,double fallback)const{return std::stod(get(k,std::to_string(fallback)));}
    fs::path path(const std::string& k)const{auto p=get(k);require(!p.empty(),"Missing "+k);return fs::absolute(p);}
};
std::string policy_schema(size_t actions,bool planner){return std::string(planner?TMFAST_PLANNER_SCHEMA:TMFAST_SCHEMA)+"|policy_actions="+(actions==1?"steering_residual1":"pedals_residual3");}
Action command(const std::vector<double>& a){return a.size()==1?Action{1.,-1.,a[0]}:Action{a[0],a[1],a[2]};}
struct Evaluation{size_t trials=0,finishes=0;double reward=0,mean_ms=0,best_ms=1e9;};
Evaluation evaluate(Api& api,tmfast_env handle,const tm2020::rl::ActorCritic* policy,size_t trials,uint32_t repeat,uint32_t seed){
    Evaluation result;
    std::vector<std::unique_ptr<Environment>> worlds;
    for(size_t trial=0;trial<trials;++trial)worlds.push_back(std::make_unique<Environment>(api,api.clone(handle)));
    std::vector<Evaluation> outcomes(trials);std::vector<std::string> errors(trials);
    std::vector<std::jthread> threads;
    for(size_t worker=0;worker<std::min(size_t(16),trials);++worker)threads.emplace_back([&,worker]{
      for(size_t trial=worker;trial<trials;trial+=16)try{
        const auto handle=worlds[trial]->handle;
        tmfast_state state{};api.check(api.reset(handle,seed+trial,&state));double score=0;
        // Deterministic start perturbations, independent of policy training RNG.
        if(trial>0){
            std::mt19937_64 perturb(seed+trial);
            const auto warm=8+perturb()%15,duration=1+perturb()%5;
            const double amplitude=(trial%2?1.:-1.)*(0.15+double(perturb()%3500)/10000.);
            for(size_t k=0;k<warm;++k){api.check(api.step(handle,Action{1,-1,0}.data(),repeat,&state));score+=state.reward;}
            for(size_t k=0;k<duration;++k){
                const auto steer=int(std::round(std::clamp(state.observation[31]+amplitude,-1.,1.)*127.));
                const std::array<float,3> controls{1,0,float(steer)/127.f};
                api.check(api.step_controls(handle,controls.data(),repeat,&state));score+=state.reward;
            }
        }
        while(!state.terminated&&!state.truncated){
            const auto action=policy?command(policy->deterministic(state.observation).action):Action{1,-1,0};
            api.check(api.step(handle,action.data(),repeat,&state));score+=state.reward;
        }
        outcomes[trial]={1,state.terminated,score,state.terminated?double(state.finish_ms):0.,state.terminated?double(state.finish_ms):1e9};
      }catch(const std::exception& e){errors[trial]=e.what();}
    });
    for(auto& thread:threads)thread.join();
    for(size_t i=0;i<trials;++i){require(errors[i].empty(),errors[i]);const auto& x=outcomes[i];
        result.trials+=x.trials;result.finishes+=x.finishes;result.reward+=x.reward;result.mean_ms+=x.mean_ms;result.best_ms=std::min(result.best_ms,x.best_ms);}
    if(result.finishes)result.mean_ms/=result.finishes;else result.mean_ms=1e9;
    result.reward/=trials;return result;
}
void json_eval(std::ostream& out,const Evaluation& e){out<<"{\"trials\":"<<e.trials<<",\"finishes\":"<<e.finishes
    <<",\"meanFinishMs\":"<<(e.finishes?e.mean_ms:-1)<<",\"bestFinishMs\":"<<(e.finishes?e.best_ms:-1)<<",\"meanReward\":"<<e.reward<<'}';}
void rollout_csv(const fs::path& file,const std::vector<tm2020::rl::Transition>& rows,size_t nx,size_t na){
    std::ofstream out(file);out<<"old_log_probability,old_value,reward,next_value,terminated,truncated,elapsed_steps";
    for(size_t j=0;j<na;++j)out<<",latent_"<<j;
    for(size_t j=0;j<nx;++j)out<<",observation_"<<j;
    out<<'\n'<<std::setprecision(17);
    for(auto& r:rows){out<<r.old_log_probability<<','<<r.old_value<<','<<r.reward<<','<<r.next_value<<','
        <<r.terminated<<','<<r.truncated<<','<<r.elapsed_steps;
        for(auto v:r.latent)out<<','<<v;
        for(auto v:r.observation)out<<','<<v;
        out<<'\n';}
    require(bool(out),"Rollout evidence write failed");
}
struct PhysicalRow{uint32_t env,episode,bank,reserved;tmfast_state before,after;Action action;};
static_assert(sizeof(PhysicalRow)==1128);
int main(int argc,char**argv)try{
    Args args(argc,argv);const auto mode=args.get("--mode","train");
    const auto output=args.path("--output");require(!fs::exists(output),"Output must be new");fs::create_directories(output);
    const auto n=args.number("--environments",16),threads=args.number("--threads",16),updates=args.number("--updates",100),
        length=args.number("--rollout",256),horizon=args.number("--horizon",4000),repeat=args.number("--repeat",5),
        width=args.number("--hidden",64),seed=args.number("--seed",2026),na=args.number("--actions",1),epochs=args.number("--epochs",4),eval_every=args.number("--eval-every",5);
    require(n>=1&&n<=64&&threads>=1&&threads<=64&&length>=1&&length<=4096&&n*length<=131072&&
        updates>=1&&updates<=100000&&horizon>=1&&horizon<=100000&&repeat>=1&&repeat<=100&&width>=8&&width<=256&&
        (na==1||na==3)&&epochs>=1&&epochs<=32&&eval_every>=1&&eval_every<=1000,"Invalid bounded training options");
    const auto look=args.real("--lookahead",10),gain=args.real("--gain",3),residual=args.real("--residual",.35);
    const bool curriculum=args.number("--curriculum",0)!=0;
    const auto bank_decay=args.number("--bank-decay",200);
    const double bank_probability=args.real("--bank-probability",.7);
    require(bank_decay>0 && bank_probability>=0 && bank_probability<=1,"Invalid reset curriculum");
    const bool planner=args.number("--planner",0)!=0;
    Api api(args.path("--library"));
    Environment root(api,api.open(args.path("--map").c_str(),args.path("--packs").c_str(),args.path("--route").c_str(),horizon));
    api.check(api.configure(root.handle,look,gain,residual));
    api.check(api.configure_planner(root.handle,planner));
    const auto schema=policy_schema(na,planner);
    tm2020::rl::ActorCritic policy(TMFAST_OBSERVATIONS,na,width,seed);
    auto base=policy.actor.hidden*(policy.actor.inputs+1);
    std::fill(policy.actor.parameters.begin()+base,policy.actor.parameters.end(),0.);
    if(na==3){policy.actor.parameters[base+na*width]=2;policy.actor.parameters[base+na*width+1]=-2;}
    const auto noise=args.real("--noise",.035);require(noise>0 && noise<=1,"Invalid exploration scale");
    policy.log_std.assign(na,std::log(noise/std::max(.01,residual)));
    if(!args.get("--model").empty()){
        std::string loaded;policy=tm2020::rl::ActorCritic::load(args.path("--model"),&loaded);
        require(loaded==schema&&policy.actor.outputs==na&&policy.actor.inputs==TMFAST_OBSERVATIONS,"Policy schema differs");
    }
    tm2020::rl::PpoConfig cfg;cfg.gamma=.999;cfg.lambda=.97;cfg.epochs=epochs;cfg.minibatch=256;
    cfg.learning_rate=args.real("--learning-rate",.0003);cfg.target_kl=.02;
    tm2020::rl::PpoTrainer trainer(policy,cfg,seed+1);std::mt19937_64 sampler(seed+2);
    if(!args.get("--resume").empty())trainer.load_checkpoint(args.path("--resume"),schema,sampler);
    {
        std::ofstream cfgout(output/"config.json");cfgout<<std::setprecision(17)<<"{\"schema\":"<<std::quoted(schema)
            <<",\"explorationPhysicalStd\":"<<noise<<",\"planner\":"<<(planner?"true":"false")<<",\"observations\":"<<TMFAST_OBSERVATIONS<<",\"physicsApiVersion\":"<<TMFAST_API_VERSION
            <<",\"initialModel\":"<<std::quoted(args.get("--model"))<<",\"resumedCheckpoint\":"<<std::quoted(args.get("--resume"))
            <<",\"map\":"<<std::quoted(args.path("--map").string())<<",\"route\":"<<std::quoted(args.path("--route").string())
            <<",\"library\":"<<std::quoted(args.path("--library").string())<<",\"environments\":"<<n<<",\"threads\":"<<threads
            <<",\"rolloutLength\":"<<length<<",\"horizon\":"<<horizon<<",\"repeat\":"<<repeat
            <<",\"hidden\":"<<width<<",\"actions\":"<<na<<",\"seed\":"<<seed<<",\"lookahead\":"<<look
            <<",\"gain\":"<<gain<<",\"residual\":"<<residual<<",\"rewardScale\":0.01,\"timePenalty\":0.01,\"crossTrackPenalty\":0.000005,\"geometricRouteAssistance\":true"
            <<",\"demonstrationResetCurriculum\":"<<(curriculum?"true":"false")<<",\"bankProbability\":"<<bank_probability
            <<",\"bankDecayUpdates\":"<<bank_decay<<",\"resetSnapshots\":"<<api.bank_size(root.handle)
            <<",\"evaluationPerturbation\":\"physical_i8_steering_v1\",\"evaluationStartsAtZero\":true"
            <<",\"recordedControlsUsedInObservations\":false,\"completeExactPhysicsQualified\":false}\n";
    }
    if(mode=="eval"){
        const auto trials=args.number("--trials",10);require(trials>=1&&trials<=100,"Invalid evaluation trials");
        auto baseline=evaluate(api,root.handle,nullptr,trials,repeat,seed+100000);
        auto candidate=evaluate(api,root.handle,&policy,trials,repeat,seed+100000);
        std::ofstream out(output/"report.json");out<<std::setprecision(17)<<"{\"baseline\":";json_eval(out,baseline);
        out<<",\"candidate\":";json_eval(out,candidate);out<<"}\n";
        std::cout<<"EVALUATION baseline="<<baseline.finishes<<'/'<<trials<<" mean_ms="<<baseline.mean_ms
            <<" candidate="<<candidate.finishes<<'/'<<trials<<" mean_ms="<<candidate.mean_ms<<'\n';return 0;
    }
    require(mode=="train"||mode=="bench","Unknown mode");
    std::vector<std::unique_ptr<Environment>> envs;std::vector<Action> actions(n);
    std::vector<tmfast_state> states(n);std::vector<uint32_t> episodes(n),banks(n);
    const auto bank_count=api.bank_size(root.handle);
    auto reset_env=[&](size_t i,size_t update){
        uint64_t hash=seed+i+uint64_t(episodes[i])*n+uint64_t(update)*0x9e3779b97f4a7c15ULL;
        hash=(hash^(hash>>30))*0xbf58476d1ce4e5b9ULL;hash=(hash^(hash>>27))*0x94d049bb133111ebULL;hash^=hash>>31;
        const double probability=bank_probability*std::max(0.,1.-double(update)/bank_decay);
        banks[i]=curriculum && bank_count>1 && double(hash%1000000)/1000000.<probability?
            1+uint32_t((hash>>20)%(bank_count-1)):0;
        api.check(api.reset_bank(envs[i]->handle,uint32_t(seed+i+episodes[i]*n),banks[i],&states[i]));
    };
    for(size_t i=0;i<n;++i){envs.push_back(std::make_unique<Environment>(api,api.clone(root.handle)));reset_env(i,0);}
    Workers workers(api,envs,actions,states,threads,repeat);
    if(mode=="bench"){
        const auto start=Clock::now();uint64_t ticks=0,resets=0;
        for(size_t t=0;t<length;++t){std::fill(actions.begin(),actions.end(),Action{1,-1,0});workers.step();
            for(size_t i=0;i<n;++i){ticks+=states[i].advanced_ticks;if(states[i].terminated||states[i].truncated){
                reset_env(i,0);resets++;}}}
        auto elapsed=std::chrono::duration<double>(Clock::now()-start).count();
        std::ofstream out(output/"report.json");out<<std::setprecision(17)<<"{\"physicsTicks\":"<<ticks
            <<",\"seconds\":"<<elapsed<<",\"ticksPerSecond\":"<<ticks/elapsed<<",\"resets\":"<<resets<<"}\n";
        std::cout<<"FAST_BENCH ticks_per_second="<<ticks/elapsed<<" resets="<<resets<<'\n';return 0;
    }
    policy.save(output/"initial.tmppo",schema);trainer.save_checkpoint(output/"initial.checkpoint",schema,sampler);
    std::ofstream summary(output/"updates.csv");summary<<"update,transitions,physics_ticks,episodes,finishes,mean_finish_ms,collect_seconds,train_seconds,eval_finishes,eval_mean_ms,policy_loss,value_loss,kl,gradient_norm\n";
    summary<<std::setprecision(17);auto begin=Clock::now();uint64_t total=0,total_ticks=0;
    Evaluation best{};best.reward=-1e30;best.mean_ms=1e9;
    for(size_t update=0;update<updates;++update){
        if(fs::exists(output/"STOP")){
            std::cout<<"FAST_PPO stopped between complete updates; checkpoints retained"<<std::endl;break;
        }
        auto folder=output/("update-"+std::to_string(update));fs::create_directories(folder);
        policy.save(folder/"behavior.tmppo",schema);
        std::vector<tm2020::rl::Transition> rows;rows.reserve(n*length);
        std::ofstream physics(folder/"physics.bin",std::ios::binary);physics.write("TMFAST03",8);
        size_t completed=0,finishes=0;double finish_sum=0;uint64_t ticks=0;auto start=Clock::now();
        for(size_t t=0;t<length;++t){
            auto before=states;std::vector<tm2020::rl::Decision> decisions;decisions.reserve(n);
            for(size_t i=0;i<n;++i){decisions.push_back(policy.sample(before[i].observation,sampler));actions[i]=command(decisions.back().action);}
            workers.step();
            for(size_t i=0;i<n;++i){const auto& s=states[i];const auto& d=decisions[i];
                require(s.advanced_ticks>0&&s.advanced_ticks<=repeat,"Invalid physical duration");
                const auto boundary=bool(s.truncated)||(t+1==length&&!s.terminated);
                rows.push_back({{std::begin(before[i].observation),std::end(before[i].observation)},d.latent,
                    d.log_probability,d.value,s.reward*.01,policy.value(s.observation),bool(s.terminated),boundary,
                    double(s.advanced_ticks)/repeat});
                PhysicalRow evidence{uint32_t(i),episodes[i],banks[i],0,before[i],s,actions[i]};
                physics.write(reinterpret_cast<const char*>(&evidence),sizeof(evidence));ticks+=s.advanced_ticks;
                if(s.terminated||s.truncated){completed++;finishes+=s.terminated;if(s.terminated)finish_sum+=s.finish_ms;
                    episodes[i]++;reset_env(i,update);}
            }
        }
        physics.flush();require(bool(physics),"Physical rollout write failed");physics.close();
        const auto collected=std::chrono::duration<double>(Clock::now()-start).count();
        rollout_csv(folder/"rollout.csv",rows,TMFAST_OBSERVATIONS,na);
        start=Clock::now();const auto metrics=trainer.update(rows,n);
        const auto trained=std::chrono::duration<double>(Clock::now()-start).count();
        trainer.save_checkpoint(folder/"training.checkpoint",schema,sampler);policy.save(folder/"updated.tmppo",schema);
        const bool evaluated=update%eval_every==0 || update+1==updates;
        auto trial=evaluated?evaluate(api,root.handle,&policy,3,repeat,uint32_t(seed+50000)):Evaluation{};
        const bool improved=trial.finishes>best.finishes || (trial.finishes==best.finishes &&
            (trial.mean_ms<best.mean_ms || (trial.mean_ms==best.mean_ms && trial.reward>best.reward)));
        if(evaluated&&improved){
            best=trial;policy.save(output/"best.tmppo",schema);trainer.save_checkpoint(output/"best.checkpoint",schema,sampler);
            std::ofstream selected(output/"best.json");selected<<"{\"update\":"<<update<<",\"evaluation\":";json_eval(selected,trial);selected<<"}\n";
        }
        total+=rows.size();total_ticks+=ticks;
        summary<<update<<','<<rows.size()<<','<<ticks<<','<<completed<<','<<finishes<<','<<(finishes?finish_sum/finishes:-1.)
            <<','<<collected<<','<<trained<<','<<(evaluated?int(trial.finishes):-1)<<','<<(trial.finishes?trial.mean_ms:-1.)<<','
            <<metrics.policy_loss<<','<<metrics.value_loss<<','<<metrics.approx_kl<<','<<metrics.gradient_norm<<'\n';summary.flush();
        std::cout<<"FAST_PPO update="<<update<<" transitions="<<total<<" finishes="<<finishes<<'/'<<completed
            <<" eval="<<trial.finishes<<" eval_ms="<<(trial.finishes?trial.mean_ms:-1.)<<" collect_s="<<collected<<" train_s="<<trained<<std::endl;
        std::ofstream report(output/"report.json");report<<std::setprecision(17)<<"{\"updates\":"<<update+1
            <<",\"transitions\":"<<total<<",\"physicsTicks\":"<<total_ticks<<",\"environments\":"<<n
            <<",\"seconds\":"<<std::chrono::duration<double>(Clock::now()-begin).count()<<",\"bestDevelopmentEvaluation\":";
        json_eval(report,best);report<<",\"heldOutTestUsedForSelection\":false,\"originalGameValidationPerformed\":false"
            <<",\"completeExactPhysicsQualified\":false,\"generalRacePolicyQualified\":false}\n";
    }
}catch(const std::exception& e){std::cerr<<"FAST_TRAIN_ERROR "<<e.what()<<'\n';return 1;}
