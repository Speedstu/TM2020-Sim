#define TM2020_POLICY_BUILD
#include "tm2020/trainer.h"
#include "tm2020/rl.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <memory>
#include <optional>
#include <fstream>
#include <iomanip>

namespace {
thread_local std::string error;
void require(bool ok,const char* message){if(!ok)throw std::invalid_argument(message);}
struct Pending {std::vector<double> observation;tm2020::rl::Decision decision;};
struct Trainer {
    tm2020::rl::ActorCritic policy;
    tm2020::rl::PpoTrainer trainer;
    std::mt19937_64 sampler;
    std::string schema;
    std::optional<Pending> pending;
    std::vector<tm2020::rl::Transition> rows;
    Trainer(uint32_t nx,uint32_t na,uint32_t width,uint64_t seed,const char* s)
        :policy(nx,na,width,seed),trainer(policy,{},seed+1),sampler(seed+2),schema(s){}
    void idle(){require(!pending&&rows.empty(),"Checkpoint operation requires an empty rollout");}
};
Trainer& get(tm2020_trainer_handle h){require(h,"Null trainer handle");return *static_cast<Trainer*>(h);}
std::span<const double> observation(const Trainer& t,const double* x,uint32_t n){
    require(x&&n==t.policy.actor.inputs,"Observation dimension mismatch");
    require(std::all_of(x,x+n,[](double v){return std::isfinite(v);}),"Nonfinite observation");return {x,n};
}
auto path(const char* p){require(p&&*p,"Empty checkpoint/model path");
    return std::filesystem::path(std::u8string(reinterpret_cast<const char8_t*>(p),std::strlen(p)));}
template<class F> int32_t attempt(F&& fn) noexcept {
    try{fn();error.clear();return 0;}
    catch(const std::exception& e){error=e.what();return -1;}
    catch(...){error="Unknown trainer error";return -2;}
}
}
extern "C" {
uint32_t tm2020_trainer_version(void){return TM2020_TRAINER_API_VERSION;}
const char* tm2020_trainer_last_error(void){return error.c_str();}
int32_t tm2020_trainer_create(uint32_t nx,uint32_t na,uint32_t width,uint64_t seed,
                            const char* schema,tm2020_trainer_handle* out){
    if(out)*out=nullptr;
    return attempt([&]{require(out&&schema&&*schema,"Missing trainer output/schema");
        require(std::strlen(schema)<=4096,"Schema too long");
        auto t=std::make_unique<Trainer>(nx,na,width,seed,schema);*out=t.release();});
}
int32_t tm2020_trainer_sample(tm2020_trainer_handle h,const double* x,uint32_t nx,
                            double* a,uint32_t na,double* value){
    return attempt([&]{auto& t=get(h);
        require(!t.pending,"Observe or cancel the outstanding decision first");
        require(t.rows.size()<65536,"Rollout transition bound reached");
        require(a&&value&&na==t.policy.actor.outputs,"Action dimension mismatch");
        auto obs=observation(t,x,nx);
        // Allocate before advancing sampler RNG or installing pending state.
        Pending p{std::vector<double>(obs.begin(),obs.end()),{}};
        p.decision=t.policy.sample(obs,t.sampler);
        t.pending=std::move(p);
        std::copy(t.pending->decision.action.begin(),t.pending->decision.action.end(),a);
        *value=t.pending->decision.value;
    });
}
int32_t tm2020_trainer_observe(tm2020_trainer_handle h,double reward,const double* x,uint32_t nx,
                             uint32_t terminal,uint32_t truncated,double duration){
    return attempt([&]{auto& t=get(h);require(t.pending.has_value(),"No outstanding decision");
        require(terminal<=1&&truncated<=1&&std::isfinite(reward)&&std::isfinite(duration)&&
                duration>0&&duration<=10000,"Invalid transition reward/boundary/duration");
        auto obs=observation(t,x,nx);const auto& p=*t.pending;
        const auto next=t.policy.value(obs);
        t.rows.push_back({p.observation,p.decision.latent,p.decision.log_probability,
            p.decision.value,reward,next,bool(terminal),bool(truncated),duration});
        t.pending.reset();
    });
}
int32_t tm2020_trainer_cancel(tm2020_trainer_handle h){
    return attempt([&]{auto& t=get(h);require(t.pending.has_value(),"No outstanding decision");
        t.pending.reset();if(!t.rows.empty())t.rows.back().truncated=true;});
}
int32_t tm2020_trainer_update(tm2020_trainer_handle h,tm2020_trainer_metrics* out){
    return attempt([&]{auto& t=get(h);
        require(out&&out->size_bytes==sizeof(*out)&&out->api_version==TM2020_TRAINER_API_VERSION,"Invalid metrics ABI");
        require(!t.pending&&!t.rows.empty(),"Update requires accepted rows and no pending decision");
        const auto n=t.rows.size();auto m=t.trainer.update(t.rows,1);
        *out={sizeof(*out),TM2020_TRAINER_API_VERSION,n,t.trainer.optimizer_steps(),m.minibatches,m.epochs,
            m.policy_loss,m.value_loss,m.approx_kl,m.clip_fraction,m.gradient_norm,uint32_t(m.kl_stopped),0};
        t.rows.clear();
    });
}
int32_t tm2020_trainer_rollout_csv(tm2020_trainer_handle h,const char* p){
    return attempt([&]{auto& t=get(h);require(!t.pending&&!t.rows.empty(),"Export requires accepted rows and no pending decision");
        std::ofstream out(path(p));require(bool(out),"Cannot open rollout CSV");
        out<<"old_log_probability,old_value,reward,next_value,terminated,truncated,elapsed_steps";
        for(std::size_t i=0;i<t.policy.actor.outputs;++i)out<<",latent_"<<i;
        for(std::size_t i=0;i<t.policy.actor.inputs;++i)out<<",observation_"<<i;
        out<<'\n'<<std::setprecision(17);
        for(const auto& row:t.rows){
            out<<row.old_log_probability<<','<<row.old_value<<','<<row.reward<<','<<row.next_value
               <<','<<row.terminated<<','<<row.truncated<<','<<row.elapsed_steps;
            for(double v:row.latent)out<<','<<v;
            for(double v:row.observation)out<<','<<v;
            out<<'\n';
        }
        out.flush();require(bool(out),"Rollout CSV write failed");
    });
}
int32_t tm2020_trainer_checkpoint(tm2020_trainer_handle h,const char* p){
    return attempt([&]{auto& t=get(h);t.idle();t.trainer.save_checkpoint(path(p),t.schema,t.sampler);});
}
int32_t tm2020_trainer_resume(tm2020_trainer_handle h,const char* p){
    return attempt([&]{auto& t=get(h);t.idle();t.trainer.load_checkpoint(path(p),t.schema,t.sampler);});
}
int32_t tm2020_trainer_export(tm2020_trainer_handle h,const char* p){
    return attempt([&]{auto& t=get(h);t.idle();t.policy.save(path(p),t.schema);});
}
void tm2020_trainer_close(tm2020_trainer_handle h){delete static_cast<Trainer*>(h);}
}
