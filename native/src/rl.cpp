#include "tm2020/rl.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <numeric>
#include <stdexcept>
namespace tm2020::rl {
namespace {
constexpr double log_two_pi=1.8378770664093454836;
void require(bool b,const char* msg){if(!b)throw std::invalid_argument(msg);}
void finite(std::span<const double> values){for(double x:values)require(std::isfinite(x),"Non-finite RL input");}
double jacobian(double z){const double a=-2*z;const double softplus=std::max(a,0.)+std::log1p(std::exp(-std::abs(a)));return 2*(std::log(2.)-z-softplus);}
std::uint64_t checksum(std::span<const std::byte> b){std::uint64_t h=14695981039346656037ull;for(auto x:b){h^=std::to_integer<unsigned char>(x);h*=1099511628211ull;}return h;}
}
Network::Network(std::size_t in,std::size_t width,std::size_t out,std::mt19937_64& rng)
    :inputs(in),hidden(width),outputs(out){
    require(in>0&&in<=4096&&width>0&&width<=1024&&out>0&&out<=64,"Network dimensions out of bounds");
    parameters.resize(hidden*inputs+hidden+outputs*hidden+outputs);
    std::normal_distribution<double> normal;
    for(std::size_t i=0;i<hidden*inputs;i++)parameters[i]=normal(rng)*std::sqrt(1./inputs);
    const auto head=hidden*inputs+hidden;
    for(std::size_t i=0;i<outputs*hidden;i++)parameters[head+i]=normal(rng)*.01/std::sqrt(double(hidden));
}
std::vector<double> Network::forward(std::span<const double> x)const{
    std::vector<double> y(outputs);forward_into(x,y);return y;
}
void Network::forward_into(std::span<const double> x,std::span<double> y)const{
    require(parameters.size()==hidden*inputs+hidden+outputs*hidden+outputs,"Malformed network parameter count");
    require(hidden<=1024&&x.size()==inputs&&y.size()==outputs,"Network inference dimension mismatch");finite(x);
    std::array<double,1024> h{};
    const auto bias=hidden*inputs,head=bias+hidden,tail=head+outputs*hidden;
    std::size_t i=0;
    // Four independent rows expose SIMD/ILP without reassociating a row's
    // floating-point sum. Keep the same bias-first, input-order arithmetic.
    for(;i+4<=hidden;i+=4){
        double a=parameters[bias+i],b=parameters[bias+i+1],c=parameters[bias+i+2],d=parameters[bias+i+3];
        for(std::size_t j=0;j<inputs;j++){
            const double v=x[j];
            a+=parameters[i*inputs+j]*v;b+=parameters[(i+1)*inputs+j]*v;
            c+=parameters[(i+2)*inputs+j]*v;d+=parameters[(i+3)*inputs+j]*v;
        }
        h[i]=std::tanh(a);h[i+1]=std::tanh(b);h[i+2]=std::tanh(c);h[i+3]=std::tanh(d);
    }
    for(;i<hidden;i++){
        double v=parameters[bias+i];for(std::size_t j=0;j<inputs;j++)v+=parameters[i*inputs+j]*x[j];h[i]=std::tanh(v);
    }
    for(std::size_t i=0;i<outputs;i++){
        double v=parameters[tail+i];for(std::size_t j=0;j<hidden;j++)v+=parameters[head+i*hidden+j]*h[j];y[i]=v;
    }
    finite(y);
}
void Network::backward(std::span<const double> x,std::span<const double> dy,std::span<double> g)const{
    require(parameters.size()==hidden*inputs+hidden+outputs*hidden+outputs,"Malformed network parameter count");
    require(x.size()==inputs&&dy.size()==outputs&&g.size()==parameters.size(),"Gradient shape mismatch");
    finite(x);finite(dy);
    const auto bias=hidden*inputs,head=bias+hidden,tail=head+outputs*hidden;
    require(hidden<=1024,"Hidden network width exceeds scratch capacity");
    std::array<double,1024> h{};
    for(std::size_t i=0;i<hidden;i++){
        double v=parameters[bias+i];for(std::size_t j=0;j<inputs;j++)v+=parameters[i*inputs+j]*x[j];h[i]=std::tanh(v);
    }
    for(std::size_t i=0;i<outputs;i++){
        g[tail+i]+=dy[i];for(std::size_t j=0;j<hidden;j++)g[head+i*hidden+j]+=dy[i]*h[j];
    }
    for(std::size_t j=0;j<hidden;j++){
        double dh=0;for(std::size_t i=0;i<outputs;i++)dh+=dy[i]*parameters[head+i*hidden+j];
        dh*=1-h[j]*h[j];g[bias+j]+=dh;
        for(std::size_t k=0;k<inputs;k++)g[j*inputs+k]+=dh*x[k];
    }
}
ActorCritic::ActorCritic(std::size_t observations,std::size_t actions,std::size_t width,std::uint64_t seed)
    :actor([&](){std::mt19937_64 rng(seed);return Network(observations,width,actions,rng);}()),
     critic([&](){std::mt19937_64 rng(seed+1);return Network(observations,width,1,rng);}()),log_std(actions,-.5){}
double ActorCritic::value(std::span<const double> x)const{
    double result;critic.forward_into(x,std::span(&result,1));return result;
}
double ActorCritic::log_probability(std::span<const double> x,std::span<const double> z)const{
    require(log_std.size()==actor.outputs,"Malformed policy standard deviation count");finite(log_std);
    require(z.size()==log_std.size(),"Latent action dimension mismatch");finite(z);
    auto mean=actor.forward(x);double logp=0;
    for(std::size_t i=0;i<z.size();i++){
        const double d=(z[i]-mean[i])*std::exp(-log_std[i]);
        logp+=-.5*(d*d+log_two_pi)-log_std[i]-jacobian(z[i]);
    }
    require(std::isfinite(logp),"Non-finite policy log probability");return logp;
}
Decision ActorCritic::sample(std::span<const double> x,std::mt19937_64& rng)const{
    std::vector<double> noise(actor.outputs);std::normal_distribution<double> n;
    for(auto& v:noise)v=n(rng);
    return sample_with_noise(x,noise);
}
Decision ActorCritic::sample_with_noise(std::span<const double> x,std::span<const double> noise)const{
    require(log_std.size()==actor.outputs,"Malformed policy standard deviation count");finite(log_std);
    require(noise.size()==actor.outputs,"Standard normal dimension mismatch");finite(noise);
    Decision d;const auto mean=actor.forward(x);d.latent=mean;d.action.resize(d.latent.size());
    for(std::size_t i=0;i<d.latent.size();i++){
        d.latent[i]+=std::exp(log_std[i])*noise[i];d.action[i]=std::tanh(d.latent[i]);
    }
    for(std::size_t i=0;i<d.latent.size();i++){
        const double scaled=(d.latent[i]-mean[i])*std::exp(-log_std[i]);
        d.log_probability+=-.5*(scaled*scaled+log_two_pi)-log_std[i]-jacobian(d.latent[i]);
    }
    require(std::isfinite(d.log_probability),"Non-finite policy log probability");d.value=value(x);return d;
}
Decision ActorCritic::deterministic(std::span<const double> x)const{
    Decision d;d.latent=actor.forward(x);for(auto v:d.latent)d.action.push_back(std::tanh(v));
    d.value=value(x);d.log_probability=log_probability(x,d.latent);return d;
}
void ActorCritic::predict_into(std::span<const double> x,std::span<double> actions,double& v)const{
    actor.forward_into(x,actions);
    for(auto& a:actions)a=std::tanh(a);
    critic.forward_into(x,std::span(&v,1));
}
std::vector<Advantage> generalized_advantage(std::span<const Transition> rollout,std::size_t envs,double gamma,double lambda){
    require(envs>0&&!rollout.empty()&&rollout.size()%envs==0,"Invalid vector rollout shape");
    require(std::isfinite(gamma)&&gamma>=0&&gamma<=1&&std::isfinite(lambda)&&lambda>=0&&lambda<=1,"Invalid GAE discounts");
    std::vector<Advantage> result(rollout.size());std::vector<double> running(envs);
    for(std::size_t i=rollout.size();i-->0;){
        const auto& t=rollout[i];finite(std::array{t.old_value,t.reward,t.next_value});
        require(std::isfinite(t.elapsed_steps)&&t.elapsed_steps>0&&t.elapsed_steps<=10000,"Invalid transition duration");
        const auto env=i%envs;const auto bootstrap=t.terminated?0.:t.next_value;
        const double discount=std::pow(gamma,t.elapsed_steps),trace_decay=std::pow(lambda,t.elapsed_steps);
        const double delta=t.reward+discount*bootstrap-t.old_value;
        running[env]=delta+((t.terminated||t.truncated)?0.:discount*trace_decay*running[env]);
        result[i]={running[env],running[env]+t.old_value};
    }
    return result;
}
PpoTrainer::PpoTrainer(ActorCritic& policy,PpoConfig c,std::uint64_t seed):policy_(policy),config_(c),rng_(seed){
    finite(std::array{c.learning_rate,c.gamma,c.lambda,c.clip,c.value_coefficient,c.latent_entropy_coefficient,c.max_gradient_norm,c.target_kl});
    require(c.learning_rate>0&&c.gamma>=0&&c.gamma<=1&&c.lambda>=0&&c.lambda<=1&&c.clip>0&&c.clip<1&&
        c.value_coefficient>=0&&c.latent_entropy_coefficient>=0&&c.max_gradient_norm>0&&c.target_kl>0&&
        c.epochs>0&&c.epochs<=1000&&c.minibatch>0,"Invalid PPO configuration");
    const auto n=policy.actor.parameters.size()+policy.critic.parameters.size()+policy.log_std.size();
    first_moment_.resize(n);second_moment_.resize(n);
}
UpdateMetrics PpoTrainer::update(std::span<const Transition> rollout,std::size_t envs){
    require(first_moment_.size()==policy_.actor.parameters.size()+policy_.critic.parameters.size()+policy_.log_std.size()&&
        policy_.log_std.size()==policy_.actor.outputs,"Policy architecture changed after trainer construction");
    for(const auto& t:rollout){
        require(t.observation.size()==policy_.actor.inputs&&t.latent.size()==policy_.actor.outputs,"PPO transition shape mismatch");
        finite(t.observation);finite(t.latent);finite(std::array{t.old_log_probability,t.old_value,t.reward,t.next_value});
        // Enforce on-policy rollout identity before mutating any model parameter.
        require(std::abs(policy_.log_probability(t.observation,t.latent)-t.old_log_probability)<1e-7&&
                std::abs(policy_.value(t.observation)-t.old_value)<1e-7,"Rollout was not collected by current policy");
    }
    auto targets=generalized_advantage(rollout,envs,config_.gamma,config_.lambda);
    double mean=0,var=0;for(auto a:targets)mean+=a.advantage;mean/=targets.size();
    for(auto a:targets)var+=(a.advantage-mean)*(a.advantage-mean);
    var/=targets.size();
    require(std::isfinite(mean)&&std::isfinite(var),"Advantage statistics overflow");
    for(auto& a:targets)a.advantage=(a.advantage-mean)/std::sqrt(var+1e-8);
    std::vector<std::size_t> order(rollout.size());std::iota(order.begin(),order.end(),0);
    const auto actor_n=policy_.actor.parameters.size(),critic_n=policy_.critic.parameters.size();
    const auto std_start=actor_n+critic_n,n=first_moment_.size();UpdateMetrics m;
    for(std::size_t epoch=0;epoch<config_.epochs;epoch++){
        double kl=0;
        for(const auto& t:rollout){const double d=policy_.log_probability(t.observation,t.latent)-t.old_log_probability;
            kl+=std::exp(std::clamp(d,-60.,60.))-1-d;}
        kl/=rollout.size();m.approx_kl=kl;
        if(kl>1.5*config_.target_kl){m.kl_stopped=true;break;}
        std::shuffle(order.begin(),order.end(),rng_);
        for(std::size_t begin=0;begin<order.size();begin+=config_.minibatch){
            const auto end=std::min(order.size(),begin+config_.minibatch);
            const double inv_batch=1./double(end-begin);std::vector<double> g(n);
            for(std::size_t at=begin;at<end;at++){
                const auto index=order[at];const auto& t=rollout[index];const auto a=targets[index];
                const double logp=policy_.log_probability(t.observation,t.latent);
                const double ratio=std::exp(std::clamp(logp-t.old_log_probability,-60.,60.));
                const double clipped=std::clamp(ratio,1-config_.clip,1+config_.clip);
                const bool stop=(a.advantage>=0&&ratio>1+config_.clip)||(a.advantage<0&&ratio<1-config_.clip);
                const double coefficient=stop?0.:-a.advantage*ratio*inv_batch;
                const auto mu=policy_.actor.forward(t.observation);std::vector<double> dmu(mu.size());
                for(std::size_t k=0;k<mu.size();k++){
                    const double diff=t.latent[k]-mu[k],inverse_variance=std::exp(-2*policy_.log_std[k]);
                    dmu[k]=coefficient*diff*inverse_variance;
                    g[std_start+k]+=coefficient*(diff*diff*inverse_variance-1)-config_.latent_entropy_coefficient*inv_batch;
                }
                policy_.actor.backward(t.observation,dmu,std::span(g.data(),actor_n));
                const double v=policy_.value(t.observation),error=v-a.target;
                const std::array dv{config_.value_coefficient*error*inv_batch};
                policy_.critic.backward(t.observation,dv,std::span(g.data()+actor_n,critic_n));
                m.policy_loss+=-std::min(ratio*a.advantage,clipped*a.advantage)*inv_batch;
                m.value_loss+=.5*error*error*inv_batch;m.clip_fraction+=double(stop)*inv_batch;
            }
            finite(g);double norm=0;for(auto x:g)norm+=x*x;norm=std::sqrt(norm);
            require(std::isfinite(norm),"Gradient norm overflow");
            const auto scale=norm>config_.max_gradient_norm?config_.max_gradient_norm/norm:1.;m.gradient_norm=norm;
            ++updates_;const double b1=1-std::pow(.9,double(updates_)),b2=1-std::pow(.999,double(updates_));
            for(std::size_t k=0;k<n;k++){
                const auto grad=g[k]*scale;first_moment_[k]=.9*first_moment_[k]+.1*grad;
                second_moment_[k]=.999*second_moment_[k]+.001*grad*grad;
                const double step=config_.learning_rate*(first_moment_[k]/b1)/(std::sqrt(second_moment_[k]/b2)+1e-8);
                if(k<actor_n)policy_.actor.parameters[k]-=step;
                else if(k<std_start)policy_.critic.parameters[k-actor_n]-=step;
                else policy_.log_std[k-std_start]=std::clamp(policy_.log_std[k-std_start]-step,-5.,2.);
            }
            m.minibatches++;
        }
        m.epochs++;
    }
    if(m.minibatches){m.policy_loss/=m.minibatches;m.value_loss/=m.minibatches;m.clip_fraction/=m.minibatches;}
    double kl=0;for(const auto& t:rollout){const double d=policy_.log_probability(t.observation,t.latent)-t.old_log_probability;kl+=std::exp(std::clamp(d,-60.,60.))-1-d;}
    m.approx_kl=kl/rollout.size();return m;
}
void ActorCritic::save(const std::filesystem::path& file,const std::string& schema)const{
    static_assert(std::endian::native==std::endian::little);
    require(!schema.empty()&&schema.size()<=4096,"Invalid observation schema");
    require(actor.inputs==critic.inputs&&actor.hidden==critic.hidden&&critic.outputs==1&&log_std.size()==actor.outputs,"Incompatible actor/critic architecture");
    (void)actor.forward(std::vector<double>(actor.inputs));(void)critic.forward(std::vector<double>(critic.inputs));
    finite(actor.parameters);finite(critic.parameters);finite(log_std);
    for(double x:log_std)require(x>=-5&&x<=2,"Invalid policy log standard deviation");
    std::vector<std::byte> bytes;
    auto append=[&](const void* p,std::size_t n){auto b=static_cast<const std::byte*>(p);bytes.insert(bytes.end(),b,b+n);};
    const std::array<std::uint32_t,6> header{1,static_cast<std::uint32_t>(actor.inputs),static_cast<std::uint32_t>(actor.outputs),static_cast<std::uint32_t>(actor.hidden),static_cast<std::uint32_t>(schema.size()),0};
    append("TMPPO001",8);append(header.data(),sizeof(header));append(schema.data(),schema.size());
    for(const auto* v:{&actor.parameters,&critic.parameters,&log_std})append(v->data(),v->size()*sizeof(double));
    const auto hash=checksum(bytes);append(&hash,sizeof(hash));
    std::ofstream out(file,std::ios::binary|std::ios::trunc);out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
    if(!out)throw std::runtime_error("Cannot save PPO model");
}
ActorCritic ActorCritic::load(const std::filesystem::path& file,std::string* schema){
    const auto n=std::filesystem::file_size(file);require(n>=40&&n<=32*1024*1024,"Invalid PPO model size");
    std::vector<std::byte> b(n);std::ifstream in(file,std::ios::binary);in.read(reinterpret_cast<char*>(b.data()),n);
    require(bool(in),"Truncated PPO model");require(std::memcmp(b.data(),"TMPPO001",8)==0,"Invalid PPO magic");
    std::array<std::uint32_t,6> h{};std::memcpy(h.data(),b.data()+8,sizeof(h));
    require(h[0]==1&&h[4]>0&&h[4]<=4096&&h[5]==0,"Unsupported PPO model version/schema/flags");
    ActorCritic p(h[1],h[2],h[3]);std::size_t offset=32+h[4];
    const auto count=p.actor.parameters.size()+p.critic.parameters.size()+p.log_std.size();
    require(offset+count*sizeof(double)+8==b.size(),"Invalid PPO model dimensions/length");
    std::uint64_t hash{};std::memcpy(&hash,b.data()+b.size()-8,8);
    require(checksum(std::span(b.data(),b.size()-8))==hash,"PPO checksum mismatch");
    for(auto* v:{&p.actor.parameters,&p.critic.parameters,&p.log_std}){
        std::memcpy(v->data(),b.data()+offset,v->size()*sizeof(double));offset+=v->size()*sizeof(double);finite(*v);
    }
    for(double x:p.log_std)require(x>=-5&&x<=2,"Invalid policy log standard deviation");
    if(schema)schema->assign(reinterpret_cast<const char*>(b.data()+32),h[4]);
    return p;
}
}
