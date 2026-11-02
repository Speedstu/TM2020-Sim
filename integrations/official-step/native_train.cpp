// SPDX-License-Identifier: MIT
// Fully native original-server IPC + SDK PPO. Python is only an external audit.
#include "tm2020/trainer.h"
#include <openssl/evp.h>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/wait.h>
#include <unistd.h>

extern char** environ;
namespace fs = std::filesystem;
namespace {
constexpr char schema[] = "tm2020_official_preinput13_v1|actions=ghost_binary_pedals_i8_steer_v1";
constexpr char server_sha[] = "3b6107824feea402bd32c888e994dcd6df4a10afc8676a2647ac9560ccf0d779";
struct Frame {
    uint32_t magic;
    int32_t engine, origin, offset, count, index;
    std::array<float, 3> controls;
    std::array<float, 10> state;
    int32_t race_ms() const { return engine-origin; }
};
struct Action { uint32_t mode; std::array<float, 3> controls; };
static_assert(sizeof(Frame)==76 && sizeof(Action)==16);
void require(bool ok, const std::string& text) { if (!ok) throw std::runtime_error(text); }
void checked(int code) { require(code==0, tm2020_trainer_last_error()); }
std::string hex(const void* raw, size_t size) {
    auto* bytes = static_cast<const unsigned char*>(raw);
    constexpr char digits[]="0123456789abcdef";
    std::string out; out.reserve(size*2);
    for (size_t i=0;i<size;++i) { out+=digits[bytes[i]>>4]; out+=digits[bytes[i]&15]; }
    return out;
}
class Digest {
    std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx{EVP_MD_CTX_new(),EVP_MD_CTX_free};
public:
    Digest() { require(ctx && EVP_DigestInit_ex(ctx.get(),EVP_sha256(),nullptr)==1,"SHA256 init failed"); }
    void add(const void* p,size_t n) { require(EVP_DigestUpdate(ctx.get(),p,n)==1,"SHA256 update failed"); }
    std::string finish() {
        std::array<unsigned char,32> out{}; unsigned n=0;
        require(EVP_DigestFinal_ex(ctx.get(),out.data(),&n)==1 && n==32,"SHA256 finish failed");
        return hex(out.data(),out.size());
    }
};
std::string file_sha(const fs::path& path) {
    std::ifstream in(path,std::ios::binary);require(bool(in),"Cannot hash "+path.string());
    Digest digest; std::array<char,65536> block{};
    while (in.read(block.data(),block.size()) || in.gcount()) digest.add(block.data(),in.gcount());
    require(in.eof(),"SHA256 read failed");return digest.finish();
}
void transfer(int fd,void* data,size_t size,bool sending) {
    auto* p=static_cast<unsigned char*>(data);
    while(size) {
        pollfd event{fd,short(sending?POLLOUT:POLLIN),0}; int ready;
        do { ready=poll(&event,1,30000); } while (ready<0 && errno==EINTR);
        require(ready>0,"Official engine IPC timeout/error; inspect retained server.log");
        ssize_t n=sending?write(fd,p,size):read(fd,p,size);
        if(n<0 && errno==EINTR)continue;
        require(n>0,"Official engine closed before successor; inspect retained server.log");
        p+=n;size-=size_t(n);
    }
}
class Engine {
    fs::path server, track, ghost, shim;
    pid_t child=-1;int from=-1,to=-1;
    void receive() {
        transfer(from,&state,sizeof(state),false);
        const int64_t relative=int64_t(state.engine)-state.origin-state.offset;
        const int32_t index=relative<0?-1:int32_t(relative/10);
        require(state.magic==0x36304d54 && state.count>0 && state.index==index,"Bad original input boundary");
        for(float x:state.state)require(std::isfinite(x),"Nonfinite engine state");
        double norm=0;for(size_t i=0;i<4;++i)norm+=double(state.state[i])*state.state[i];
        require(std::abs(norm-1)<0.001,"Invalid engine quaternion");
    }
public:
    Frame state{};
    Engine(fs::path s,fs::path m,fs::path g,fs::path lib):
        server(fs::canonical(s)),track(fs::canonical(m)),ghost(fs::canonical(g)),shim(fs::canonical(lib)) {
        require(file_sha(server/"TrackmaniaServer")==server_sha,"Unsupported original server hash");
        require(fs::is_directory(server/"Packs"),"Missing original server Packs");
        auto name=ghost.filename().string();
        require(name.ends_with(".Ghost.Gbx")||name.ends_with(".Replay.Gbx"),"Unsupported ghost name");
    }
    ~Engine(){close();}
    void close() {
        if(child>0){kill(child,SIGKILL);while(waitpid(child,nullptr,0)<0 && errno==EINTR){}child=-1;}
        if(from>=0){::close(from);from=-1;}if(to>=0){::close(to);to=-1;}
    }
    void reset(const fs::path& directory) {
        close();const auto root=fs::absolute(directory);
        require(!fs::exists(root),"Never share or reuse an engine workspace");
        fs::create_directories(root/"UserData/Maps");fs::create_directories(root/"UserData/Replays");
        fs::create_symlink(server/"Packs",root/"Packs");
        fs::create_symlink(server/"TrackmaniaServer",root/"TrackmaniaServer");
        fs::create_symlink(track,root/"UserData/Maps"/track.filename());
        fs::create_symlink(ghost,root/"UserData/Replays"/ghost.filename());
        int commands[2]{-1,-1},frames[2]{-1,-1};
        require(pipe2(commands,O_CLOEXEC)==0,"Cannot create action pipe");
        if(pipe2(frames,O_CLOEXEC)!=0){::close(commands[0]);::close(commands[1]);throw std::runtime_error("Cannot create frame pipe");}
        to=commands[1];from=frames[0];
        int log=open((root/"server.log").c_str(),O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);
        if(log<0){::close(commands[0]);::close(frames[1]);throw std::runtime_error("Cannot create server log");}
        std::vector<std::string> variables;
        for(char** p=environ;*p;++p){std::string v=*p;
            if(!v.starts_with("LD_PRELOAD=") && !v.starts_with("TM2020_STEP_"))variables.push_back(v);}
        variables.push_back("LD_PRELOAD="+shim.string());
        variables.push_back("TM2020_STEP_IN_FD=198");variables.push_back("TM2020_STEP_OUT_FD=199");
        std::vector<char*> env;for(auto& v:variables)env.push_back(v.data());env.push_back(nullptr);
        posix_spawn_file_actions_t actions;
        require(posix_spawn_file_actions_init(&actions)==0,"Cannot initialize spawn actions");
        int err=posix_spawn_file_actions_adddup2(&actions,commands[0],198);
        if(!err)err=posix_spawn_file_actions_adddup2(&actions,frames[1],199);
        if(!err)err=posix_spawn_file_actions_adddup2(&actions,log,STDOUT_FILENO);
        if(!err)err=posix_spawn_file_actions_adddup2(&actions,log,STDERR_FILENO);
        if(!err)err=posix_spawn_file_actions_addchdir_np(&actions,root.c_str());
        std::string exe="./TrackmaniaServer";
        char* argv[]{exe.data(),const_cast<char*>("/nodaemon"),const_cast<char*>("/validatepath=."),nullptr};
        if(!err)err=posix_spawn(&child,exe.c_str(),&actions,nullptr,argv,env.data());
        posix_spawn_file_actions_destroy(&actions);
        ::close(commands[0]);::close(frames[1]);::close(log);
        require(err==0,"Cannot launch original server: "+std::string(std::strerror(err)));
        receive();while(state.race_ms()<0)step(nullptr);
        require(state.race_ms()==0,"Missing exact race-zero boundary");
    }
    void step(const std::array<float,3>* controls) {
        Action action{controls?1u:0u,controls?*controls:std::array<float,3>{}};
        if(controls)require(state.index>=0 && state.index<state.count,"Input tape exhausted");
        transfer(to,&action,sizeof(action),true);Frame previous=state;receive();
        require(state.engine==previous.engine+10 && state.origin==previous.origin &&
            state.offset==previous.offset && state.count==previous.count,"Clock gap or race identity change");
    }
};
using Observation=std::array<double,13>;
Observation observe(const Frame& s,const std::array<double,3>& origin,const std::array<float,3>& previous) {
    Observation result{};
    for(size_t i=0;i<3;++i)result[i]=(double(s.state[4+i])-origin[i])/100.0;
    for(size_t i=0;i<4;++i)result[3+i]=s.state[i];
    for(size_t i=0;i<3;++i){result[7+i]=double(s.state[7+i])/100.0;result[10+i]=previous[i];}
    return result;
}
struct TrainerCloser {void operator()(void* h)const{tm2020_trainer_close(h);}};
}
int main(int argc,char** argv)try {
    require(argc>=7 && argc<=10,"Usage: tm2020_official_train SERVER MAP GHOST SHIM INITIAL.checkpoint OUTPUT [episodes=3] [horizon=503] [repeat=5]");
    signal(SIGPIPE,SIG_IGN);
    const size_t episodes=argc>7?std::stoul(argv[7]):3,horizon=argc>8?std::stoul(argv[8]):503,repeat=argc>9?std::stoul(argv[9]):5;
    require(episodes>=1 && episodes<=100 && horizon>=1 && horizon<=100000 && repeat>=1 && repeat<=100,"Invalid training bounds");
    require(episodes*((horizon+repeat-1)/repeat)<=65536,"Native rollout bound exceeded");
    auto output=fs::absolute(argv[6]);require(!fs::exists(output),"Training output must be new");
    Engine engine(argv[1],argv[2],argv[3],argv[4]);
    tm2020_trainer_handle handle{};checked(tm2020_trainer_create(13,3,32,2026,schema,&handle));
    std::unique_ptr<void,TrainerCloser> trainer(handle);
    checked(tm2020_trainer_resume(handle,argv[5]));
    fs::create_directories(output);
    checked(tm2020_trainer_export(handle,(output/"behavior.tmppo").c_str()));
    std::ofstream physics(output/"physics.csv");
    physics<<"episode,index,advanced_ticks,trace_sha256,before_hex,after_hex\n";
    size_t transitions=0;std::vector<double> scores;
    for(size_t episode=0;episode<episodes;++episode){
        engine.reset(output/("engine-"+std::to_string(episode)));
        require(int64_t(engine.state.index)+int64_t(horizon)<engine.state.count,"Input tape shorter than task horizon");
        const auto initial=engine.state;
        std::array<double,3> origin{initial.state[4],initial.state[5],initial.state[6]};
        double w=initial.state[0],x=initial.state[1],y=initial.state[2],z=initial.state[3];
        std::array<double,3> axis{2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)};
        std::array<float,3> previous{};auto observation=observe(initial,origin,previous);
        size_t ticks=0,index=0;double score=0;
        while(ticks<horizon){
            std::array<double,3> sampled{};double value{};
            checked(tm2020_trainer_sample(handle,observation.data(),13,sampled.data(),3,&value));
            try {
                const int steering=int(std::nearbyint(sampled[2]*127.0));
                std::array<float,3> controls{float(double(steering)/127.0),float(sampled[0]>=0),float(sampled[1]>=0)};
                auto before=engine.state;const auto count=std::min(repeat,horizon-ticks);Digest digest;
                for(size_t i=0;i<count;++i){engine.step(&controls);digest.add(engine.state.state.data(),40);}
                ticks+=count;previous=controls;observation=observe(engine.state,origin,previous);
                double reward=0;for(size_t i=0;i<3;++i)reward+=(double(engine.state.state[4+i])-double(before.state[4+i]))*axis[i];
                checked(tm2020_trainer_observe(handle,reward,observation.data(),13,0,ticks==horizon,double(count)/double(repeat)));
                physics<<episode<<','<<index<<','<<count<<','<<digest.finish()<<','
                    <<hex(before.state.data(),40)<<','<<hex(engine.state.state.data(),40)<<'\n';
                score+=reward;++index;++transitions;
            }catch(...){tm2020_trainer_cancel(handle);throw;}
        }
        scores.push_back(score);
        std::cout<<"NATIVE_OFFICIAL_EPISODE "<<episode<<" transitions="<<index<<" reward="<<std::setprecision(17)<<score<<'\n';
    }
    engine.close();physics.flush();require(bool(physics),"Cannot write native physics evidence");
    checked(tm2020_trainer_rollout_csv(handle,(output/"rollout.csv").c_str()));
    tm2020_trainer_metrics metrics{};metrics.size_bytes=sizeof(metrics);metrics.api_version=TM2020_TRAINER_API_VERSION;
    checked(tm2020_trainer_update(handle,&metrics));
    checked(tm2020_trainer_checkpoint(handle,(output/"training.checkpoint").c_str()));
    checked(tm2020_trainer_export(handle,(output/"updated.tmppo").c_str()));
    std::ofstream report(output/"report.json");
    report<<"{\"schema\":\"tm2020_native_official_ppo_v1\",\"serverSha256\":\""<<server_sha
        <<"\",\"shimSha256\":\""<<file_sha(argv[4])<<"\",\"transitions\":"<<transitions
        <<",\"episodes\":"<<episodes<<",\"horizon\":"<<horizon<<",\"repeat\":"<<repeat
        <<",\"optimizerSteps\":"<<metrics.optimizer_steps<<",\"pythonRuntimeUsed\":false"
        <<",\"checkpointForkUsed\":false,\"completeIndependentSimulatorQualified\":false,\"generalRacePolicyQualified\":false}\n";
    report.flush();require(bool(report),"Cannot write native report");
    std::cout<<"PASS FULLY_NATIVE_OFFICIAL_PPO transitions="<<transitions<<" python_runtime=false\n";
}catch(const std::exception& e){std::cerr<<"NATIVE_OFFICIAL_ERROR "<<e.what()<<'\n';return 1;}
