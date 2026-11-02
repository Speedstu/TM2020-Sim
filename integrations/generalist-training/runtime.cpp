// SPDX-License-Identifier: GPL-3.0-or-later
// Explicit offline internal worker. The hook runs policy/commands on the
// original physics consumer thread. No SendInput, controller, polling pose,
// external perception service, DllMain hook or automatic activation.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include "internal_hook.hpp"
#include "tm2020/internal_tick.hpp"
#include "tm2020/internal_input_record.hpp"
#include "tm2020/hybrid_actions.hpp"
#include "tm2020/read_only_live.hpp"
#include "tm2020/rl.hpp"
#include "tm2020/observation_history.hpp"
#include "tm2020/trajectory_hybrid.hpp"
#include "fast_training.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <string>
#include <thread>
using namespace tm2020::internal;
namespace fs=std::filesystem;
extern "C" { void* tm2020_early_trampoline{}; void* tm2020_input_trampoline{};
    tm2020::internal::Controls tm2020_owned_decoder_before{}; }
namespace {
constexpr std::uint32_t consumer_rva=0x83de60;
constexpr std::uint32_t input_decoder_rva=0x12bce40;
constexpr std::size_t maximum_rows=65536;
using Consumer=void(*)(void*,void*,std::uint32_t,float);
using EarlyConsumer=void(*)(void*);
// The game compiler keeps values in volatile registers across this particular
// leaf call (notably R10 and XMM2..5). A C++ detour may clobber them. Preserve
// the complete volatile input context, run the BEFORE callback, restore it,
// then tail-call the original. Its own register/memory effects remain intact.
extern "C" __attribute__((naked,noinline,used)) void early_entry(){
    __asm__ volatile(
        "sub $0xe8, %rsp\n"
        "mov %rax,0x20(%rsp)\nmov %rcx,0x28(%rsp)\nmov %rdx,0x30(%rsp)\n"
        "mov %r8,0x38(%rsp)\nmov %r9,0x40(%rsp)\nmov %r10,0x48(%rsp)\nmov %r11,0x50(%rsp)\n"
        "movdqu %xmm0,0x60(%rsp)\nmovdqu %xmm1,0x70(%rsp)\nmovdqu %xmm2,0x80(%rsp)\n"
        "movdqu %xmm3,0x90(%rsp)\nmovdqu %xmm4,0xa0(%rsp)\nmovdqu %xmm5,0xb0(%rsp)\n"
        "call tm2020_early_before\n"
        "movdqu 0x60(%rsp),%xmm0\nmovdqu 0x70(%rsp),%xmm1\nmovdqu 0x80(%rsp),%xmm2\n"
        "movdqu 0x90(%rsp),%xmm3\nmovdqu 0xa0(%rsp),%xmm4\nmovdqu 0xb0(%rsp),%xmm5\n"
        "mov 0x20(%rsp),%rax\nmov 0x28(%rsp),%rcx\nmov 0x30(%rsp),%rdx\n"
        "mov 0x38(%rsp),%r8\nmov 0x40(%rsp),%r9\nmov 0x48(%rsp),%r10\nmov 0x50(%rsp),%r11\n"
        "add $0xe8,%rsp\njmp *tm2020_early_trampoline(%rip)\n");
}
// At the sole pinned callsite 0x12bf823, the caller saves the macro clock at
// caller RSP+0x58. Read that slot, the fifth argument and return address.
extern "C" __attribute__((naked,noinline,used)) void input_entry(){
    __asm__ volatile(
        "sub $0xe8, %rsp\n"
        "mov %rax,0x30(%rsp)\nmov %rcx,0x38(%rsp)\nmov %rdx,0x40(%rsp)\n"
        "mov %r8,0x48(%rsp)\nmov %r9,0x50(%rsp)\nmov %r10,0x58(%rsp)\nmov %r11,0x60(%rsp)\n"
        "movdqu %xmm0,0x70(%rsp)\nmovdqu %xmm1,0x80(%rsp)\nmovdqu %xmm2,0x90(%rsp)\n"
        "movdqu %xmm3,0xa0(%rsp)\nmovdqu %xmm4,0xb0(%rsp)\nmovdqu %xmm5,0xc0(%rsp)\n"
        "mov %rdx,%rcx\nmov %r8,%rdx\nmov 0x110(%rsp),%r8\nmov 0x148(%rsp),%r9d\n"
        "mov %rdi,0x20(%rsp)\nmov 0xe8(%rsp),%rax\nmov %rax,0x28(%rsp)\n"
        "call tm2020_input_before\n"
        "movdqu 0x70(%rsp),%xmm0\nmovdqu 0x80(%rsp),%xmm1\nmovdqu 0x90(%rsp),%xmm2\n"
        "movdqu 0xa0(%rsp),%xmm3\nmovdqu 0xb0(%rsp),%xmm4\nmovdqu 0xc0(%rsp),%xmm5\n"
        "mov 0x30(%rsp),%rax\nmov 0x38(%rsp),%rcx\nmov 0x40(%rsp),%rdx\n"
        "mov 0x48(%rsp),%r8\nmov 0x50(%rsp),%r9\nmov 0x58(%rsp),%r10\nmov 0x60(%rsp),%r11\n"
        "add $0xe8,%rsp\njmp *tm2020_input_trampoline(%rip)\n");
}
// Owned fixture in a genuine PE image section (WRITECOPY allocation), rather
// than VirtualAlloc memory. Never called on the Trackmania activation path.
extern "C" __attribute__((naked,noinline)) void owned_image_consumer(){
    __asm__ volatile(
        ".byte 0x48,0x8b,0xc4,0x53,0x41,0x55,0x48,0x81,0xec,0xa8,0,0,0\n"
        "movss 0x98(%rdx), %xmm0\nmovss %xmm0, 0(%rcx)\n"
        "movss 0x9c(%rdx), %xmm0\nmovss %xmm0, 4(%rcx)\n"
        "movss 0xa0(%rdx), %xmm0\nmovss %xmm0, 8(%rcx)\n"
        "add $0xa8, %rsp\npop %r13\npop %rbx\nret\n");
}
extern "C" __attribute__((naked,noinline)) void owned_early_consumer(){
    __asm__ volatile(
        ".byte 0x48,0x83,0xec,0x28,0x4c,0x8b,0x49,0x08,0x4c,0x8b,0xd9,0x49,0x8d,0x89,0x80,0x12,0,0\n"
        "mov (%r11), %rax\nmov 0x110(%rax), %rax\n"
        // These reads stand for Sport's cached pedal booleans, which must
        // already see this tick's action, before wheel spin/steering.
        "movss 0x98(%r9), %xmm0\nmovss %xmm0, (%rax)\n"
        "movss 0x9c(%r9), %xmm0\nmovss %xmm0, 4(%rax)\n"
        "movss 0xa0(%r9), %xmm0\nmovss %xmm0, 8(%rax)\n"
        "add $0x28, %rsp\nret\n");
}
extern "C" void owned_input_return();
extern "C" __attribute__((naked,noinline)) void owned_input_decoder(){
    __asm__ volatile(
        ".byte 0x4c,0x89,0x4c,0x24,0x20,0x48,0x89,0x4c,0x24,0x08,0x55,0x53,0x57,0x41,0x55,0x41,0x56\n"
        "mov 0x50(%rsp),%rax\nmov 8(%rax),%rax\n"
        "movss 0x98(%rax),%xmm0\nmovss %xmm0,tm2020_owned_decoder_before(%rip)\n"
        "movss 0x9c(%rax),%xmm0\nmovss %xmm0,tm2020_owned_decoder_before+4(%rip)\n"
        "movss 0xa0(%rax),%xmm0\nmovss %xmm0,tm2020_owned_decoder_before+8(%rip)\n"
        "movss 8(%r8),%xmm0\nmovss %xmm0,0x98(%rax)\n"
        "movss 12(%r8),%xmm0\nmovss %xmm0,0x9c(%rax)\n"
        "movss 4(%r8),%xmm0\nmovss %xmm0,0xa0(%rax)\n"
        "pop %r14\npop %r13\npop %rdi\npop %rbx\npop %rbp\nret\n");
}
extern "C" __attribute__((naked,noinline)) int owned_input_call(void*){
    __asm__ volatile(
        "push %rdi\npush %r14\nsub $0x68,%rsp\n"
        "mov (%rcx),%rdi\nmov 32(%rcx),%r14d\nmov 8(%rcx),%rdx\nmov 16(%rcx),%r8\n"
        "mov 24(%rcx),%rax\nmov %rax,0x20(%rsp)\nmov %r14d,0x58(%rsp)\nxor %r9d,%r9d\nxor %ecx,%ecx\n"
        "movabs $0x5a37c910ab82fe64,%r11\n"
        "call owned_input_decoder\n.global owned_input_return\nowned_input_return:\n"
        "movabs $0x5a37c910ab82fe64,%rax\ncmp %r11,%rax\nsete %al\nmovzbl %al,%eax\n"
        "add $0x68,%rsp\npop %r14\npop %rdi\nret\n");
}
extern "C" __attribute__((naked,noinline)) int owned_register_probe(void*){
    __asm__ volatile(
        "sub $0x28,%rsp\nmovabs $0x5a37c910ab82fe64,%r10\n"
        "movq %r10,%xmm2\nmovq %r10,%xmm3\nmovq %r10,%xmm4\nmovq %r10,%xmm5\n"
        "call owned_early_consumer\nmovabs $0x5a37c910ab82fe64,%r11\n"
        "cmp %r11,%r10\njne 1f\n"
        "movq %xmm2,%rdx\ncmp %r11,%rdx\njne 1f\n"
        "movq %xmm3,%rdx\ncmp %r11,%rdx\njne 1f\n"
        "movq %xmm4,%rdx\ncmp %r11,%rdx\njne 1f\n"
        "movq %xmm5,%rdx\ncmp %r11,%rdx\njne 1f\n"
        "mov $1,%eax\njmp 2f\n1: xor %eax,%eax\n2: add $0x28,%rsp\nret\n");
}
struct Row {std::uintptr_t manager{},vehicle{},body{};std::uint32_t ms{},race_start{};float dt{};
    std::array<float,22> rigid{};Controls before{},written{},after{},recorded{};std::int32_t gear=-999;std::uint32_t wrote{},fault{},valid_state{},valid_map{},bound_owner{},input_stage{},physical_write{},consumer_verified{};};
struct Context {
    bool input_mode{},has_input{},input_smoke_test{};std::uint32_t input_tick{};std::uintptr_t input_vehicle{},input_record{};DWORD consumer_thread{};
    Controls fixture_action{1,0,.25f};std::atomic<unsigned> consumer_mismatches{};bool owned_pipeline{};
    std::string map_uid;
    bool repeat_resets{};std::atomic<bool> episode_idle{};std::uint32_t active_start{};std::atomic<unsigned> episodes{};
    Controller controller;bool fixture{},control{};std::array<float,3> start{};
    std::uintptr_t expected_manager{},expected_vehicle{},expected_body{};
    std::uint32_t expected_start{},decision_ticks{5};std::size_t observation_width{48};bool reset_rebind{};
    std::atomic<bool> stop{},session_valid{},map_valid{},neutral_ack{};std::atomic<ULONGLONG> heartbeat{};
    std::atomic<std::uint32_t> count{};std::array<Row,maximum_rows> rows{};
    std::uintptr_t candidate{};std::atomic<std::uintptr_t> bound{};std::atomic_flag busy=ATOMIC_FLAG_INIT;std::uint32_t candidate_ms{},candidate_ticks{};DWORD physics_thread{};
    Controls previous{};std::unique_ptr<tm2020::rl::ActorCritic> policy;
    std::unique_ptr<tm2020::hybrid::Tracker> hybrid;tm2020::hybrid::Cursor hybrid_cursor;
    std::unique_ptr<tm2020::rl::ObservationHistory> history;bool first=true;
    HMODULE perception{};void* environment{};
    int (*observe)(void*,const float*,std::uint32_t,double*){};
    int (*track)(void*,const float*,std::uint32_t){};
    void (*close)(void*){};
    ~Context(){if(environment&&close)close(environment);if(perception)FreeLibrary(perception);}
};
std::atomic<Context*> current{};std::atomic<unsigned> inflight{};Consumer original{};EarlyConsumer early_original{};
ConsumerHook hook;
ConsumerHook input_hook;
void require(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
template<class T> bool read(std::uintptr_t at,T& out)noexcept{
    SIZE_T got{};return at>=0x10000&&ReadProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(at),&out,sizeof(out),&got)&&got==sizeof(out);
}
bool offline_namespace(){
    // Wine resolves /proc/self in its own isolated Proton namespace. The host
    // launcher independently verifies the actual game's network namespace.
    std::ifstream routes("Z:/proc/self/net/route");if(!routes)return false;
    std::string line;std::getline(routes,line);
    while(std::getline(routes,line)){const auto end=line.find_first_of(" \t");if(line.substr(0,end)!="lo")return false;}
    std::ifstream ipv6("Z:/proc/self/net/ipv6_route");if(!ipv6)return false;
    while(std::getline(ipv6,line)){const auto at=line.find_last_not_of(" \t\r");if(at!=std::string::npos&&line.substr(line.find_last_of(" \t",at)+1,at-line.find_last_of(" \t",at))!="lo")return false;}
    return true;
}
bool map_matches(const std::string& expected){
    const auto mapping=OpenFileMappingW(FILE_MAP_READ,FALSE,L"ManiaPlanet_Telemetry");if(!mapping)return false;
    const auto data=static_cast<const unsigned char*>(MapViewOfFile(mapping,FILE_MAP_READ,0,0,4096));
    bool result=false;
    if(data){std::array<unsigned char,560> copy{};std::memcpy(copy.data(),data,copy.size());
        std::uint32_t version{},size{},state{};std::memcpy(&version,copy.data()+32,4);std::memcpy(&size,copy.data()+36,4);std::memcpy(&state,copy.data()+44,4);
        std::size_t n{};while(n<64&&copy[112+n])++n;
        result=std::memcmp(copy.data(),"ManiaPlanet_Telemetry",20)==0&&(version==2||version==3)&&size>=560&&state==2&&
            std::string(reinterpret_cast<char*>(copy.data()+112),n)==expected;
        UnmapViewOfFile(data);
    }CloseHandle(mapping);return result;
}
bool snapshot(void* manager,void* vehicle,std::uint32_t ms,float dt,PhysicsTick& s,std::uint32_t& start)noexcept{
    s.manager=reinterpret_cast<std::uintptr_t>(manager);s.vehicle=reinterpret_cast<std::uintptr_t>(vehicle);s.timestamp_ms=ms;s.interval=dt;
    std::uint32_t handle{},index{},count{};std::uintptr_t ids{},states{};
    if(!read(s.vehicle+0x10,handle)||handle>=65536||!read(s.manager+0xb0,ids)||
       !read(ids+handle*4,index)||!read(s.manager+0x78,count)||index>=count||count>65536||
       !read(s.manager+0x70,states))return false;
    s.body=states+std::uintptr_t(index)*0x58;
    if(!read(s.body,s.rigid)||!read(s.vehicle+0x12d8,start))return false;
    s.owner_verified=true;s.race_running=std::int32_t(ms-start)>=0;
    return true;
}
void load_policy(Context& c,const std::string& model,const std::string& perception,const std::string& map,const std::string& packs){
    {std::ifstream test(model);std::string tag,uid;std::getline(test,tag);std::getline(test,uid);
     if(tag=="TM2020_BOUNDED_INPUT_RECORDING_TEST_V1"){
        require(c.input_mode&&!c.map_uid.empty()&&uid==c.map_uid,"Input recording test requires exact map and normal decoder mode");
        c.input_smoke_test=true;c.decision_ticks=1;return;
     }}
    {std::ifstream input(model,std::ios::binary);std::array<char,8> signature{};input.read(signature.data(),8);
     if(input&&std::memcmp(signature.data(),"TMHYB001",8)==0){
        auto hybrid=std::make_unique<tm2020::hybrid::Tracker>(tm2020::hybrid::Tracker::load(model));
        require(c.map_uid.empty()||hybrid->uid==c.map_uid,"Hybrid asset is for another map");
        require(hybrid->map_sha==tm2020::live::file_sha256(fs::path(map).wstring()),"Hybrid map content hash differs");
        if(hybrid->version==4){
            std::array<wchar_t,32768> executable{};GetModuleFileNameW(nullptr,executable.data(),executable.size());
            require(_wcsicmp(fs::path(executable.data()).filename().c_str(),L"Trackmania.exe")!=0||c.input_mode,
                "Learned v4 policy requires the causal normal-input mode");
        }
        c.hybrid=std::move(hybrid);c.decision_ticks=1;c.first=true;return;
     }}
    std::string schema;c.policy=std::make_unique<tm2020::rl::ActorCritic>(tm2020::rl::ActorCritic::load(model,&schema));
    if(schema.starts_with(TMFAST_PREVIEW_SCHEMA)){c.observation_width=72;c.decision_ticks=5;}
    else if(schema.starts_with(TMFAST_SCHEMA_100HZ))c.decision_ticks=1;
    else{require(schema.starts_with(TMFAST_SCHEMA),"Policy perception schema differs");c.decision_ticks=5;}
    const auto frames=tm2020::rl::observation_frames(c.policy->actor.inputs,c.observation_width);
    c.history=std::make_unique<tm2020::rl::ObservationHistory>(c.observation_width,frames);
    const auto outputs=c.policy->actor.outputs;require((outputs==1&&schema.ends_with("steering_direct1"))||(outputs==3&&(schema.ends_with("pedals_direct3")||schema.ends_with("hybrid_continuous_v1")))||(outputs==19&&schema.ends_with("hybrid_discrete17_v1"))||(outputs==35&&schema.ends_with("hybrid_discrete33_v1")),"Unsupported action distribution/schema");
    for(std::size_t h=0;h<c.policy->actor.hidden;++h)for(std::size_t frame=0;frame<frames;++frame)
        for(std::size_t channel:{13u,14u})require(c.policy->actor.parameters[h*c.policy->actor.inputs+frame*c.observation_width+channel]==0.,"Policy consumes an unqualified contact/turbo channel");
    c.perception=LoadLibraryW(fs::path(perception).c_str());require(c.perception,"Cannot load in-process map encoder");
    using Open=void*(*)(const char*,const char*,const char*,std::uint32_t);
    auto open=reinterpret_cast<Open>(GetProcAddress(c.perception,"tmfast_open"));
    c.observe=reinterpret_cast<decltype(c.observe)>(GetProcAddress(c.perception,c.observation_width==72?"tmgen_observe72":"tmgen_observe"));
    c.track=reinterpret_cast<decltype(c.track)>(GetProcAddress(c.perception,"tmgen_track_pose"));
    c.close=reinterpret_cast<decltype(c.close)>(GetProcAddress(c.perception,"tmfast_close"));
    require(open&&c.observe&&c.track&&c.close,"In-process perception ABI missing");c.environment=open(map.c_str(),packs.c_str(),"",4000);require(c.environment,"Cannot parse owned map/packs in process");
    std::array<float,24> warm{};std::copy(c.start.begin(),c.start.end(),warm.begin());warm[3]=warm[7]=warm[11]=1;
    std::array<double,72> x{};require(c.observe(c.environment,warm.data(),1,x.data())==0,"Perception warmup failed");
    c.history->reset(std::span<const double>(x.data(),c.observation_width));c.policy->actor.forward(c.history->values);c.first=true;
}
bool infer(void* opaque,const PhysicsTick& tick,Controls& command)noexcept{
    auto& c=*static_cast<Context*>(opaque);
    if(c.fixture){command=c.fixture_action;return true;}
    try{
        if(c.input_smoke_test){
            std::uint32_t start{};if(!read(tick.vehicle+0x12d8,start)||tick.timestamp_ms<start)return false;
            const auto elapsed=tick.timestamp_ms-start;
            // Bounded recording diagnostic: 0.8 s total gas, alternating small
            // steer, brake/neutral. No trajectory or record claim.
            if(elapsed<400)command={1,0,13.f/127.f};
            else if(elapsed<800)command={0,1,-13.f/127.f};
            else if(elapsed<1200)command={1,0,-13.f/127.f};
            else if(elapsed<2000)command={0,1,13.f/127.f};
            else command={};
            return true;
        }
        if(c.hybrid){
            std::uint32_t start{};if(!read(tick.vehicle+0x12d8,start)||std::int32_t(tick.timestamp_ms-start)<0)return false;
            return c.hybrid->action(c.hybrid_cursor,tick.rigid.data(),tick.timestamp_ms-start,command);
        }
        std::array<float,24> raw{};
        std::copy_n(tick.rigid.data()+9,3,raw.data());std::copy_n(tick.rigid.data(),9,raw.data()+3);
        std::copy_n(tick.rigid.data()+16,3,raw.data()+12);
        std::copy_n(tick.rigid.data()+19,3,raw.data()+21);
        raw[15]=c.previous.gas;raw[16]=c.previous.brake;raw[17]=c.previous.steer;
        std::int32_t gear{};if(!read(tick.vehicle+0x15dc,gear)||gear<-1||gear>16)return false;
        raw[18]=float(gear);
        // These two channels are required to have exactly zero model weights;
        // no guessed contact/turbo field is used in a deployed policy.
        raw[19]=raw[20]=0.;std::array<double,72> x{};
        if(c.observe(c.environment,raw.data(),c.first?1:0,x.data()))return false;
        const auto observation=std::span<const double>(x.data(),c.observation_width);
        if(c.first){c.history->reset(observation);c.first=false;}else c.history->push(observation);
        const auto values=c.policy->actor.forward(c.history->values);
        return decode_actions(values,command);
    }catch(...){return false;}
}
template<class Next> void dispatch(void* manager,void* vehicle,std::uint32_t ms,float dt,Next next,std::uintptr_t input_record=0)noexcept{
    inflight.fetch_add(1,std::memory_order_acq_rel);auto* c=current.load(std::memory_order_acquire);
    if(c&&c->busy.test_and_set(std::memory_order_acquire)){if(c->control)c->stop=true;next();inflight.fetch_sub(1,std::memory_order_acq_rel);return;}
    Row* row=nullptr;PhysicsTick state;std::uint32_t race_start{};bool wrote=false;
    if(c&&snapshot(manager,vehicle,ms,dt,state,race_start)){
        state.session_verified=c->session_valid.load();
        const auto n=c->count.fetch_add(1);if(n<maximum_rows){row=&c->rows[n];*row=Row{};
            row->manager=state.manager;row->vehicle=state.vehicle;row->body=state.body;row->ms=ms;row->dt=dt;row->race_start=race_start;
            row->rigid=state.rigid;row->input_stage=input_record?1:0;read(state.vehicle+0x98,row->before);
            read(state.vehicle+0x15dc,row->gear);row->valid_state=valid(state);row->valid_map=c->map_valid.load();
        }else c->stop=true;
        const CandidateIdentity prior{c->expected_manager,c->expected_vehicle,c->expected_body,c->expected_start};
        const bool expected_owner=!c->control||c->fixture||qualified_candidate(prior,state,race_start,c->reset_rebind);
        if(c->repeat_resets&&c->bound&&expected_owner&&!c->stop.load()&&c->map_valid.load()&&
           GetCurrentThreadId()==c->physics_thread&&GetTickCount64()-c->heartbeat.load()<=250&&
           qualified_restart({c->expected_manager,c->bound.load(),c->expected_body,c->active_start},state,race_start,c->start)){
            c->controller.stop();c->bound=0;c->candidate=0;c->candidate_ticks=0;
            c->hybrid_cursor={};c->previous={};c->first=true;c->episode_idle=false;c->neutral_ack=false;
        }
        if(!c->bound&&expected_owner&&valid(state)&&c->map_valid.load()&&(!c->input_mode||input_record||!c->control)){
            float distance{};for(int k=0;k<3;++k){const float d=state.rigid[9+k]-c->start[k];distance+=d*d;}
            if(distance<2.25f&&std::uint32_t(ms-race_start)<3000){
                if(c->candidate==state.vehicle&&std::uint32_t(ms-c->candidate_ms)==10)++c->candidate_ticks;
                else if(c->candidate_ms!=ms||!c->candidate){c->candidate=state.vehicle;c->candidate_ticks=1;}
                c->candidate_ms=ms;
                // The 100 Hz model may use the first race tick only when the
                // exact manager/body is already qualified by observe mode.
                // Unqualified discovery still needs three stable macro ticks.
                const bool qualified_fast_start=c->control&&c->decision_ticks==1&&
                    c->expected_manager==state.manager&&c->expected_body==state.body&&
                    c->expected_vehicle!=0&&expected_owner;
                if(c->candidate_ticks>=3||qualified_fast_start){c->bound=state.vehicle;c->physics_thread=GetCurrentThreadId();
                    if(c->control&&!c->fixture){
                        auto accepted=prior;
                        if(!commit_qualified_candidate(accepted,state,race_start,c->reset_rebind)){c->stop=true;}
                        else{c->expected_vehicle=accepted.vehicle;c->expected_start=accepted.race_start_ms;}
                    }
                    c->active_start=race_start;++c->episodes;
                    if(c->control)c->controller.arm(state,infer,c,c->decision_ticks);
                }
            }
        }
        if(row)row->bound_owner=c->bound.load()==state.vehicle;
        if(c->control&&c->bound==state.vehicle){
            if(c->input_mode&&!input_record&&(!c->has_input||c->input_tick!=ms||c->input_vehicle!=state.vehicle))c->stop=true;
            if(c->hybrid&&c->hybrid->budget_expired(c->hybrid_cursor,ms-race_start)){
                if(c->repeat_resets)c->episode_idle=true;else c->stop=true;
            }
            const bool verifier=c->input_mode&&!input_record;
            if(verifier&&!c->consumer_thread)c->consumer_thread=GetCurrentThreadId();
            const bool stopped=c->stop.load()||c->episode_idle||(c->repeat_resets&&!state.race_running)||GetCurrentThreadId()!=(verifier?c->consumer_thread:c->physics_thread)||!c->map_valid.load()||
                GetTickCount64()-c->heartbeat.load()>250;
            const auto begin=GetTickCount64();
            auto action=verifier?(stopped?Controls{}:c->previous):c->controller.before_consume(state,stopped);
            if(verifier&&stopped){c->controller.stop();c->stop=true;}
            if(verifier&&!stopped){
                Controls consumed{};
                if(!read(state.vehicle+0x98,consumed)||!same_input_controls(consumed,action)){
                    ++c->consumer_mismatches;c->stop=true;c->controller.stop();action={};
                }else if(row)row->consumer_verified=1;
            }
            if(c->repeat_resets&&c->controller.fault()==Fault::policy_failed)c->episode_idle=true;
            if(GetTickCount64()-begin>2){c->controller.stop();action={};c->stop=true;}
            if(c->track&&!c->first){const float* p=state.rigid.data()+9;if(c->track(c->environment,p,0)){c->controller.stop();action={};c->stop=true;}}
            if(input_record){
                const auto axes=input_axes(action);SIZE_T n{};PlayerInputRecord verified{};
                const bool ok=WriteProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(input_record+4),axes.data(),12,&n)&&n==12&&
                    read(input_record,verified)&&verified.axes[0]==action.steer&&verified.axes[1]==action.gas&&verified.axes[2]==action.brake;
                if(!ok){c->stop=true;c->controller.stop();action={};}
                else{c->has_input=true;c->input_tick=ms;c->input_vehicle=state.vehicle;c->input_record=input_record;
                    if(row)row->recorded=input_controls(verified);}
            }
            // V7 commands travel only through the normal input decoder.
            // The force hook observes the result, never repairs a non-neutral
            // decoder output. Physical writes are reserved for neutral stop.
            if(!c->input_mode||c->stop.load()){
                std::memcpy(static_cast<unsigned char*>(vehicle)+0x98,&action,sizeof(action));
                if(row)row->physical_write=1;
            }
            c->previous=action;wrote=true;
            if(c->stop.load()&&action.gas==0&&action.brake==0&&action.steer==0&&
               (!c->input_mode||(input_record&&c->has_input&&c->input_tick==ms)))c->neutral_ack=true;
            if(row){row->written=action;row->wrote=1;row->fault=std::uint32_t(c->controller.fault());}
        }
    }else if(c&&c->control&&c->bound.load()==reinterpret_cast<std::uintptr_t>(vehicle)){
        // A failed state read must never leave a previous throttle held.
        c->stop=true;c->controller.stop();const Controls neutral{};SIZE_T bytes{};
        if(WriteProcessMemory(GetCurrentProcess(),static_cast<unsigned char*>(vehicle)+0x98,&neutral,sizeof(neutral),&bytes)&&bytes==sizeof(neutral))
            c->neutral_ack=true;
    }
    next();
    if(row&&wrote)read(state.vehicle+0x98,row->after);
    if(c)c->busy.clear(std::memory_order_release);
    inflight.fetch_sub(1,std::memory_order_acq_rel);
}
void callback(void* manager,void* vehicle,std::uint32_t ms,float dt)noexcept{
    dispatch(manager,vehicle,ms,dt,[&]{original(manager,vehicle,ms,dt);});
}
extern "C" __attribute__((noinline,used)) void tm2020_early_before(void* force)noexcept{
    const auto at=reinterpret_cast<std::uintptr_t>(force);
    std::uintptr_t scene{},manager{},vehicle{};std::uint32_t ms{};float dt{};
    const bool ok=read(at,scene)&&read(scene+0x110,manager)&&read(at+8,vehicle)&&
        read(at+0x14,ms)&&read(at+0x18,dt);
    if(!ok){if(auto* c=current.load())c->stop=true;return;}
    dispatch(reinterpret_cast<void*>(manager),reinterpret_cast<void*>(vehicle),ms,dt,[]{});
}
extern "C" __attribute__((noinline,used)) void tm2020_input_before(std::uintptr_t previous,std::uintptr_t next,
        std::uintptr_t descriptor,std::uint32_t ms,std::uintptr_t player,std::uintptr_t return_address)noexcept{
    inflight.fetch_add(1,std::memory_order_acq_rel);
    auto* c=current.load(std::memory_order_acquire);
    if(c&&c->input_mode&&c->control){
        const auto base=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
        std::array<std::uint64_t,2> entity{};PlayerInputRecord old{},now{};
        if((return_address==base+0x12bf828||((c->fixture||c->owned_pipeline)&&return_address==reinterpret_cast<std::uintptr_t>(&owned_input_return)))&&read(descriptor,entity)&&
           input_record_owner(player,previous,next,static_cast<std::uint32_t>(entity[0]),entity[1])&&
           read(previous,old)&&read(next,now)&&driving_record(old)&&driving_record(now)){
            PhysicsTick state;std::uint32_t start{};
            if(snapshot(reinterpret_cast<void*>(c->expected_manager),reinterpret_cast<void*>(entity[1]),ms,.010000001f,state,start)&&
               qualified_candidate({c->expected_manager,c->expected_vehicle,c->expected_body,c->expected_start},state,start,c->reset_rebind))
                dispatch(reinterpret_cast<void*>(c->expected_manager),reinterpret_cast<void*>(entity[1]),ms,.010000001f,[]{},next);
        }
    }
    inflight.fetch_sub(1,std::memory_order_acq_rel);
}
void detach(Context& c){
    c.stop=true;
    for(unsigned wait=0;c.control&&c.bound&&!c.neutral_ack.load()&&wait<500;++wait)Sleep(1);
    if(c.control&&c.bound&&!c.neutral_ack.load()){
        // A finish/menu can stop physics entirely. Only the stop path may
        // neutralize outside a consumer call, with every other thread paused
        // and the exact bound physical owner revalidated.
        const auto binding=c.controller.binding();PausedThreads paused;
        if(paused.pause()){
            PhysicsTick state;std::uint32_t start{};Controls neutral{},verified{};SIZE_T n{};
            const bool same=snapshot(reinterpret_cast<void*>(binding.manager),reinterpret_cast<void*>(binding.vehicle),binding.timestamp_ms,binding.interval,state,start)&&state.body==binding.body;
            std::uint32_t handle{};Controls prior{};
            const bool retired=read(binding.vehicle+0x10,handle)&&handle==UINT32_MAX&&read(binding.vehicle+0x98,prior)&&valid(prior);
            const bool wrote=(same||retired)&&WriteProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(binding.vehicle+0x98),&neutral,sizeof(neutral),&n)&&n==sizeof(neutral)&&read(binding.vehicle+0x98,verified)&&verified.gas==0&&verified.brake==0&&verified.steer==0;
            paused.resume();
            bool input_neutral=true;
            if(c.input_mode&&c.input_record){
                PlayerInputRecord record{};const std::array<float,3> axes{};SIZE_T bytes{};
                input_neutral=read(c.input_record,record)&&driving_record(record)&&
                    WriteProcessMemory(GetCurrentProcess(),reinterpret_cast<void*>(c.input_record+4),axes.data(),12,&bytes)&&bytes==12;
            }
            if(wrote&&input_neutral){c.previous={};c.controller.stop();c.neutral_ack=true;}
        }
    }
    require(!c.control||!c.bound||c.neutral_ack.load(),"Neutralization awaits a physics tick; stopped context and hook remain pinned");
    current=nullptr;
    for(unsigned attempt=0;attempt<100&&input_hook.installed();++attempt){if(input_hook.remove())break;Sleep(1);}
    require(!input_hook.installed(),"Input hook removal refused; runtime retained inert");
    for(unsigned attempt=0;attempt<100&&hook.installed();++attempt){if(hook.remove())break;Sleep(1);}
    require(!hook.installed(),"Hook removal refused; DLL retained inert, restart offline process before another run");
    for(unsigned attempt=0;attempt<500&&inflight.load();++attempt)Sleep(1);
    require(inflight.load()==0,"Internal callbacks have not drained; context retained");
}
void dump(const Context& c,const fs::path& path){
    std::ofstream file(path);require(bool(file),"Cannot retain internal tick evidence");file<<std::setprecision(9);
    file<<"manager,vehicle,body,tick_ms,race_start_ms,interval,r00,r01,r02,r10,r11,r12,r20,r21,r22,x,y,z,qw,qx,qy,qz,vx,vy,vz,wx,wy,wz,gear,valid_state,valid_map,bound_owner,gas_before,brake_before,steer_before,gas,brake,steer,gas_after,brake_after,steer_after,wrote,fault,input_stage,record_gas,record_brake,record_steer,physical_write,consumer_verified\n";
    for(std::size_t i=0;i<std::min<std::size_t>(c.count.load(),maximum_rows);++i){const auto& r=c.rows[i];
        file<<r.manager<<','<<r.vehicle<<','<<r.body<<','<<r.ms<<','<<r.race_start<<','<<r.dt;
        for(auto word:r.rigid)file<<','<<word;
        file<<','<<r.gear<<','<<r.valid_state<<','<<r.valid_map<<','<<r.bound_owner;
        for(auto value:{r.before.gas,r.before.brake,r.before.steer,r.written.gas,r.written.brake,r.written.steer,r.after.gas,r.after.brake,r.after.steer})file<<','<<value;
        file<<','<<r.wrote<<','<<r.fault<<','<<r.input_stage<<','<<r.recorded.gas<<','<<r.recorded.brake<<','<<r.recorded.steer<<','<<r.physical_write<<','<<r.consumer_verified<<'\n';
    }
}
std::unique_ptr<Context> retained; // Never free a context while a hook might reference it.
}
extern "C" __declspec(dllexport) DWORD WINAPI tm2020_runtime_probe(void*)noexcept{return 1;}
extern "C" __declspec(dllexport) DWORD WINAPI tm2020_internal_selftest(void*)noexcept{
    try{
        std::array<wchar_t,32768> image{};GetModuleFileNameW(nullptr,image.data(),image.size());
        require(_wcsicmp(fs::path(image.data()).filename().c_str(),L"tm2020_local_dll_loader.exe")==0,"Fixture export is restricted to the owned loader child");
        hook.use_debug_writer(true);input_hook.use_debug_writer(true); // Owned image writers.
        if(GetEnvironmentVariableW(L"TM2020_TEST_PROC_DEBUG",nullptr,0)){
            std::array<wchar_t,32768> args{};require(GetEnvironmentVariableW(L"TM2020_INTERNAL_FIXTURE_ARGS",args.data(),args.size())>0,"Missing owned fixture arguments");
            const fs::path handoff(std::wstring(args.data())+L".proc");const auto begin=GetTickCount64();
            while(!fs::exists(handoff)&&GetTickCount64()-begin<30000)Sleep(10);
            std::ifstream source(handoff);std::string memory;std::getline(source,memory);require(bool(source),"No owned process memory handoff");
            hook.use_proc_debug_writer(fs::path(memory).wstring());
            input_hook.use_proc_debug_writer(fs::path(memory).wstring());
        }
        retained=std::make_unique<Context>();auto& c=*retained;c.fixture=c.control=true;c.session_valid=c.map_valid=true;c.heartbeat=GetTickCount64();
        alignas(16) std::array<unsigned char,0x200> manager{};alignas(16) std::array<unsigned char,0x1e00> vehicle{};
        std::array<float,22> body{};body[0]=body[4]=body[8]=body[12]=1;std::array<std::uint32_t,1> ids{};
        auto states=body.data();auto map=ids.data();std::uint32_t count=1;
        std::memcpy(manager.data()+0x70,&states,8);std::memcpy(manager.data()+0x78,&count,4);std::memcpy(manager.data()+0xb0,&map,8);
        alignas(16) std::array<unsigned char,0x120> scene{};alignas(16) std::array<unsigned char,0x50> force{};
        auto manager_ptr=manager.data();auto scene_ptr=scene.data();
        std::memcpy(scene.data()+0x110,&manager_ptr,8);std::memcpy(force.data(),&scene_ptr,8);
        auto code=reinterpret_cast<unsigned char*>(&owned_early_consumer);MEMORY_BASIC_INFORMATION memory{};
        require(VirtualQuery(code,&memory,sizeof(memory))&&memory.Type==MEM_IMAGE,"Owned consumer is not in a PE image");
        hook.prepare(code,early_consumer_prologue);tm2020_early_trampoline=hook.original();current=&c;
        require(hook.install(reinterpret_cast<void*>(&early_entry)),"Fixture hook installation failed");
        auto consume=[&](void*,void* v,std::uint32_t ms,float dt){
            std::memcpy(force.data()+8,&v,8);std::memcpy(force.data()+0x14,&ms,4);std::memcpy(force.data()+0x18,&dt,4);
            reinterpret_cast<EarlyConsumer>(code)(force.data());
        };
        for(unsigned tick=0;tick<100;++tick){c.heartbeat=GetTickCount64();consume(manager.data(),vehicle.data(),tick*10,.01f);
            if(tick>=2){Controls received{};std::memcpy(&received,manager.data(),sizeof(received));require(received.gas==1&&received.brake==0&&received.steer==32.f/127.f,"Original consumer did not receive direct controls");}}
        require(owned_register_probe(force.data())==1,"Early hook clobbered a game-live R10/XMM2..5 register");
        c.stop=true;consume(manager.data(),vehicle.data(),1000,.01f);Controls neutral{};std::memcpy(&neutral,manager.data(),sizeof(neutral));
        require(neutral.gas==0&&neutral.brake==0&&neutral.steer==0,"Internal failsafe did not neutralize consumer");
        // A previously valid owner with an unreadable/invalid body lookup
        // must also receive neutral, rather than its last held throttle.
        c.stop=false;c.neutral_ack=false;PhysicsTick state;std::uint32_t start{};
        require(snapshot(manager.data(),vehicle.data(),1010,.01f,state,start),"Fixture state read failed");state.session_verified=true;
        require(c.controller.arm(state,infer,&c),"Fixture controller rearm failed");
        c.heartbeat=GetTickCount64();consume(manager.data(),vehicle.data(),1010,.01f);
        std::uint32_t empty=0;std::memcpy(manager.data()+0x78,&empty,4);consume(manager.data(),vehicle.data(),1020,.01f);
        std::memcpy(&neutral,manager.data(),sizeof(neutral));
        require(c.stop&&c.neutral_ack&&neutral.gas==0&&neutral.brake==0&&neutral.steer==0,"Failed physical read left a held command");
        detach(c);require(std::memcmp(code,early_consumer_prologue.data(),early_consumer_prologue.size())==0,"Original early entry bytes were not restored");
        // Actual PE detours on both boundaries: decode genuine input records,
        // then verify exactly the same command at the physical consumer.
        alignas(16) std::array<unsigned char,0x200> player{};PlayerInputRecord record{};record.bits=2;
        std::memcpy(player.data()+0x188,&record,sizeof(record));std::memcpy(player.data()+0x1a8,&record,sizeof(record));
        std::array<std::uint64_t,2> descriptor{0x0a020000,reinterpret_cast<std::uintptr_t>(vehicle.data())};
        std::array<std::uint64_t,5> call_args{reinterpret_cast<std::uintptr_t>(player.data()),
            reinterpret_cast<std::uintptr_t>(player.data()+0x1a8),reinterpret_cast<std::uintptr_t>(player.data()+0x188),
            reinterpret_cast<std::uintptr_t>(descriptor.data()),0};
        c.input_mode=true;c.has_input=false;c.stop=false;c.neutral_ack=false;c.bound=0;c.candidate=0;c.candidate_ticks=0;c.count=0;
        c.decision_ticks=1;c.expected_manager=reinterpret_cast<std::uintptr_t>(manager.data());
        c.expected_vehicle=reinterpret_cast<std::uintptr_t>(vehicle.data());c.expected_body=reinterpret_cast<std::uintptr_t>(body.data());
        std::memcpy(manager.data()+0x78,&count,4);
        input_hook.prepare(reinterpret_cast<void*>(&owned_input_decoder),input_decoder_prologue);tm2020_input_trampoline=input_hook.original();
        require(input_hook.install(reinterpret_cast<void*>(&input_entry)),"Owned input hook installation failed");
        require(hook.install(reinterpret_cast<void*>(&early_entry)),"Owned paired consumer hook installation failed");current=&c;
        for(unsigned tick=0;tick<100;++tick){
            c.heartbeat=GetTickCount64();call_args[4]=tick*10;
            c.fixture_action={float(tick%17!=0),float(tick%13<3),float(int(tick%31)-15)/15.f};
            const Controls expected{c.fixture_action.gas,c.fixture_action.brake,std::round(c.fixture_action.steer*127.f)/127.f};
            Controls prior_controls{};std::memcpy(&prior_controls,vehicle.data()+0x98,sizeof(prior_controls));
            require(owned_input_call(call_args.data())==1,"Input detour destroyed the incoming R11 before saving it");
            require(std::memcmp(&prior_controls,&tm2020_owned_decoder_before,sizeof(Controls))==0,"Input adapter wrote physical controls before the original decoder");
            require(read(reinterpret_cast<std::uintptr_t>(player.data()+0x188),record)&&same_input_controls(input_controls(record),expected),
                "Owned original input decoder did not receive the applied command");
            consume(manager.data(),vehicle.data(),tick*10,.01f);Controls received{};std::memcpy(&received,manager.data(),sizeof(received));
            require(same_input_controls(received,expected),"Owned recorder and physics differ");
        }
        require(c.controller.decisions()==100&&c.controller.ticks()==100,"Input and physics stages duplicated decisions");
        // Simulate a broken decoder. The verifier must stop, not overwrite
        // the mismatch with the requested throttle and call it a success.
        c.fixture_action={1,0,0};call_args[4]=1000;c.heartbeat=GetTickCount64();owned_input_call(call_args.data());
        const Controls corrupt{0,1,.5f};std::memcpy(vehicle.data()+0x98,&corrupt,sizeof(corrupt));
        consume(manager.data(),vehicle.data(),1000,.01f);
        require(c.stop&&c.consumer_mismatches==1,"Decoder mismatch was hidden by a direct physical write");
        Controls stopped_controls{};std::memcpy(&stopped_controls,vehicle.data()+0x98,sizeof(stopped_controls));
        require(same_input_controls(stopped_controls,Controls{}),"Decoder mismatch did not neutralize physics");
        call_args[4]=1010;owned_input_call(call_args.data());consume(manager.data(),vehicle.data(),1010,.01f);
        require(read(reinterpret_cast<std::uintptr_t>(player.data()+0x188),record)&&record.axes[0]==0&&record.axes[1]==0&&record.axes[2]==0,"Input failsafe left a recorded command");
        detach(c);require(!input_hook.installed()&&!hook.installed(),"Paired hooks remained installed");
        c.input_mode=false;
        std::array<wchar_t,32768> fixture_args{};
        const auto length=GetEnvironmentVariableW(L"TM2020_INTERNAL_FIXTURE_ARGS",fixture_args.data(),fixture_args.size());
        if(length){
            require(length<fixture_args.size(),"Owned pipeline argument path too long");
            dump(c,fs::path(std::wstring(fixture_args.data())+L".causal.csv"));
            std::ofstream progress(fs::path(std::wstring(fixture_args.data())+L".status"));
            auto stage=[&](const char* what){progress<<GetTickCount64()<<' '<<what<<std::endl;};stage("fixture_begin");
            std::ifstream input(fs::path(fixture_args.data()));std::string tag,perception,map_path,packs,model,trace;
            std::getline(input,tag);std::getline(input,perception);std::getline(input,map_path);std::getline(input,packs);
            require(tag=="TM2020_INTERNAL_FIXTURE_V1","Invalid owned pipeline fixture");unsigned variants{},heads{};
            while(std::getline(input,model)&&std::getline(input,trace)){
                stage("context_replace_begin");
                retained=std::make_unique<Context>();auto& full=*retained;full.control=true;full.session_valid=full.map_valid=true;
                full.input_mode=full.owned_pipeline=true;
                full.expected_manager=reinterpret_cast<std::uintptr_t>(manager.data());full.expected_vehicle=reinterpret_cast<std::uintptr_t>(vehicle.data());full.expected_body=reinterpret_cast<std::uintptr_t>(body.data());
                stage("context_ready");
                full.start={1200,34.014f,1360};for(int k=0;k<3;++k)body[9+k]=full.start[k];
                std::memcpy(manager.data()+0x78,&count,4);std::memset(vehicle.data()+0x98,0,sizeof(Controls));
                load_policy(full,model,perception,map_path,packs);
                const bool repeat_fixture=full.hybrid&&GetEnvironmentVariableW(L"TM2020_TEST_REPEAT_CYCLE",nullptr,0);
                full.repeat_resets=repeat_fixture;full.reset_rebind=repeat_fixture;
                const auto outputs=full.policy?full.policy->actor.outputs:0;
                heads|=full.hybrid?32u:(outputs==19?2u:(outputs==35?4u:(full.observation_width==72?16u:(full.decision_ticks==1?8u:1u))));
                stage("policy_loaded");
                // Warm parser/query/code pages before any hooked consumer tick.
                PhysicsTick warm;std::uint32_t zero{};
                require(snapshot(manager.data(),vehicle.data(),0,.01f,warm,zero),"Owned pipeline snapshot failed");
                Controls discard{};require(infer(&full,warm,discard),"Owned pipeline warmup failed");
                full.first=true;full.previous={};full.hybrid_cursor={};hook.prepare(code,early_consumer_prologue);tm2020_early_trampoline=hook.original();
                full.heartbeat=GetTickCount64();
                require(input_hook.install(reinterpret_cast<void*>(&input_entry)),"Owned policy input hook refused");
                require(hook.install(reinterpret_cast<void*>(&early_entry)),"Owned pipeline hook refused");current=&full;
                for(unsigned tick=0;tick<100;++tick){
                    full.heartbeat=GetTickCount64();call_args[4]=tick*10;owned_input_call(call_args.data());consume(manager.data(),vehicle.data(),tick*10,.01f);
                    if(tick>=2){Controls received{};std::memcpy(&received,manager.data(),sizeof(received));
                        require(valid(received)&&std::memcmp(&received,&full.previous,sizeof(received))==0,"Owned policy commands did not reach consumer");}
                }
                require(full.controller.decisions()==100/full.decision_ticks&&full.controller.fault()==Fault::none,"Owned full policy pipeline missed a decision or failed its time budget");
                stage("consumer_decisions_passed");
                if(repeat_fixture){
                    const std::uint32_t second_start=2000;
                    std::memcpy(vehicle.data()+0x12d8,&second_start,4);
                    full.heartbeat=GetTickCount64();consume(manager.data(),vehicle.data(),1500,.01f);
                    Controls during_countdown{};std::memcpy(&during_countdown,vehicle.data()+0x98,sizeof(during_countdown));
                    require(during_countdown.gas==0&&during_countdown.brake==0&&during_countdown.steer==0,"Repeat countdown held controls");
                    for(unsigned tick=0;tick<100;++tick){full.heartbeat=GetTickCount64();call_args[4]=second_start+tick*10;owned_input_call(call_args.data());consume(manager.data(),vehicle.data(),second_start+tick*10,.01f);}
                    require(full.episodes==2&&full.controller.decisions()==100&&full.controller.fault()==Fault::none,"Repeat attempt failed to rearm exact owner at race zero");
                    stage("repeat_reset_passed");
                    const std::uint32_t restored_start=0;
                    std::memcpy(vehicle.data()+0x12d8,&restored_start,4);
                }
                full.stop=true;consume(manager.data(),vehicle.data(),1000,.01f);detach(full);dump(full,trace);++variants;
                stage("detached_and_dumped");
            }
            require((variants==3&&heads==7)||(variants==4&&(heads==15||heads==23||heads==39))||(variants==5&&(heads==31||heads==47||heads==55))||(variants==6&&heads==63),"Owned pipeline must exercise each requested head/cadence exactly once");
            // No further physics callback: shutdown still clears the exact
            // bound command fields and restores the consumer safely.
            retained=std::make_unique<Context>();auto& paused=*retained;paused.fixture=paused.control=true;paused.session_valid=paused.map_valid=true;
            paused.start={body[9],body[10],body[11]};std::memcpy(manager.data()+0x78,&count,4);
            hook.prepare(code,early_consumer_prologue);tm2020_early_trampoline=hook.original();paused.heartbeat=GetTickCount64();current=&paused;
            require(hook.install(reinterpret_cast<void*>(&early_entry)),"Paused-stop fixture hook refused");
            for(unsigned tick=0;tick<3;++tick){paused.heartbeat=GetTickCount64();consume(manager.data(),vehicle.data(),tick*10,.01f);}
            require(paused.bound&&paused.previous.gas==1,"Paused-stop fixture did not drive");detach(paused);
            Controls cleared{};std::memcpy(&cleared,vehicle.data()+0x98,sizeof(cleared));
            require(cleared.gas==0&&cleared.brake==0&&cleared.steer==0&&!hook.installed(),"Paused physics shutdown left a command/hook active");
            stage("fixture_complete");
        }
        retained.reset();return 1;
    }catch(...){if(retained){retained->stop=true;current=nullptr;}return 0;}
}
extern "C" __declspec(dllexport) DWORD WINAPI tm2020_bot_run(void* parameter)noexcept{
    fs::path config;std::ofstream status;
    try{
        require(!hook.installed()&&inflight.load()==0,"Previous internal worker has not detached; restart the offline process");
        require(parameter,"Missing config");const auto* text=static_cast<const wchar_t*>(parameter);std::size_t length{};
        while(length<32768&&text[length])++length;require(length&&length<32768,"Invalid config path");config=fs::path(std::wstring(text,length));
        status.open(config.string()+".status");require(bool(status),"Cannot retain worker status");
        std::ifstream input(config);std::string tag,mode,trace,uid,model,perception,map,packs;double seconds{};
        std::getline(input,tag);std::getline(input,mode);input>>seconds;input.ignore(1000,'\n');
        for(auto* value:{&trace,&uid,&model,&perception,&map,&packs})std::getline(input,*value);
        retained=std::make_unique<Context>();auto& c=*retained;input>>c.start[0]>>c.start[1]>>c.start[2];
        const bool input_mode=tag=="TM2020_INTERNAL_RUNTIME_V7_LOCAL_PROC_INPUT";
        c.input_mode=input_mode;
        const bool repeat=tag=="TM2020_INTERNAL_RUNTIME_V6_LOCAL_PROC_REPEAT";
        const bool reset_rebind=tag=="TM2020_INTERNAL_RUNTIME_V5_LOCAL_PROC_RESET"||repeat||input_mode;
        const bool proc_debug=tag=="TM2020_INTERNAL_RUNTIME_V4_LOCAL_PROC_DEBUG"||reset_rebind;
        const bool debug_write=tag=="TM2020_INTERNAL_RUNTIME_V3_LOCAL_DEBUG_WRITE";
        const bool local_solo=tag=="TM2020_INTERNAL_RUNTIME_V2_LOCAL_SOLO"||debug_write||proc_debug;
        require(bool(input)&&(tag=="TM2020_INTERNAL_RUNTIME_V1"||local_solo)&&(mode=="observe"||mode=="control")&&seconds>0&&seconds<=120,"Invalid internal runtime config");
        if(mode=="control"){
            input>>c.expected_manager>>c.expected_vehicle>>c.expected_body;
            if(reset_rebind){input>>c.expected_start;c.reset_rebind=true;}
            require(bool(input)&&c.expected_manager&&c.expected_vehicle&&c.expected_body,"Control requires the exact observed manager/vehicle/body binding");
        }
        std::string proc_path;
        if(proc_debug){
            if(mode=="observe"){std::uintptr_t unused{};input>>unused>>unused>>unused;}
            input.ignore(1000,'\n');std::getline(input,proc_path);require(bool(input)&&!proc_path.empty(),"Missing explicit process memory path");
        }
        std::array<wchar_t,32768> image{};GetModuleFileNameW(nullptr,image.data(),image.size());
        require(_wcsicmp(fs::path(image.data()).filename().c_str(),L"Trackmania.exe")==0,"Actual client process required");
        require(tm2020::live::file_sha256(image.data())==tm2020::live::visual_state_build_sha256,"Unsupported client build");
        require(local_solo||offline_namespace(),"Client namespace is networked; explicit local Solo activation required");c.session_valid=true;c.control=mode=="control";
        require(!uid.empty(),"Missing expected map UID");c.map_uid=uid;
        if(c.control){
            load_policy(c,model,perception,map,packs);
            require(!repeat||bool(c.hybrid),"Repeat mode requires the qualified trajectory controller");
            c.repeat_resets=repeat;
        }
        HMODULE pinned{};require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_PIN,reinterpret_cast<LPCWSTR>(&callback),&pinned),"Cannot pin worker lifetime");
        hook.use_debug_writer(debug_write);
        if(proc_debug)hook.use_proc_debug_writer(fs::path(proc_path).wstring());
        hook.prepare(reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr))+consumer_rva,early_consumer_prologue);tm2020_early_trampoline=hook.original();
        if(input_mode){
            require(proc_debug,"Input record test requires the explicitly authorized local writer");
            input_hook.use_proc_debug_writer(fs::path(proc_path).wstring());
            input_hook.prepare(reinterpret_cast<unsigned char*>(GetModuleHandleW(nullptr))+input_decoder_rva,input_decoder_prologue);
            tm2020_input_trampoline=input_hook.original();
            require(input_hook.install(reinterpret_cast<void*>(&input_entry)),"Input decoder hook installation refused");
        }
        c.heartbeat=GetTickCount64();
        if(!hook.install(reinterpret_cast<void*>(&early_entry)))throw std::runtime_error("Consumer hook refused: "+hook.diagnostic());
        current=&c;
        status<<"INTERNAL_INSTALLED rva=0x83de60 stage=before_cached_pedals mode="<<mode<<" writer="<<(proc_debug?"explicit_proc_debug":(debug_write?"explicit_debug_write":"VirtualProtect"))<<std::endl;const auto start=GetTickCount64();auto checked=start;
        unsigned reported_episodes=0;bool reported_idle=false;
        while(GetTickCount64()-start<seconds*1000&&!c.stop.load()){
            c.heartbeat=GetTickCount64();c.map_valid=map_matches(uid);
            if(c.repeat_resets&&!c.map_valid.load())c.stop=true;
            if(c.repeat_resets){
                const auto episodes=c.episodes.load();const bool idle=c.episode_idle.load();
                if(episodes!=reported_episodes){status<<"EPISODE_BEGIN "<<episodes<<std::endl;reported_episodes=episodes;}
                if(idle&&!reported_idle)status<<"WAITING_FOR_MANUAL_RESET"<<std::endl;
                reported_idle=idle;
            }
            if(GetTickCount64()-checked>=250){c.session_valid=local_solo||offline_namespace();checked=GetTickCount64();if(!c.session_valid.load())c.stop=true;}
            if(fs::exists(config.string()+".STOP")||(GetAsyncKeyState(VK_ESCAPE)&0x8000))c.stop=true;
            Sleep(10);
        }
        c.stop=true;Sleep(30);detach(c);dump(c,trace);
        status<<"RETURNED internal_ticks="<<c.count.load()<<" decisions="<<c.controller.decisions()<<" bound="<<c.bound<<" fault="<<unsigned(c.controller.fault())<<" episodes="<<c.episodes<<std::endl;
        retained.reset();return 0;
    }catch(const std::exception& error){
        if(retained){retained->stop=true;try{detach(*retained);dump(*retained,config.string()+".failed.csv");retained.reset();}catch(...){} }
        if(status)status<<"ERROR "<<error.what()<<std::endl;return 6;
    }catch(...){if(retained)retained->stop=true;if(status)status<<"ERROR unknown"<<std::endl;return 6;}
}
