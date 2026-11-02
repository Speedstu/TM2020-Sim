#include "tm2020/rl.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <locale>
#include <sstream>
#include <stdexcept>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#endif
namespace tm2020::rl {
namespace {
void require(bool ok,const char* message){if(!ok)throw std::invalid_argument(message);}
std::uint64_t hash(std::span<const std::byte> bytes){
    std::uint64_t h=14695981039346656037ull;
    for(auto b:bytes){h^=std::to_integer<unsigned char>(b);h*=1099511628211ull;}return h;
}
std::string encode_rng(const std::mt19937_64& rng){
    std::ostringstream out;out.imbue(std::locale::classic());out<<rng;return out.str();
}
std::mt19937_64 decode_rng(const std::string& text){
    std::istringstream in(text);in.imbue(std::locale::classic());std::mt19937_64 rng;
    require(bool(in>>rng),"Invalid checkpoint RNG");in>>std::ws;
    require(in.eof(),"Trailing checkpoint RNG content");return rng;
}
void finite(std::span<const double> v){for(double x:v)require(std::isfinite(x),"Non-finite checkpoint state");}
}
void PpoTrainer::save_checkpoint(const std::filesystem::path& file,const std::string& schema,
                                 const std::mt19937_64& sampler)const{
    static_assert(std::endian::native==std::endian::little);
    require(!schema.empty()&&schema.size()<=4096,"Invalid checkpoint schema");
    const auto& p=policy_;
    require(p.actor.inputs==p.critic.inputs&&p.actor.hidden==p.critic.hidden&&p.critic.outputs==1&&
        p.log_std.size()==p.actor.outputs,"Incompatible checkpoint architecture");
    (void)p.deterministic(std::vector<double>(p.actor.inputs));
    const auto count=p.actor.parameters.size()+p.critic.parameters.size()+p.log_std.size();
    require(first_moment_.size()==count&&second_moment_.size()==count,"Invalid optimizer shape");
    for(const auto* v:{&p.actor.parameters,&p.critic.parameters,&p.log_std,&first_moment_,&second_moment_})finite(*v);
    for(double x:p.log_std)require(x>=-5&&x<=2,"Invalid checkpoint policy variance");
    for(double x:second_moment_)require(x>=0,"Negative Adam second moment");
    const auto shuffle=encode_rng(rng_),sampling=encode_rng(sampler);
    require(shuffle.size()<=32768&&sampling.size()<=32768,"Checkpoint RNG size exceeded");
    std::vector<std::byte> bytes;
    auto append=[&](const void* data,std::size_t size){const auto b=static_cast<const std::byte*>(data);bytes.insert(bytes.end(),b,b+size);};
    const std::array<std::uint32_t,6> header{1,static_cast<std::uint32_t>(p.actor.inputs),static_cast<std::uint32_t>(p.actor.outputs),
        static_cast<std::uint32_t>(p.actor.hidden),static_cast<std::uint32_t>(schema.size()),0};
    const std::array values{config_.learning_rate,config_.gamma,config_.lambda,config_.clip,config_.value_coefficient,
        config_.latent_entropy_coefficient,config_.max_gradient_norm,config_.target_kl};
    const std::array<std::uint64_t,2> sizes{config_.epochs,config_.minibatch};
    const std::array<std::uint32_t,2> lengths{static_cast<std::uint32_t>(shuffle.size()),static_cast<std::uint32_t>(sampling.size())};
    append("TMTRAIN1",8);append(header.data(),sizeof(header));append(&updates_,8);
    append(values.data(),sizeof(values));append(sizes.data(),sizeof(sizes));append(lengths.data(),sizeof(lengths));
    append(schema.data(),schema.size());
    for(const auto* v:{&p.actor.parameters,&p.critic.parameters,&p.log_std,&first_moment_,&second_moment_})append(v->data(),v->size()*sizeof(double));
    append(shuffle.data(),shuffle.size());append(sampling.data(),sampling.size());const auto digest=hash(bytes);append(&digest,8);
    auto temporary=file;temporary+=".tmp";
    require(!std::filesystem::exists(temporary),"Checkpoint temporary exists; inspect retained recovery file first");
#ifdef _WIN32
    const HANDLE output=CreateFileW(temporary.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(output==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot exclusively create checkpoint temporary");
    DWORD written{};
    const bool stored=WriteFile(output,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)&&
        written==bytes.size()&&FlushFileBuffers(output);
    const bool closed=CloseHandle(output)!=0;
    if(!stored||!closed)throw std::runtime_error("Durable checkpoint write failed; temporary retained");
#else
    {
        std::ofstream out(temporary,std::ios::binary);out.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());
        out.flush();if(!out)throw std::runtime_error("Checkpoint write failed; temporary retained");
        out.close();if(!out)throw std::runtime_error("Checkpoint close failed; temporary retained");
    }
#endif
#ifdef _WIN32
    if(!MoveFileExW(temporary.c_str(),file.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
        throw std::runtime_error("Atomic checkpoint replacement failed; temporary retained");
#else
    std::filesystem::rename(temporary,file);
#endif
}
void PpoTrainer::load_checkpoint(const std::filesystem::path& file,const std::string& schema,std::mt19937_64& sampler){
    const auto size=std::filesystem::file_size(file);
    require(size>=136&&size<=64*1024*1024,"Invalid training checkpoint size");
    std::vector<std::byte> bytes(size);std::ifstream in(file,std::ios::binary);in.read(reinterpret_cast<char*>(bytes.data()),size);
    require(bool(in),"Truncated training checkpoint");
    std::uint64_t digest{};std::memcpy(&digest,bytes.data()+size-8,8);
    require(hash(std::span(bytes.data(),bytes.size()-8))==digest,"Training checkpoint checksum mismatch");
    require(std::memcmp(bytes.data(),"TMTRAIN1",8)==0,"Invalid training checkpoint magic");
    std::size_t offset=8;
    auto read=[&](void* target,std::size_t count){require(offset<=size-8&&count<=size-8-offset,"Truncated checkpoint field");std::memcpy(target,bytes.data()+offset,count);offset+=count;};
    std::array<std::uint32_t,6> h{};read(h.data(),sizeof(h));
    require(h[0]==1&&h[5]==0&&h[4]>0&&h[4]<=4096,"Unsupported training checkpoint header");
    require(h[1]==policy_.actor.inputs&&h[2]==policy_.actor.outputs&&h[3]==policy_.actor.hidden,
        "Training checkpoint architecture mismatch");
    ActorCritic candidate(h[1],h[2],h[3]);std::uint64_t steps{};read(&steps,8);
    std::array<double,8> v{};std::array<std::uint64_t,2> sizes{};std::array<std::uint32_t,2> lengths{};
    read(v.data(),sizeof(v));read(sizes.data(),sizeof(sizes));read(lengths.data(),sizeof(lengths));finite(v);
    require(sizes[0]<=1000&&sizes[1]>0&&sizes[1]<=100000000,"Invalid checkpoint batch configuration");
    require(lengths[0]>0&&lengths[0]<=32768&&lengths[1]>0&&lengths[1]<=32768,"Invalid checkpoint RNG lengths");
    std::string stored_schema(h[4],'\0');read(stored_schema.data(),stored_schema.size());
    require(stored_schema==schema,"Training checkpoint observation schema mismatch");
    PpoConfig config{v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],static_cast<std::size_t>(sizes[0]),static_cast<std::size_t>(sizes[1])};
    PpoTrainer restored(candidate,config);
    for(auto* values:{&candidate.actor.parameters,&candidate.critic.parameters,&candidate.log_std,&restored.first_moment_,&restored.second_moment_}){
        read(values->data(),values->size()*sizeof(double));finite(*values);
    }
    for(double x:candidate.log_std)require(x>=-5&&x<=2,"Invalid checkpoint policy variance");
    for(double x:restored.second_moment_)require(x>=0,"Negative checkpoint second moment");
    std::string shuffle(lengths[0],'\0'),sampling(lengths[1],'\0');read(shuffle.data(),shuffle.size());read(sampling.data(),sampling.size());
    require(offset==size-8,"Trailing training checkpoint payload");
    auto shuffle_rng=decode_rng(shuffle),sampling_rng=decode_rng(sampling);
    // All validation completed. Moves use standard allocator storage; observers
    // continue referring to the original ActorCritic object.
    policy_=std::move(candidate);config_=config;rng_=shuffle_rng;sampler=sampling_rng;
    first_moment_=std::move(restored.first_moment_);second_moment_=std::move(restored.second_moment_);updates_=steps;
}
}
