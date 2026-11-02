// SPDX-License-Identifier: GPL-3.0-or-later
// Persistent in-process vector environments and native PPO; no Python runtime.
#include "fast_training.h"
#include "tm2020/rl.hpp"
#include "tm2020/observation_history.hpp"
#include "gpu_optimizer.hpp"
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
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
static_assert(sizeof(tmfast_state)==544);
void require(bool ok,const std::string& message){if(!ok)throw std::runtime_error(message);}
struct Api{
    void* library{};uint32_t (*reward_version)(){};
#define API(name) decltype(&tmfast_##name) name{};
    API(version) API(last_error) API(open) API(clone) API(configure) API(configure_planner) API(reset) API(reset_bank) API(bank_size) API(step) API(step_controls) API(close)
#undef API
    explicit Api(const fs::path& p){
        library=dlopen(fs::absolute(p).c_str(),RTLD_NOW|RTLD_LOCAL);
        require(library!=nullptr,"Cannot load native physics library");
#define LOAD(name) name=reinterpret_cast<decltype(name)>(dlsym(library,"tmfast_" #name));require(name!=nullptr,"Missing tmfast_" #name);
        LOAD(version) LOAD(last_error) LOAD(open) LOAD(clone) LOAD(configure) LOAD(configure_planner) LOAD(reset) LOAD(reset_bank) LOAD(bank_size) LOAD(step) LOAD(step_controls) LOAD(close)
#undef LOAD
        reward_version=reinterpret_cast<decltype(reward_version)>(dlsym(library,"tmgen_reward_version"));
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
Action command(const std::vector<double>& a);
class Workers{
    Api& api;std::vector<std::unique_ptr<Environment>>& envs;std::vector<Action>& actions;
    std::vector<tmfast_state>& states;std::vector<std::string> errors;
    const size_t count;const uint32_t repeat;std::barrier<> start,finish;
    bool stop=false;std::vector<std::jthread> threads;
    const tm2020::rl::ActorCritic* policy{};std::vector<tm2020::rl::ObservationHistory>* histories{};
    std::vector<tm2020::rl::Decision>* decisions{};const std::vector<double>* kicks{};
    std::vector<std::vector<double>> noises;std::vector<double> values;
public:
    Workers(Api& a,std::vector<std::unique_ptr<Environment>>& e,std::vector<Action>& ac,
            std::vector<tmfast_state>& s,size_t n,uint32_t r):api(a),envs(e),actions(ac),states(s),errors(e.size()),
            count(std::min(n,e.size())),repeat(r),start(count+1),finish(count+1),noises(e.size()),values(e.size()){
        for(size_t w=0;w<count;++w)threads.emplace_back([this,w]{
            for(;;){start.arrive_and_wait();if(stop)break;
                for(size_t i=w;i<envs.size();i+=count)try{
                    if(policy){
                        (*decisions)[i]=policy->sample_with_noise((*histories)[i].values,noises[i]);
                        actions[i]=command((*decisions)[i].action);
                        if((*kicks)[i]!=0.)actions[i][2]=std::clamp(actions[i][2]+(*kicks)[i],-1.,1.);
                    }
                    const auto code=api.step(envs[i]->handle,actions[i].data(),repeat,&states[i]);
                    errors[i]=code?("env="+std::to_string(i)+" "+api.last_error()):"";
                    if(!code&&policy){(*histories)[i].push(states[i].observation);values[i]=policy->value((*histories)[i].values);}
                }catch(const std::exception& error){errors[i]=error.what();
                }
                finish.arrive_and_wait();
            }
        });
    }
    ~Workers(){stop=true;start.arrive_and_wait();for(auto& thread:threads)thread.join();}
    void step(){start.arrive_and_wait();finish.arrive_and_wait();for(auto& e:errors)require(e.empty(),"Physics worker: "+e);}
    void collect(const tm2020::rl::ActorCritic& p,std::mt19937_64& rng,std::vector<tm2020::rl::ObservationHistory>& encoded,
                 std::vector<tm2020::rl::Decision>& result,const std::vector<double>& disturbance){
        policy=&p;histories=&encoded;decisions=&result;kicks=&disturbance;
        for(auto& noise:noises){noise.resize(p.actor.outputs);std::normal_distribution<double> normal;for(auto& v:noise)v=normal(rng);}
        step();policy=nullptr;
    }
    double next_value(size_t i)const{return values[i];}
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
            "--eval-trials","--gpu-service","--map-list","--curriculum","--bank-probability","--bank-decay","--bank-min-fraction","--planner","--noise","--disturbance-probability","--rollout-format","--history"};
        for(auto& [k,v]:values)require(std::find(allowed.begin(),allowed.end(),k)!=allowed.end(),"Unknown option "+k);
    }
    std::string get(const std::string& k,const std::string& fallback="")const{
        auto i=values.find(k);return i==values.end()?fallback:i->second;
    }
    size_t number(const std::string& k,size_t fallback)const{return std::stoull(get(k,std::to_string(fallback)));}
    double real(const std::string& k,double fallback)const{return std::stod(get(k,std::to_string(fallback)));}
    fs::path path(const std::string& k)const{auto p=get(k);require(!p.empty(),"Missing "+k);return fs::absolute(p);}
};
std::string policy_schema(size_t actions,bool planner,size_t history=1){return std::string(planner?TMFAST_PLANNER_SCHEMA:TMFAST_SCHEMA)+(history>1?"|history="+std::to_string(history):"")+"|policy_actions="+(actions==1?"steering_direct1":"pedals_direct3");}
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
        tm2020::rl::ObservationHistory history(48,policy?tm2020::rl::observation_frames(policy->actor.inputs):1);history.reset(state.observation);
        // Deterministic start perturbations, independent of policy training RNG.
        if(trial>0){
            std::mt19937_64 perturb(seed+trial);
            const auto warm=8+perturb()%15,duration=1+perturb()%5;
            const double amplitude=(trial%2?1.:-1.)*(0.15+double(perturb()%3500)/10000.);
            for(size_t k=0;k<warm&&!state.terminated&&!state.truncated;++k){
                const auto action=policy?command(policy->deterministic(history.values).action):Action{1,-1,0};
                api.check(api.step(handle,action.data(),repeat,&state));history.push(state.observation);score+=state.reward;
            }
            for(size_t k=0;k<duration&&!state.terminated&&!state.truncated;++k){
                const auto action=policy?command(policy->deterministic(history.values).action):Action{1,-1,0};
                const auto steer=int(std::round(std::clamp(action[2]+amplitude,-1.,1.)*127.));
                const std::array<float,3> controls{float(action[0]>=0),float(action[1]>=0),float(steer)/127.f};
                api.check(api.step_controls(handle,controls.data(),repeat,&state));history.push(state.observation);score+=state.reward;
            }
        }
        while(!state.terminated&&!state.truncated){
            const auto action=policy?command(policy->deterministic(history.values).action):Action{1,-1,0};
            api.check(api.step(handle,action.data(),repeat,&state));history.push(state.observation);score+=state.reward;
        }
        outcomes[trial]={1,size_t(state.finish_ms>=0),score,state.finish_ms>=0?double(state.finish_ms):0.,state.finish_ms>=0?double(state.finish_ms):1e9};
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
void rollout_binary(const fs::path& file,const std::vector<tm2020::rl::Transition>& rows,size_t nx,size_t na){
    const std::array<uint32_t,2> dimensions{uint32_t(nx),uint32_t(na)};const uint64_t count=rows.size();
    const size_t columns=7+na+nx;std::vector<double> values(rows.size()*columns);
    for(size_t i=0;i<rows.size();++i){const auto& r=rows[i];auto* p=values.data()+i*columns;
        require(r.latent.size()==na&&r.observation.size()==nx,"Binary rollout shape mismatch");
        p[0]=r.old_log_probability;p[1]=r.old_value;p[2]=r.reward;p[3]=r.next_value;
        p[4]=double(r.terminated);p[5]=double(r.truncated);p[6]=r.elapsed_steps;
        std::copy(r.latent.begin(),r.latent.end(),p+7);std::copy(r.observation.begin(),r.observation.end(),p+7+na);
    }
    std::ofstream out(file,std::ios::binary);out.write("TMROLL01",8);
    out.write(reinterpret_cast<const char*>(dimensions.data()),sizeof(dimensions));out.write(reinterpret_cast<const char*>(&count),sizeof(count));
    out.write(reinterpret_cast<const char*>(values.data()),values.size()*sizeof(double));
    require(bool(out),"Binary rollout write failed");
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
        updates>=1&&updates<=100000&&horizon>=1&&horizon<=100000&&repeat>=1&&repeat<=100&&width>=8&&width<=1024&&
        (na==1||na==3)&&epochs>=1&&epochs<=32&&eval_every>=1&&eval_every<=1000,"Invalid bounded training options");
    const auto eval_trials=args.number("--eval-trials",1);
    require(eval_trials>=1&&eval_trials<=100,"Evaluation trials must be 1..100");
    const auto look=args.real("--lookahead",10),gain=args.real("--gain",3),residual=args.real("--residual",1.);
    const bool curriculum=args.number("--curriculum",0)!=0;
    const auto bank_decay=args.number("--bank-decay",200);
    const double bank_probability=args.real("--bank-probability",.7);
    const double bank_min_fraction=args.real("--bank-min-fraction",0.);
    require(bank_decay>0 && bank_probability>=0 && bank_probability<=1&&bank_min_fraction>=0&&bank_min_fraction<=1,"Invalid reset curriculum");
    const bool planner=args.number("--planner",0)!=0;
    const double disturbance_probability=args.real("--disturbance-probability",0.);
    require(std::isfinite(disturbance_probability)&&disturbance_probability>=0.&&disturbance_probability<=1.,"Invalid disturbance probability");
    const bool cuda_optimizer=!args.get("--gpu-service").empty();
    const auto rollout_format=args.get("--rollout-format","csv");require(rollout_format=="csv"||rollout_format=="binary","Invalid rollout format");
    const auto gpu_service=cuda_optimizer?args.path("--gpu-service"):fs::path{};
    if(cuda_optimizer){std::ifstream ready(gpu_service/"ready.txt");std::string tag;ready>>tag;
        require(tag=="TM2020_CUDA_PPO_V1","CUDA optimizer service is not ready");}
    Api api(args.path("--library"));
    std::cout<<"GENERALIST_MAP_LOADING "<<args.path("--map").string()<<std::endl;
    Environment root(api,api.open(args.path("--map").c_str(),args.path("--packs").c_str(),args.path("--route").c_str(),horizon));
    api.check(api.configure(root.handle,look,gain,residual));
    api.check(api.configure_planner(root.handle,planner));
    std::vector<std::unique_ptr<Environment>> additional_roots;
    std::vector<tmfast_env> maps{root.handle};
    std::vector<std::string> map_names{args.path("--map").string()};
    if(!args.get("--map-list").empty()){
        std::ifstream list(args.path("--map-list"));require(bool(list),"Cannot open map list");
        std::string line;
        while(std::getline(list,line)){
            if(!line.empty()&&line.back()=='\r')line.pop_back();
            if(line.empty()||line==map_names.front())continue;
            require(maps.size()<64,"At most 64 maps per run");
            std::cout<<"GENERALIST_MAP_LOADING "<<line<<std::endl;
            auto e=std::make_unique<Environment>(api,api.open(fs::absolute(line).c_str(),args.path("--packs").c_str(),"",horizon));
            api.check(api.configure(e->handle,look,gain,residual));api.check(api.configure_planner(e->handle,planner));
            maps.push_back(e->handle);map_names.push_back(line);additional_roots.push_back(std::move(e));
        }
    }
    require(n>=maps.size(),"Environments must cover every training map");
    {std::ofstream manifest(output/"maps.txt");for(auto& name:map_names)manifest<<name<<'\n';}
    size_t policy_width=width,history_frames=args.number("--history",1);
    require(history_frames==1||history_frames==3||history_frames==5,"Invalid observation history");
    const auto architecture_source=!args.get("--resume").empty()?"--resume":"--model";
    if(!args.get(architecture_source).empty()){
        std::ifstream checkpoint(args.path(architecture_source),std::ios::binary);
        std::array<char,8> magic{};std::array<uint32_t,6> header{};
        checkpoint.read(magic.data(),magic.size());
        checkpoint.read(reinterpret_cast<char*>(header.data()),sizeof(header));
        require(bool(checkpoint)&&std::string(magic.data(),magic.size())==(std::string(architecture_source)=="--resume"?"TMTRAIN1":"TMPPO001")&&
            header[0]==1&&(header[1]==48||header[1]==144||header[1]==240)&&header[2]==na&&
            header[3]>=8&&header[3]<=1024,"Invalid resume checkpoint architecture");
        policy_width=header[3];history_frames=tm2020::rl::observation_frames(header[1]);
    }
    const auto schema=policy_schema(na,planner,history_frames);
    const auto policy_inputs=48*history_frames;
    tm2020::rl::ActorCritic policy(policy_inputs,na,policy_width,seed);
    auto base=policy.actor.hidden*(policy.actor.inputs+1);
    std::fill(policy.actor.parameters.begin()+base,policy.actor.parameters.end(),0.);
    if(na==3){policy.actor.parameters[base+na*policy.actor.hidden]=1;policy.actor.parameters[base+na*policy.actor.hidden+1]=-1;}
    const auto noise=args.real("--noise",.035);require(noise>0 && noise<=1,"Invalid exploration scale");
    policy.log_std.assign(na,std::log(noise/std::max(.01,residual)));
    if(!args.get("--model").empty()){
        std::string loaded;policy=tm2020::rl::ActorCritic::load(args.path("--model"),&loaded);
        require(loaded==schema&&policy.actor.outputs==na&&policy.actor.inputs==policy_inputs,"Policy schema differs");
    }
    const bool minimum_time=api.reward_version&&api.reward_version()>=2;
    tm2020::rl::PpoConfig cfg;cfg.gamma=minimum_time?1.:.999;cfg.lambda=.97;cfg.epochs=epochs;cfg.minibatch=256;
    cfg.learning_rate=args.real("--learning-rate",.0003);cfg.target_kl=.02;
    tm2020::rl::PpoTrainer trainer(policy,cfg,seed+1);std::mt19937_64 sampler(seed+2);
    std::array<double,8> actual_config{cfg.learning_rate,cfg.gamma,cfg.lambda,cfg.clip,cfg.value_coefficient,cfg.latent_entropy_coefficient,cfg.max_gradient_norm,cfg.target_kl};
    if(!args.get("--resume").empty()){
        std::ifstream source(args.path("--resume"),std::ios::binary);source.seekg(40);
        source.read(reinterpret_cast<char*>(actual_config.data()),sizeof(actual_config));
        require(bool(source)&&(!minimum_time||actual_config[1]==1.),"Minimum-time reward requires a gamma=1 checkpoint; convert actor/critic explicitly");
        trainer.load_checkpoint(args.path("--resume"),schema,sampler);
    }
    {
        std::ofstream cfgout(output/"config.json");cfgout<<std::setprecision(17)<<"{\"schema\":"<<std::quoted(schema)
            <<",\"rewardContract\":"<<std::quoted(minimum_time?(api.reward_version()==4?"minimum_time_failure_progress_v4":(api.reward_version()==3?"minimum_time_pure_v3":"minimum_time_potential_v2")):"checkpoint_progress_v1")<<",\"gamma\":"<<actual_config[1]<<",\"optimizerLearningRate\":"<<actual_config[0]<<",\"optimizerDevice\":"<<std::quoted(cuda_optimizer?"cuda":"cpu")<<",\"initialSteeringLatentStd\":"<<std::exp(policy.log_std.back())<<",\"planner\":"<<(planner?"true":"false")<<",\"observations\":"<<policy_inputs<<",\"rawObservations\":48,\"historyFrames\":"<<history_frames<<",\"physicsApiVersion\":"<<TMFAST_API_VERSION
            <<",\"initialModel\":"<<std::quoted(args.get("--model"))<<",\"resumedCheckpoint\":"<<std::quoted(args.get("--resume"))
            <<",\"map\":"<<std::quoted(args.path("--map").string())<<",\"route\":"<<std::quoted(args.path("--route").string())
            <<",\"library\":"<<std::quoted(args.path("--library").string())<<",\"environments\":"<<n<<",\"threads\":"<<threads
            <<",\"rolloutLength\":"<<length<<",\"horizon\":"<<horizon<<",\"repeat\":"<<repeat
            <<",\"evaluationTrials\":"<<eval_trials<<",\"hidden\":"<<policy.actor.hidden<<",\"actions\":"<<na<<",\"seed\":"<<seed<<",\"lookahead\":"<<look
            <<",\"gain\":"<<gain<<",\"residual\":"<<residual<<",\"rewardScale\":0.01,\"timePenalty\":"<<(minimum_time?.01:.002)<<",\"crossTrackPenalty\":0.0,\"geometricRouteAssistance\":false"
            <<",\"demonstrationResetCurriculum\":"<<(curriculum?"true":"false")<<",\"bankProbability\":"<<bank_probability
            <<",\"bankDecayUpdates\":"<<bank_decay<<",\"bankMinFraction\":"<<bank_min_fraction<<",\"resetSnapshots\":"<<api.bank_size(root.handle)
            <<",\"evaluationPerturbation\":\"policy_relative_physical_i8_steering_v2\",\"evaluationStartsAtZero\":true"
            <<",\"trainingDisturbanceProbability\":"<<disturbance_probability<<",\"parallelPolicyInference\":true,\"rolloutFormat\":"<<std::quoted(rollout_format)
            <<",\"recordedControlsUsedInObservations\":false,\"completeExactPhysicsQualified\":false}\n";
    }
    if(mode=="eval-stream"){
        std::ofstream history(output/"evaluations.jsonl");history<<std::setprecision(17);
        std::string tag,model_name,trials_text,seed_text;size_t sequence=0;
        std::cout<<"EVAL_STREAM_READY"<<std::endl;
        while(std::getline(std::cin,tag)&&tag!="STOP"){
            require(tag=="TM2020_EVAL_V1"&&bool(std::getline(std::cin,model_name))&&bool(std::getline(std::cin,trials_text))&&bool(std::getline(std::cin,seed_text)),"Invalid evaluation stream request");
            const auto trials=std::stoull(trials_text),request_seed=std::stoull(seed_text);
            require(trials>=1&&trials<=100&&request_seed<=UINT32_MAX,"Invalid evaluation stream limits");
            std::string loaded_schema;auto candidate=tm2020::rl::ActorCritic::load(model_name,&loaded_schema);
            const auto frames=tm2020::rl::observation_frames(candidate.actor.inputs);
            require((candidate.actor.outputs==1||candidate.actor.outputs==3)&&
                loaded_schema==policy_schema(candidate.actor.outputs,false,frames),"Evaluation model schema differs");
            auto result=evaluate(api,root.handle,&candidate,trials,repeat,uint32_t(request_seed+100000));
            std::ostringstream response;response<<std::setprecision(17)<<"{\"sequence\":"<<sequence++<<",\"model\":"<<std::quoted(model_name)
                <<",\"hidden\":"<<candidate.actor.hidden<<",\"candidate\":";json_eval(response,result);response<<"}";
            history<<response.str()<<'\n';history.flush();std::cout<<"EVAL_JSON "<<response.str()<<std::endl;
        }
        return 0;
    }
    if(mode=="eval"){
        const auto trials=args.number("--trials",10);require(trials>=1&&trials<=100,"Invalid evaluation trials");
        Evaluation baseline{},candidate{};
        std::ofstream per_map(output/"maps.jsonl");
        for(size_t k=0;k<maps.size();++k){
            auto b=evaluate(api,maps[k],nullptr,trials,repeat,seed+100000);
            auto c=evaluate(api,maps[k],&policy,trials,repeat,seed+100000);
            per_map<<"{\"map\":"<<std::quoted(map_names[k])<<",\"baseline\":";json_eval(per_map,b);
            per_map<<",\"candidate\":";json_eval(per_map,c);per_map<<"}\n";
            baseline.trials+=b.trials;baseline.finishes+=b.finishes;baseline.mean_ms+=b.finishes?b.mean_ms*b.finishes:0.;
            candidate.trials+=c.trials;candidate.finishes+=c.finishes;candidate.mean_ms+=c.finishes?c.mean_ms*c.finishes:0.;
            baseline.reward+=b.reward;candidate.reward+=c.reward;
            baseline.best_ms=std::min(baseline.best_ms,b.best_ms);candidate.best_ms=std::min(candidate.best_ms,c.best_ms);
        }
        baseline.reward/=maps.size();candidate.reward/=maps.size();
        baseline.mean_ms=baseline.finishes?baseline.mean_ms/baseline.finishes:1e9;
        candidate.mean_ms=candidate.finishes?candidate.mean_ms/candidate.finishes:1e9;

        std::ofstream out(output/"report.json");out<<std::setprecision(17)<<"{\"baseline\":";json_eval(out,baseline);
        out<<",\"candidate\":";json_eval(out,candidate);out<<"}\n";
        std::cout<<"EVALUATION baseline="<<baseline.finishes<<'/'<<trials<<" mean_ms="<<baseline.mean_ms
            <<" candidate="<<candidate.finishes<<'/'<<trials<<" mean_ms="<<candidate.mean_ms<<'\n';return 0;
    }
    require(mode=="train"||mode=="bench","Unknown mode");
    std::vector<std::unique_ptr<Environment>> envs;std::vector<Action> actions(n);
    std::vector<tmfast_state> states(n);std::vector<uint32_t> episodes(n),banks(n);
    std::vector<tm2020::rl::ObservationHistory> histories(n,tm2020::rl::ObservationHistory(48,history_frames));
    std::vector<size_t> episode_steps(n),disturbance_start(n),disturbance_duration(n);
    std::vector<double> disturbance_amplitude(n);
    const auto bank_count=api.bank_size(root.handle);
    auto reset_env=[&](size_t i,size_t update){
        uint64_t hash=seed+i+uint64_t(episodes[i])*n+uint64_t(update)*0x9e3779b97f4a7c15ULL;
        hash=(hash^(hash>>30))*0xbf58476d1ce4e5b9ULL;hash=(hash^(hash>>27))*0x94d049bb133111ebULL;hash^=hash>>31;
        const double probability=bank_probability*std::max(0.,1.-double(update)/bank_decay);
        const auto first_bank=bank_count>1?1+std::min(bank_count-2,uint32_t(bank_min_fraction*(bank_count-1))):0;
        banks[i]=curriculum && bank_count>1 && double(hash%1000000)/1000000.<probability?
            first_bank+uint32_t((hash>>20)%(bank_count-first_bank)):0;
        episode_steps[i]=0;disturbance_start[i]=8+(hash>>20)%15;
        disturbance_duration[i]=double(hash%1000000)/1000000.<disturbance_probability?1+(hash>>32)%5:0;
        disturbance_amplitude[i]=(hash&1?1.:-1.)*(.15+double((hash>>40)%3500)/10000.);
        api.check(api.reset_bank(envs[i]->handle,uint32_t(seed+i+episodes[i]*n),banks[i],&states[i]));
        histories[i].reset(states[i].observation);
    };
    for(size_t i=0;i<n;++i){envs.push_back(std::make_unique<Environment>(api,api.clone(maps[i%maps.size()])));reset_env(i,0);}
    Workers workers(api,envs,actions,states,threads,repeat);
    if(mode=="bench"){
        const auto start=Clock::now();uint64_t ticks=0,resets=0;
        for(size_t t=0;t<length;++t){std::fill(actions.begin(),actions.end(),Action{1,-1,0});workers.step();
            for(size_t i=0;i<n;++i){ticks+=states[i].advanced_ticks;if(states[i].terminated||states[i].truncated){
                reset_env(i,0);resets++;}}}
        auto elapsed=std::chrono::duration<double>(Clock::now()-start).count();
        std::ofstream out(output/"report.json");out<<std::setprecision(17)<<"{\"physicsTicks\":"<<ticks
            <<",\"seconds\":"<<elapsed<<",\"ticksPerSecond\":"<<ticks/elapsed<<",\"resets\":"<<resets<<"}\n";
        std::cout<<"GENERALIST_BENCH ticks_per_second="<<ticks/elapsed<<" resets="<<resets<<'\n';return 0;
    }
    policy.save(output/"initial.tmppo",schema);trainer.save_checkpoint(output/"initial.checkpoint",schema,sampler);
    std::ofstream profile(output/"profile.jsonl");profile<<std::setprecision(17);
    std::ofstream summary(output/"updates.csv");summary<<"update,transitions,physics_ticks,episodes,finishes,mean_finish_ms,collect_seconds,train_seconds,eval_finishes,eval_mean_ms,policy_loss,value_loss,kl,gradient_norm\n";
    summary<<std::setprecision(17);auto begin=Clock::now();uint64_t total=0,total_ticks=0;
    Evaluation best{};best.reward=-1e30;best.mean_ms=1e9;
    for(size_t update=0;update<updates;++update){
        if(fs::exists(output/"STOP")){
            std::cout<<"GENERALIST_PPO stopped between complete updates; checkpoints retained"<<std::endl;break;
        }
        auto folder=output/("update-"+std::to_string(update));fs::create_directories(folder);
        const auto update_start=Clock::now();double sample_seconds=0,physics_seconds=0,transition_seconds=0;
        policy.save(folder/"behavior.tmppo",schema);
        std::vector<tm2020::rl::Transition> rows;rows.reserve(n*length);
        std::ofstream physics(folder/"physics.bin",std::ios::binary);physics.write("TMFAST03",8);
        size_t completed=0,finishes=0;double finish_sum=0;uint64_t ticks=0;auto start=Clock::now();
        for(size_t t=0;t<length;++t){
            auto stage=Clock::now();
            auto before=states;const auto before_history=histories;std::vector<tm2020::rl::Decision> decisions(n);std::vector<double> kicks(n);
            for(size_t i=0;i<n;++i){
                // Exogenous steering kicks: keep the sampled latent/logp intact.
                // PPO learns the policy under disturbances, not the likelihood
                // of a clipped or perturbed action masquerading as its sample.
                if(episode_steps[i]>=disturbance_start[i]&&episode_steps[i]<disturbance_start[i]+disturbance_duration[i])
                    kicks[i]=disturbance_amplitude[i];
                episode_steps[i]++;
            }
            sample_seconds+=std::chrono::duration<double>(Clock::now()-stage).count();stage=Clock::now();
            workers.collect(policy,sampler,histories,decisions,kicks);
            physics_seconds+=std::chrono::duration<double>(Clock::now()-stage).count();stage=Clock::now();
            for(size_t i=0;i<n;++i){const auto& s=states[i];const auto& d=decisions[i];
                require(s.advanced_ticks>0&&s.advanced_ticks<=repeat,"Invalid physical duration");
                const auto boundary=bool(s.truncated)||(t+1==length&&!s.terminated);
                rows.push_back({before_history[i].values,d.latent,
                    d.log_probability,d.value,s.reward*.01,workers.next_value(i),bool(s.terminated),boundary,
                    double(s.advanced_ticks)/repeat});
                PhysicalRow evidence{uint32_t(i),episodes[i],banks[i],0,before[i],s,actions[i]};
                physics.write(reinterpret_cast<const char*>(&evidence),sizeof(evidence));ticks+=s.advanced_ticks;
                if(s.terminated||s.truncated){completed++;finishes+=s.finish_ms>=0;if(s.finish_ms>=0)finish_sum+=s.finish_ms;
                    episodes[i]++;reset_env(i,update);}
            }
            transition_seconds+=std::chrono::duration<double>(Clock::now()-stage).count();
        }
        physics.flush();require(bool(physics),"Physical rollout write failed");physics.close();
        const auto collected=std::chrono::duration<double>(Clock::now()-start).count();
        const auto rollout_file=folder/(rollout_format=="binary"?"rollout.bin":"rollout.csv");
        if(rollout_format=="binary")rollout_binary(rollout_file,rows,policy_inputs,na);
        else rollout_csv(rollout_file,rows,policy_inputs,na);
        const auto serialized=std::chrono::duration<double>(Clock::now()-start).count()-collected;
        start=Clock::now();tm2020::rl::UpdateMetrics metrics;
        if(cuda_optimizer){
            trainer.save_checkpoint(folder/"optimizer-input.checkpoint",schema,sampler);
            metrics=gpu_update(gpu_service,update,folder/"optimizer-input.checkpoint",rollout_file,n,
                folder/"cuda-output.checkpoint",folder/"cuda-metrics.json");
            trainer.load_checkpoint(folder/"cuda-output.checkpoint",schema,sampler);
        }else{metrics=trainer.update(rows,n);}
        const auto trained=std::chrono::duration<double>(Clock::now()-start).count();
        const auto evaluation_start=Clock::now();
        trainer.save_checkpoint(folder/"training.checkpoint",schema,sampler);policy.save(folder/"updated.tmppo",schema);
        const bool evaluated=update%eval_every==0 || update+1==updates;
        Evaluation trial{};
        if(evaluated){
            for(auto handle:maps){auto e=evaluate(api,handle,&policy,eval_trials,repeat,uint32_t(seed+50000));
                trial.trials+=e.trials;trial.finishes+=e.finishes;trial.reward+=e.reward;
                if(e.finishes){trial.mean_ms+=e.mean_ms*e.finishes;}trial.best_ms=std::min(trial.best_ms,e.best_ms);}
            trial.reward/=maps.size();trial.mean_ms=trial.finishes?trial.mean_ms/trial.finishes:1e9;
        }
        const bool improved=trial.finishes>best.finishes || (trial.finishes==best.finishes &&
            (trial.mean_ms<best.mean_ms || (trial.mean_ms==best.mean_ms && trial.reward>best.reward)));
        if(evaluated&&improved){
            best=trial;policy.save(output/"best.tmppo",schema);trainer.save_checkpoint(output/"best.checkpoint",schema,sampler);
            std::ofstream selected(output/"best.json");selected<<"{\"update\":"<<update<<",\"evaluation\":";json_eval(selected,trial);selected<<"}\n";
        }
        total+=rows.size();total_ticks+=ticks;
        const auto update_seconds=std::chrono::duration<double>(Clock::now()-update_start).count();
        profile<<"{\"update\":"<<update<<",\"transitions\":"<<rows.size()<<",\"sampleSeconds\":"<<sample_seconds
          <<",\"physicsAndInferenceSeconds\":"<<physics_seconds<<",\"transitionSeconds\":"<<transition_seconds<<",\"serializeSeconds\":"<<serialized
          <<",\"optimizeSeconds\":"<<trained<<",\"checkpointAndEvaluationSeconds\":"<<std::chrono::duration<double>(Clock::now()-evaluation_start).count()
          <<",\"totalSeconds\":"<<update_seconds<<"}\n";profile.flush();
        summary<<update<<','<<rows.size()<<','<<ticks<<','<<completed<<','<<finishes<<','<<(finishes?finish_sum/finishes:-1.)
            <<','<<collected<<','<<trained<<','<<(evaluated?int(trial.finishes):-1)<<','<<(trial.finishes?trial.mean_ms:-1.)<<','
            <<metrics.policy_loss<<','<<metrics.value_loss<<','<<metrics.approx_kl<<','<<metrics.gradient_norm<<'\n';summary.flush();
        std::cout<<"GENERALIST_PPO update="<<update<<" transitions="<<total<<" finishes="<<finishes<<'/'<<completed
            <<" eval="<<trial.finishes<<" eval_ms="<<(trial.finishes?trial.mean_ms:-1.)<<" collect_s="<<collected<<" train_s="<<trained<<std::endl;
        std::ofstream report(output/"report.json");report<<std::setprecision(17)<<"{\"updates\":"<<update+1
            <<",\"transitions\":"<<total<<",\"physicsTicks\":"<<total_ticks<<",\"environments\":"<<n
            <<",\"seconds\":"<<std::chrono::duration<double>(Clock::now()-begin).count()<<",\"bestDevelopmentEvaluation\":";
        json_eval(report,best);report<<",\"optimizerDevice\":"<<std::quoted(cuda_optimizer?"cuda":"cpu")<<",\"heldOutTestUsedForSelection\":false,\"originalGameValidationPerformed\":false"
            <<",\"completeExactPhysicsQualified\":false,\"generalRacePolicyQualified\":false}\n";
    }
}catch(const std::exception& e){std::cerr<<"GENERALIST_TRAIN_ERROR "<<e.what()<<'\n';return 1;}
