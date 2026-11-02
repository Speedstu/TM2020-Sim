// Development-only, bounded local-Solo hardware-breakpoint capture. Never
// patches executable bytes, elevates privileges or bypasses protection.
#include "tm2020/read_only_live.hpp"
#include "tm2020/recovered_rigid.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <span>
#include <stdexcept>
#include <vector>
namespace {
struct Handle {HANDLE h{};~Handle(){if(h&&h!=INVALID_HANDLE_VALUE)CloseHandle(h);}};
template<class T>bool read(HANDLE process,std::uintptr_t address,T& out){SIZE_T got{};return ReadProcessMemory(process,reinterpret_cast<void*>(address),&out,sizeof(out),&got)&&got==sizeof(out);}
struct DebugCapture {
    DWORD pid{};bool attached{},restored{},detached{};unsigned restore_failures{};std::map<DWORD,CONTEXT> original;
    ~DebugCapture(){const bool needed=attached;detach();if(needed)std::cerr<<"DEBUG_CLEANUP detached="<<detached<<" restore_failures="<<restore_failures<<'\n';}
    void detach()noexcept{
        if(!attached)return;
        // Context access outside a stopped debug event requires suspending
        // each surviving thread. Restore all four original debug addresses.
        if(!restored)for(const auto& [tid,saved]:original){
            Handle thread{OpenThread(THREAD_SUSPEND_RESUME|THREAD_GET_CONTEXT|THREAD_SET_CONTEXT,FALSE,tid)};
            if(!thread.h){if(GetLastError()!=ERROR_INVALID_PARAMETER)++restore_failures;continue;}
            if(SuspendThread(thread.h)==DWORD(-1)){++restore_failures;continue;}
            CONTEXT c{};c.ContextFlags=CONTEXT_DEBUG_REGISTERS;
            if(GetThreadContext(thread.h,&c)){c.Dr0=saved.Dr0;c.Dr1=saved.Dr1;c.Dr2=saved.Dr2;c.Dr3=saved.Dr3;c.Dr6=saved.Dr6;c.Dr7=saved.Dr7;if(!SetThreadContext(thread.h,&c))++restore_failures;}else ++restore_failures;
            ResumeThread(thread.h);
        }
        detached=DebugActiveProcessStop(pid)!=0;if(detached)attached=false;
    }
    void restore_while_stopped(){
        for(const auto& [tid,saved]:original){
            Handle thread{OpenThread(THREAD_GET_CONTEXT|THREAD_SET_CONTEXT,FALSE,tid)};
            if(!thread.h)throw std::runtime_error("Cannot restore stopped debug thread");
            CONTEXT c{};c.ContextFlags=CONTEXT_DEBUG_REGISTERS;
            if(!GetThreadContext(thread.h,&c))throw std::runtime_error("Cannot read restoration context");
            c.Dr0=saved.Dr0;c.Dr1=saved.Dr1;c.Dr2=saved.Dr2;c.Dr3=saved.Dr3;c.Dr6=saved.Dr6;c.Dr7=saved.Dr7;
            if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot restore original debug registers");
        }restored=true;
    }
    void arm(DWORD tid,std::uintptr_t entry){
        if(original.contains(tid))return;
        Handle thread{OpenThread(THREAD_GET_CONTEXT|THREAD_SET_CONTEXT,FALSE,tid)};
        if(!thread.h)throw std::runtime_error("Cannot open stopped debug thread");
        CONTEXT c{};c.ContextFlags=CONTEXT_DEBUG_REGISTERS;
        if(!GetThreadContext(thread.h,&c))throw std::runtime_error("Cannot read stopped debug context");
        if(c.Dr7&0xff)throw std::runtime_error("Existing hardware breakpoints: capture refuses to overwrite them");
        original.emplace(tid,c);c.Dr0=entry;c.Dr1=0;c.Dr6=0;c.Dr7=(c.Dr7&~DWORD64(0xffff000f))|1;
        if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot arm local execution breakpoint");
    }
};
struct Pending {std::uintptr_t forces{},callback_arg0{},context{},manager{},vehicle{},dyna{},states{},configuration{};std::uint32_t item{},index{},raw_clock{};float dt{};std::array<float,6> forces_before{};std::array<float,22> rigid_before{};};
struct FixtureContext {void* manager;void* vehicle;std::uint32_t item,clock;};
#if defined(__GNUC__)
__attribute__((noinline,noclone,noipa))
#else
__declspec(noinline)
#endif
void fixture_tick(float* forces,float interval,FixtureContext* context){
    forces[0]+=interval;forces[1]+=1;context->clock+=10;
}
int owned_fixture(const std::string& ready_name){
    std::array<std::byte,0x200> manager{},dyna{},vehicle{};std::array<float,22> state{};std::array<float,6> forces{};std::uint32_t index{};
    std::array<std::byte,64> configuration{};
    const auto pointer=[](auto& bytes,std::size_t offset,void* value){std::memcpy(bytes.data()+offset,&value,8);};
    pointer(manager,0x110,dyna.data());pointer(dyna,0x70,state.data());pointer(dyna,0xa0,forces.data());pointer(dyna,0xb0,&index);pointer(vehicle,0x88,configuration.data());
    FixtureContext context{manager.data(),vehicle.data(),0,0};
    Handle ready{OpenEventA(EVENT_MODIFY_STATE,FALSE,ready_name.c_str())};if(!ready.h||!SetEvent(ready.h))return 2;Sleep(200);
    for(unsigned n=0;n<100;n++){fixture_tick(forces.data(),.01f,&context);Sleep(1);}return 0;
}
struct SceneFixture {std::uint64_t marker=0x5343454e45414249ull;std::uint32_t calls{};};
#if defined(__GNUC__)
__attribute__((noinline,noclone,noipa))
#else
__declspec(noinline)
#endif
void scene_fixture_tick(SceneFixture* scene,std::uint32_t clock,std::uint32_t interval,
                        std::uint32_t mode,const std::uint32_t* input,std::uint8_t flags){
    LARGE_INTEGER a{},b{};QueryPerformanceCounter(&a);QueryPerformanceCounter(&b);
    if(clock==12340&&interval==10&&mode==1&&input&&input[2]==7&&flags==0xfe)++scene->calls;
}
int owned_scene_fixture(const std::string& event){
    SceneFixture scene;const std::array<std::uint32_t,3> input{0,0,7};
    Handle ready{OpenEventA(EVENT_MODIFY_STATE,FALSE,event.c_str())};
    if(!ready.h||!SetEvent(ready.h))return 2;Sleep(200);
    for(unsigned i=0;i<100;++i){scene_fixture_tick(&scene,12340,10,1,input.data(),0xfe);Sleep(1);}
    return scene.calls==100?0:3;
}
std::string address(std::uint64_t value){std::ostringstream out;out<<"0x"<<std::hex<<value;return out.str();}
std::uint64_t process_created(HANDLE p){FILETIME a{},b{},c{},d{};
    if(!GetProcessTimes(p,&a,&b,&c,&d))throw std::runtime_error("Cannot read process creation identity");
    return (std::uint64_t(a.dwHighDateTime)<<32)|a.dwLowDateTime;
}
int capture_scene_entry(int argc,char** argv){
    const bool owned_hold=argc>=2&&std::string(argv[1])=="--selftest-scene-entry-hold";
    const bool owned=(owned_hold&&(argc==4||argc==5))||(argc==3&&(std::string(argv[1])=="--selftest-scene-entry"||std::string(argv[1])=="--selftest-scene-entry-abort"));
    const bool abort=owned&&std::string(argv[1])=="--selftest-scene-entry-abort";
    if(!owned&&((argc<4||argc>6)||std::string(argv[1])!="--confirm-local-solo-scene"))
        throw std::invalid_argument("Usage: --confirm-local-solo-scene target.txt output-prefix [release-event] | --selftest-scene-entry[-abort] prefix");
#ifndef TM2020_ENABLE_EXPERIMENTAL_GAME_DEBUG_CAPTURE
    if(!owned)throw std::runtime_error("Live scene debugger disabled; explicit research build required");
#endif
    DWORD pid{};std::uint64_t created{},expected_base{},expected_scene{},registry{},manager{},collision{},vehicle_context{};
    std::array<std::uint32_t,3> slots{};std::string pinned;
    Handle child_process,child_thread;
    const std::string prefix=owned?argv[2]:argv[3];
    const bool hold=owned_hold||(!owned&&argc>=5);
    const unsigned oracle_ticks=!owned&&argc==6?std::stoul(argv[5]):1;
    if(oracle_ticks<1||oracle_ticks>100)throw std::runtime_error("Source physical oracle is bounded to 1..100 ticks");
    const auto hold_ms=owned_hold&&argc==5?std::stoul(argv[4]):60000ul;
    if(hold_ms<50||hold_ms>60000)throw std::runtime_error("Snapshot lease duration bound is 50..60000 ms");
    Handle release;
    if(hold){release.h=OpenEventA(SYNCHRONIZE,FALSE,argv[owned_hold?3:4]);if(!release.h)throw std::runtime_error("Cannot open snapshot release event");}
    if(!owned&&(std::filesystem::exists(prefix+".json")||std::filesystem::exists(prefix+".stage.json")))
        throw std::runtime_error("Scene entry capture never overwrites evidence");
    if(owned){
        wchar_t self[32768]{};if(!GetModuleFileNameW(nullptr,self,32768))throw std::runtime_error("Cannot resolve owned target");
        const auto event=L"Local\\TM2020-Scene-Entry-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64());
        Handle ready{CreateEventW(nullptr,TRUE,FALSE,event.c_str())};
        std::wstring command=L"\""+std::wstring(self)+L"\" --owned-scene-target "+event;
        STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION child{};
        if(!ready.h||!CreateProcessW(self,command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child))
            throw std::runtime_error("Cannot start owned scene fixture");
        child_process.h=child.hProcess;child_thread.h=child.hThread;pid=child.dwProcessId;
        if(WaitForSingleObject(ready.h,5000)!=WAIT_OBJECT_0)throw std::runtime_error("Owned scene readiness timed out");
    }else{
        std::ifstream in(argv[2]);std::string line;
        auto get=[&](){if(!std::getline(in,line))throw std::runtime_error("Truncated scene target");return line;};
        if(get()!="TM2020_SCENE_STAGE_TARGET_V1")throw std::runtime_error("Wrong scene target format");
        pid=std::stoul(get());created=std::stoull(get());pinned=get();expected_base=std::stoull(get(),nullptr,0);
        expected_scene=std::stoull(get(),nullptr,0);registry=std::stoull(get(),nullptr,0);
        manager=std::stoull(get(),nullptr,0);collision=std::stoull(get(),nullptr,0);vehicle_context=std::stoull(get(),nullptr,0);
        for(auto& slot:slots){slot=std::stoul(get());if(slot>=4096)throw std::runtime_error("Scene slot bound exceeded");}
        if(pinned!=tm2020::recovered::executable_sha256||expected_scene<0x10000||registry<0x10000)
            throw std::runtime_error("Scene target is not a pinned source identity");
    }
    Handle process{OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,FALSE,pid)};
    if(!process.h)throw std::runtime_error("Cannot open read-only scene source");
    if(owned)created=process_created(process.h);
    if(process_created(process.h)!=created)throw std::runtime_error("Stale scene source process");
    if(!owned){
        std::array<wchar_t,32768> file{};DWORD n=DWORD(file.size());
        if(!QueryFullProcessImageNameW(process.h,0,file.data(),&n)||
           tm2020::live::file_sha256(std::filesystem::path(std::wstring(file.data(),n)))!=pinned)
            throw std::runtime_error("Scene source executable differs");
    }
    Handle modules{CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid)};
    MODULEENTRY32W module{};module.dwSize=sizeof(module);
    if(!Module32FirstW(modules.h,&module))throw std::runtime_error("Cannot identify source module");
    const auto base=reinterpret_cast<std::uint64_t>(module.modBaseAddr);
    if(!owned&&base!=expected_base)throw std::runtime_error("Scene module base changed");
    const auto qpc=reinterpret_cast<std::uint64_t>(&QueryPerformanceCounter);
    // System DLL mappings are shared only after checking the remote image and
    // export bytes. Never infer an arbitrary external address from its name.
    MODULEENTRY32W system_module{};system_module.dwSize=sizeof(system_module);
    bool qpc_module_found=false;
    if(Module32FirstW(modules.h,&system_module))do{
        const auto start=reinterpret_cast<std::uint64_t>(system_module.modBaseAddr);
        if(start<=qpc&&qpc<start+system_module.modBaseSize){
            std::array<unsigned char,16> remote{},local{};
            std::memcpy(local.data(),reinterpret_cast<void*>(qpc),local.size());
            if(_wcsicmp(system_module.szModule,L"kernel32.dll")||!read(process.h,qpc,remote)||remote!=local)
                throw std::runtime_error("Source QueryPerformanceCounter export cohort differs");
            qpc_module_found=true;break;
        }
    }while(Module32NextW(modules.h,&system_module));
    if(!qpc_module_found)throw std::runtime_error("Source QueryPerformanceCounter module not found");
    const auto entry=owned?base+reinterpret_cast<std::uint64_t>(&scene_fixture_tick)-reinterpret_cast<std::uint64_t>(GetModuleHandleW(nullptr))
                           :base+0x12e9ea0;
    std::uint32_t module_tls_index=0xffffffffu;std::uint64_t module_tls_bytes{};
    IMAGE_DOS_HEADER dos{};IMAGE_NT_HEADERS64 nt{};IMAGE_TLS_DIRECTORY64 tls_directory{};
    if(read(process.h,base,dos)&&dos.e_magic==IMAGE_DOS_SIGNATURE&&
       read(process.h,base+dos.e_lfanew,nt)&&nt.Signature==IMAGE_NT_SIGNATURE&&
       nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS].VirtualAddress&&
       read(process.h,base+nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_TLS].VirtualAddress,tls_directory)){
        read(process.h,tls_directory.AddressOfIndex,module_tls_index);
        module_tls_bytes=tls_directory.EndAddressOfRawData-tls_directory.StartAddressOfRawData+tls_directory.SizeOfZeroFill;
    }
    if(!owned&&(module_tls_index!=0||module_tls_bytes!=0x11d8))throw std::runtime_error("Pinned game's static TLS layout differs");
    constexpr std::array<unsigned char,16> original_prefix{0x48,0x8b,0xc4,0x48,0x89,0x58,0x18,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56};
    auto validate=[&](){
        if(process_created(process.h)!=created)throw std::runtime_error("Source identity changed");
        if(owned)return;
        std::array<unsigned char,16> raw{};std::uint64_t linked{};
        if(!read(process.h,entry,raw)||raw!=original_prefix||!read(process.h,expected_scene+0x7c8,linked)||linked!=registry)
            throw std::runtime_error("Original scene code/context differs");
        const std::array<std::uint64_t,3> expected{manager,collision,vehicle_context};
        for(unsigned i=0;i<slots.size();++i)
            if(!read(process.h,registry+0x10+slots[i]*8,linked)||linked!=expected[i])throw std::runtime_error("Scene services changed");
    };
    validate();BOOL existing{};
    if(!CheckRemoteDebuggerPresent(process.h,&existing)||existing)throw std::runtime_error("Existing debugger or debugger identity unavailable");
    DebugCapture debug;debug.pid=pid;
    if(!DebugActiveProcess(pid))throw std::runtime_error("Scene debug attach denied; Win32="+std::to_string(GetLastError()));
    debug.attached=true;if(!DebugSetProcessKillOnExit(FALSE))throw std::runtime_error("Cannot disable debugger kill-on-exit");
    bool initial=true,hit=false,returned=false,deliberate_abort=false,hold_timed_out=false;std::string frame;
    DWORD hit_thread{};std::uint64_t hit_return{};
    struct CounterCall {std::uint64_t caller{},wrapper_caller{},output{},value{};std::uint32_t result{};};
    std::vector<CounterCall> counters;bool counter_pending=false;
    bool scene_pending=false;std::uint32_t first_clock{},pending_clock{};
    struct PhysicalTick {std::uint32_t clock;std::array<std::uint32_t,22> before,after;
        std::array<std::uint32_t,6> force_before,force_after;};
    std::vector<PhysicalTick> physical_ticks;
    LARGE_INTEGER exploration_counter{};
    std::array<std::uint32_t,22> rigid_before{},rigid_after{};
    std::array<std::uint32_t,6> forces_before{},forces_after{};
    auto physical=[&](auto& rigid,auto& force){
        std::uint64_t state{},accumulator{};std::uint32_t count{};
        if(!read(process.h,manager+0x78,count)||count!=1||!read(process.h,manager+0x70,state)
           ||!read(process.h,manager+0xa0,accumulator)||!read(process.h,state,rigid)||!read(process.h,accumulator,force))
            throw std::runtime_error("Stage oracle requires the discovered single-body scene");
    };
    auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(8);
    while(!returned&&std::chrono::steady_clock::now()<deadline){
        DEBUG_EVENT event{};if(!WaitForDebugEvent(&event,100)){
            if(GetLastError()==ERROR_SEM_TIMEOUT)continue;throw std::runtime_error("Scene debug wait failed");}
        DWORD continuation=DBG_CONTINUE;
        try{
            if(event.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT){if(event.u.CreateProcessInfo.hFile)CloseHandle(event.u.CreateProcessInfo.hFile);debug.arm(event.dwThreadId,entry);}
            else if(event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT)debug.arm(event.dwThreadId,entry);
            else if(event.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT){if(event.u.LoadDll.hFile)CloseHandle(event.u.LoadDll.hFile);}
            else if(event.dwDebugEventCode==EXIT_THREAD_DEBUG_EVENT)debug.original.erase(event.dwThreadId);
            else if(event.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT)throw std::runtime_error("Scene source exited during capture");
            else if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT){
                const auto code=event.u.Exception.ExceptionRecord.ExceptionCode;
                if(code==EXCEPTION_BREAKPOINT&&initial)initial=false;
                else if(code==EXCEPTION_SINGLE_STEP){
                    Handle thread{OpenThread(THREAD_GET_CONTEXT|THREAD_SET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,event.dwThreadId)};
                    CONTEXT c{};c.ContextFlags=CONTEXT_ALL;
                    if(!thread.h||!GetThreadContext(thread.h,&c))throw std::runtime_error("Cannot read stopped scene context");
                    if((c.Dr6&1)&&c.Rip==entry){
                        if(owned||c.Rcx==expected_scene){
                            if(scene_pending)throw std::runtime_error("Reentrant target scene cannot be captured as a single tick");
                            validate();std::uint64_t return_site{},input{};std::uint8_t flags{};std::uint32_t kind{};
                            if(!read(process.h,c.Rsp,return_site)||!read(process.h,c.Rsp+0x28,input)||!read(process.h,c.Rsp+0x30,flags)
                               ||(input&&!read(process.h,input+8,kind)))throw std::runtime_error("Scene stack arguments unreadable");
                            if(c.R8!=10||c.R9>1)throw std::runtime_error("Scene interval/mode is outside statically identified call sites");
                            if(hit&&(event.dwThreadId!=hit_thread||std::uint32_t(c.Rdx)!=first_clock+physical_ticks.size()*10
                                     ||c.R9!=0||input||flags!=0xfe))
                                throw std::runtime_error("Live source continuation is not a consecutive mode-zero physical tick");
                            pending_clock=std::uint32_t(c.Rdx);if(!hit)first_clock=pending_clock;
                            if(owned&&(c.Rdx!=12340||c.R9!=1||kind!=7||flags!=0xfe))throw std::runtime_error("Owned scene ABI mismatch");
                            using Query=LONG(NTAPI*)(HANDLE,ULONG,PVOID,ULONG,PULONG);
                            auto query=reinterpret_cast<Query>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQueryInformationThread"));
                            std::array<std::uint64_t,6> info{};std::uint64_t teb{},tls_array{},tls_context{},thread_object{};
                            std::array<std::uint64_t,4> arena{};std::uint8_t initialized{};std::uint32_t thread_word{};
                            const bool tls=query&&query(thread.h,0,info.data(),sizeof(info),nullptr)>=0
                                &&info[2]==pid&&info[3]==event.dwThreadId&&(teb=info[1])
                                &&read(process.h,teb+0x58,tls_array)&&read(process.h,tls_array,tls_context)
                                &&read(process.h,tls_context+0x10,initialized)&&read(process.h,tls_context+0x14,thread_word)
                                &&read(process.h,tls_context+0x148,thread_object)&&read(process.h,tls_context+0x160,arena);
                            if(!owned&&!tls)throw std::runtime_error("Original scene TLS context unreadable");
                            if(!owned)physical(rigid_before,forces_before);
                            if(!QueryPerformanceCounter(&exploration_counter))throw std::runtime_error("Cannot read exploratory host counter");
                            std::ostringstream out;out<<"\"entryRva\":"<<std::quoted(address(entry-base))<<",\"threadId\":"<<event.dwThreadId
                                <<",\"queryPerformanceCounterAddress\":"<<std::quoted(address(qpc))
                                <<",\"explorationCounterSeed\":"<<std::quoted(std::to_string(exploration_counter.QuadPart))
                                <<",\"scene\":"<<std::quoted(address(c.Rcx))<<",\"clockWord\":"<<std::uint32_t(c.Rdx)
                                <<",\"intervalWord\":"<<std::uint32_t(c.R8)<<",\"modeWord\":"<<std::uint32_t(c.R9)
                                <<",\"fifthArgument\":"<<std::quoted(address(input))<<",\"fifthArgumentKind\":"<<kind
                                <<",\"sixthArgumentByte\":"<<unsigned(flags)<<",\"returnAddress\":"<<std::quoted(address(return_site))
                                <<",\"stackPointer\":"<<std::quoted(address(c.Rsp))<<",\"mxcsr\":"<<c.MxCsr<<",\"rflags\":"<<c.EFlags
                                <<",\"moduleTlsIndex\":"<<module_tls_index<<",\"moduleTlsBytes\":"<<module_tls_bytes
                                <<",\"gameTlsLayoutQualified\":"<<(!owned?"true":"false")
                                <<",\"tlsCaptured\":"<<(tls?"true":"false")<<",\"teb\":"<<std::quoted(address(teb))
                                <<",\"tlsArray\":"<<std::quoted(address(tls_array))<<",\"tlsContext\":"<<std::quoted(address(tls_context))
                                <<",\"tlsInitializedByte\":"<<unsigned(initialized)<<",\"tlsWord14\":"<<thread_word
                                <<",\"tlsThreadObject\":"<<std::quoted(address(thread_object))<<",\"tlsArenaWords\":[";
                            for(unsigned i=0;i<arena.size();++i){if(i)out<<',';out<<std::quoted(address(arena[i]));}out<<"],\"registers\":{";
                            const std::pair<const char*,std::uint64_t> regs[]={{"rax",c.Rax},{"rbx",c.Rbx},{"rcx",c.Rcx},{"rdx",c.Rdx},
                                {"rsi",c.Rsi},{"rdi",c.Rdi},{"rbp",c.Rbp},{"rsp",c.Rsp},{"r8",c.R8},{"r9",c.R9},{"r10",c.R10},{"r11",c.R11},
                                {"r12",c.R12},{"r13",c.R13},{"r14",c.R14},{"r15",c.R15}};
                            for(unsigned i=0;i<std::size(regs);++i){if(i)out<<',';out<<std::quoted(regs[i].first)<<':'<<std::quoted(address(regs[i].second));}
                            out<<"},\"xmmWords\":[";
                            for(unsigned i=0;i<16;++i){if(i)out<<',';std::array<std::uint32_t,4> words{};std::memcpy(words.data(),&c.FltSave.XmmRegisters[i],16);
                                out<<'[';for(unsigned j=0;j<4;++j){if(j)out<<',';out<<words[j];}out<<']';}out<<']';
                            const bool first_hit=!hit;if(first_hit)frame=out.str();hit=true;scene_pending=true;
                            if(abort){deliberate_abort=true;throw std::runtime_error("Deliberate owned scene abort while stopped");}
                            if(hold&&first_hit){
                                std::ofstream stage(prefix+".stage.json");
                                stage<<"{\"schema\":\"tm2020_stopped_scene_snapshot_lease_v1\",\"pid\":"<<pid
                                     <<",\"processCreationFiletime\":"<<std::quoted(std::to_string(created))
                                     <<",\"moduleBase\":"<<std::quoted(address(base))
                                     <<",\"executableSha256\":"<<std::quoted(pinned)
                                     <<",\"leaseExpiresGetTickCount64\":"<<GetTickCount64()+hold_ms
                                     <<",\"targetThreadsStopped\":true,\"gameThreadsStopped\":"<<(!owned?"true":"false")<<','<<frame<<"}\n";
                                stage.flush();if(!stage)throw std::runtime_error("Cannot publish stopped snapshot lease");stage.close();
                                const auto wait=WaitForSingleObject(release.h,DWORD(hold_ms));
                                hold_timed_out=wait==WAIT_TIMEOUT;
                                if(wait!=WAIT_OBJECT_0&&wait!=WAIT_TIMEOUT)throw std::runtime_error("Snapshot release wait failed");
                                deadline=std::chrono::steady_clock::now()+std::chrono::seconds(8);
                            }
                            hit_thread=event.dwThreadId;hit_return=return_site;
                            // The stack return address is the second execution breakpoint.
                            c.Dr1=hit_return;c.Dr7=(c.Dr7&~DWORD64(0xf00000))|4;
                            c.Dr2=qpc;c.Dr3=0;c.Dr7=(c.Dr7&~DWORD64(0xff0000f0))|0x10;
                        }
                        c.Dr6=0;c.EFlags|=0x10000;if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot resume scene entry");
                    }else if((c.Dr6&2)&&hit&&event.dwThreadId==hit_thread&&c.Rip==hit_return){
                        if(counter_pending)throw std::runtime_error("Scene returned with pending platform observation");
                        if(!owned){physical(rigid_after,forces_after);
                            physical_ticks.push_back({pending_clock,rigid_before,rigid_after,forces_before,forces_after});}
                        scene_pending=false;
                        if(owned||physical_ticks.size()==oracle_ticks){debug.restore_while_stopped();returned=true;}
                        else{c.Dr1=c.Dr2=c.Dr3=0;c.Dr7&=~DWORD64(0xfc);c.Dr6=0;c.EFlags|=0x10000;
                            if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot resume intermediate scene return");}
                    }else if((c.Dr6&4)&&hit&&event.dwThreadId==hit_thread&&c.Rip==qpc){
                        if(counter_pending||counters.size()>=512)throw std::runtime_error("Nested/excessive platform counter calls");
                        CounterCall call{};call.output=c.Rcx;
                        if(!call.output||!read(process.h,c.Rsp,call.caller))throw std::runtime_error("Counter call ABI unreadable");
                        if(!owned&&!read(process.h,c.Rsp+0x30,call.wrapper_caller))throw std::runtime_error("Game clock wrapper caller unreadable");
                        counters.push_back(call);counter_pending=true;
                        c.Dr3=call.caller;c.Dr7=(c.Dr7&~DWORD64(0xf0000000))|0x40;
                        c.Dr6=0;c.EFlags|=0x10000;
                        if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot resume platform entry");
                    }else if((c.Dr6&8)&&hit&&counter_pending&&event.dwThreadId==hit_thread&&c.Rip==counters.back().caller){
                        auto& call=counters.back();call.result=std::uint32_t(c.Rax);
                        if(!read(process.h,call.output,call.value))throw std::runtime_error("Counter result unreadable");
                        counter_pending=false;c.Dr3=0;c.Dr7&=~DWORD64(0x40);c.Dr6=0;c.EFlags|=0x10000;
                        if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot resume platform return");
                    }else continuation=DBG_EXCEPTION_NOT_HANDLED;
                }else continuation=DBG_EXCEPTION_NOT_HANDLED;
            }
        }catch(...){try{debug.restore_while_stopped();}catch(...){++debug.restore_failures;}
            const bool continued=ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation)!=0;debug.detach();
            std::cerr<<"SCENE_ABORT_CLEANUP continued="<<continued<<" detached="<<debug.detached
                     <<" restore_failures="<<debug.restore_failures<<'\n';
            if(deliberate_abort)break;throw;}
        if(!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation))throw std::runtime_error("Cannot continue scene source");
    }
    debug.detach();if(!debug.detached||debug.restore_failures)throw std::runtime_error("Scene debugger cleanup failed");
    if(!hit||(!returned&&!deliberate_abort))throw std::runtime_error("Target scene entry/return not reached within eight seconds");
    if(owned){if(WaitForSingleObject(child_process.h,5000)!=WAIT_OBJECT_0)throw std::runtime_error("Owned scene did not exit after detach");
        DWORD code{};if(!GetExitCodeProcess(child_process.h,&code)||code)throw std::runtime_error("Owned scene did not continue normally");}
    std::ofstream out(prefix+".json");out<<"{\"schema\":\"tm2020_stopped_scene_entry_v1\",\"pid\":"<<pid
        <<",\"processCreationFiletime\":"<<std::quoted(std::to_string(created))<<",\"moduleBase\":"<<std::quoted(address(base))
        <<",\"ownedFixture\":"<<(owned?"true":"false")<<",\"registersObservedInStoppedDebugEvent\":true"
        <<",\"executableBytesPatched\":false,\"explicitProcessMemoryWrites\":false,\"osDebugStateTemporarilyChanged\":true,\"deliberateOwnedAbort\":"<<(deliberate_abort?"true":"false")
        <<",\"threadDebugRegistersTemporarilyChanged\":true"
        <<",\"detached\":true,\"restoreFailures\":0,\"wholeWorldSnapshotCaptured\":false,\"completeSimulatorQualified\":false"
        <<",\"sceneReturned\":"<<(returned?"true":"false")<<",\"snapshotLeaseRequested\":"<<(hold?"true":"false")
        <<",\"snapshotLeaseTimedOut\":"<<(hold_timed_out?"true":"false")
        <<",\"singleBodyPhysicalOracleCaptured\":"<<(!owned&&returned?"true":"false");
    out<<",\"queryPerformanceCounterTranscript\":[";
    for(std::size_t i=0;i<counters.size();++i){if(i)out<<',';const auto& call=counters[i];
        out<<"{\"returnAddress\":"<<std::quoted(address(call.caller))<<",\"clockWrapperReturnAddress\":"<<std::quoted(address(call.wrapper_caller))
           <<",\"outputAddress\":"<<std::quoted(address(call.output))
           <<",\"counterValue\":"<<std::quoted(std::to_string(call.value))<<",\"resultWord\":"<<call.result<<'}';}
    out<<']';
    out<<",\"physicalTicks\":[";
    for(std::size_t i=0;i<physical_ticks.size();++i){if(i)out<<',';const auto& tick=physical_ticks[i];
        out<<"{\"clockWord\":"<<tick.clock;
        for(const auto& pair:{std::pair{"rigidBeforeWords",std::span<const std::uint32_t>(tick.before)},
                              std::pair{"rigidAfterWords",std::span<const std::uint32_t>(tick.after)},
                              std::pair{"forcesBeforeWords",std::span<const std::uint32_t>(tick.force_before)},
                              std::pair{"forcesAfterWords",std::span<const std::uint32_t>(tick.force_after)}}){
            out<<','<<std::quoted(pair.first)<<":[";for(std::size_t j=0;j<pair.second.size();++j){if(j)out<<',';out<<pair.second[j];}out<<']';}
        out<<'}';}out<<']';
    if(!owned&&returned){
        for(const auto& pair:{std::pair{"rigidBeforeWords",std::span<const std::uint32_t>(rigid_before)},
                              std::pair{"rigidAfterWords",std::span<const std::uint32_t>(rigid_after)},
                              std::pair{"forcesBeforeWords",std::span<const std::uint32_t>(forces_before)},
                              std::pair{"forcesAfterWords",std::span<const std::uint32_t>(forces_after)}}){
            out<<','<<std::quoted(pair.first)<<":[";for(std::size_t i=0;i<pair.second.size();++i){if(i)out<<',';out<<pair.second[i];}out<<']';}
    }
    out<<','<<frame<<"}\n";
    out.flush();if(!out)throw std::runtime_error("Cannot write scene-entry evidence");
    std::cout<<"PASS STOPPED_SCENE_ENTRY owned="<<owned<<" observed_abi=true clean_detach=true deliberate_abort="<<deliberate_abort<<"\n";
    return 0;
}
}
int main(int argc,char** argv)try{
    if(argc==3&&std::string(argv[1])=="--owned-scene-target")return owned_scene_fixture(argv[2]);
    if(argc>=2&&(std::string(argv[1])=="--selftest-scene-entry"||std::string(argv[1])=="--selftest-scene-entry-abort"||
                 std::string(argv[1])=="--selftest-scene-entry-hold"||std::string(argv[1])=="--confirm-local-solo-scene"))return capture_scene_entry(argc,argv);
    if(argc==3&&std::string(argv[1])=="--owned-target")return owned_fixture(argv[2]);
    const bool abort_fixture=argc==3&&std::string(argv[1])=="--selftest-owned-abort";
    const bool owned=abort_fixture||(argc==3&&std::string(argv[1])=="--selftest-owned");
    if(!owned&&(argc!=5||std::string(argv[1])!="--confirm-local-solo"))throw std::invalid_argument("Usage: physics_debug_capture --confirm-local-solo manifest output-prefix max-pairs | --selftest-owned output-prefix");
#ifndef TM2020_ENABLE_EXPERIMENTAL_GAME_DEBUG_CAPTURE
    if(!owned)throw std::runtime_error("Unqualified live debugger capture disabled in this build; owned-process fixtures remain available");
#endif
    std::unique_ptr<tm2020::live::ReadOnlyObserver> identity;DWORD pid{};PROCESS_INFORMATION child{};Handle child_process,child_thread;
    if(owned){
        wchar_t self[32768]{};if(!GetModuleFileNameW(nullptr,self,32768))throw std::runtime_error("Cannot locate owned fixture executable");
        const auto ready_name=L"Local\\TM2020-Physics-Owned-"+std::to_wstring(GetCurrentProcessId())+L"-"+std::to_wstring(GetTickCount64());
        Handle ready{CreateEventW(nullptr,TRUE,FALSE,ready_name.c_str())};if(!ready.h)throw std::runtime_error("Cannot create fixture readiness event");
        std::wstring command=L"\""+std::wstring(self)+L"\" --owned-target "+ready_name;STARTUPINFOW startup{};startup.cb=sizeof(startup);
        if(!CreateProcessW(self,command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child))throw std::runtime_error("Cannot launch owned debugger fixture");
        child_process.h=child.hProcess;child_thread.h=child.hThread;pid=child.dwProcessId;
        if(WaitForSingleObject(ready.h,5000)!=WAIT_OBJECT_0)throw std::runtime_error("Owned fixture readiness handshake timed out");
    }else{identity=std::make_unique<tm2020::live::ReadOnlyObserver>(argv[2]);pid=identity->process_id();}
    const auto pairs=owned?20:std::stoul(argv[4]);if(pairs<1||pairs>100)throw std::invalid_argument("Capture limit must be 1..100 pairs");
    const std::string prefix=owned?argv[2]:argv[3];
    Handle process{OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION,FALSE,pid)};
    if(!process.h)throw std::runtime_error("Cannot open target read-only");
    Handle modules;MODULEENTRY32W module{};module.dwSize=sizeof(module);bool found{};
    for(unsigned retry=0;retry<50;retry++){
        modules.h=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid);
        if(modules.h!=INVALID_HANDLE_VALUE&&Module32FirstW(modules.h,&module)){found=true;break;}
        if(modules.h!=INVALID_HANDLE_VALUE)CloseHandle(modules.h);modules.h=nullptr;Sleep(10);
    }
    if(!found)throw std::runtime_error("Cannot resolve target module base");
    if(!owned&&_wcsicmp(module.szModule,L"Trackmania.exe")!=0)throw std::runtime_error("Main-module identity did not resolve to Trackmania.exe");
    const auto base=reinterpret_cast<std::uintptr_t>(module.modBaseAddr);
    const auto offset=owned?reinterpret_cast<std::uintptr_t>(&fixture_tick)-reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr)):0x851f00;
    const auto entry=base+offset;
    std::ofstream trace(prefix+".jsonl");if(!trace)throw std::runtime_error("Cannot open debug trace");
    trace<<std::setprecision(9);
    DebugCapture capture;capture.pid=pid;
    BOOL debugger{};if(!CheckRemoteDebuggerPresent(process.h,&debugger))throw std::runtime_error("Debugger identity query failed, Win32="+std::to_string(GetLastError()));
    if(debugger)throw std::runtime_error("Existing debugger present; capture refuses to interfere");
    if(!DebugActiveProcess(pid))throw std::runtime_error("Debug attach denied; no privilege escalation attempted, Win32="+std::to_string(GetLastError()));
    capture.attached=true;if(!DebugSetProcessKillOnExit(FALSE))throw std::runtime_error("Cannot disable debugger kill-on-exit");
    std::map<DWORD,Pending> pending;std::size_t completed{},entered{};bool initial_break=true,deliberate_abort=false;
    using Clock=std::chrono::steady_clock;const auto deadline=Clock::now()+std::chrono::seconds(8);
    while(completed<pairs&&Clock::now()<deadline){
        DEBUG_EVENT event{};if(!WaitForDebugEvent(&event,100)){if(GetLastError()==ERROR_SEM_TIMEOUT)continue;throw std::runtime_error("Debug event wait failed");}
        DWORD continuation=DBG_CONTINUE;
        try{
            if(event.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT){
                if(event.u.CreateProcessInfo.hFile)CloseHandle(event.u.CreateProcessInfo.hFile);
                capture.arm(event.dwThreadId,entry);
            }else if(event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT)capture.arm(event.dwThreadId,entry);
            else if(event.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT){if(event.u.LoadDll.hFile)CloseHandle(event.u.LoadDll.hFile);}
            else if(event.dwDebugEventCode==EXIT_THREAD_DEBUG_EVENT){capture.original.erase(event.dwThreadId);pending.erase(event.dwThreadId);}
            else if(event.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT)throw std::runtime_error("Target exited during capture: code="+std::to_string(event.u.ExitProcess.dwExitCode)+" entries="+std::to_string(entered));
            else if(event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT){
                const auto code=event.u.Exception.ExceptionRecord.ExceptionCode;
                if(code==EXCEPTION_BREAKPOINT&&initial_break){initial_break=false;}
                else if(code==EXCEPTION_SINGLE_STEP){
                    Handle thread{OpenThread(THREAD_GET_CONTEXT|THREAD_SET_CONTEXT,FALSE,event.dwThreadId)};
                    CONTEXT c{};c.ContextFlags=CONTEXT_ALL;
                    if(!thread.h||!GetThreadContext(thread.h,&c))throw std::runtime_error("Cannot inspect breakpoint context");
                    if((c.Dr6&1)&&c.Rip==entry){
                        Pending p;p.callback_arg0=c.Rcx;p.context=c.R8;std::uint64_t ret{};
                        if(!read(process.h,c.Rsp,ret)||!read(process.h,c.R8,p.manager)||!read(process.h,c.R8+8,p.vehicle)||
                           !read(process.h,c.R8+0x10,p.item)||!read(process.h,c.R8+0x14,p.raw_clock)||
                           !read(process.h,p.manager+0x110,p.dyna)||!read(process.h,p.dyna+0x70,p.states)||
                           !read(process.h,p.vehicle+0x88,p.configuration))throw std::runtime_error("Original force ABI capture unreadable");
                        std::uintptr_t ids{};if(!read(process.h,p.dyna+0xb0,ids)||!read(process.h,ids+p.item*4,p.index)||p.index>1024)
                            throw std::runtime_error("Captured force item/index invalid");
                        std::uintptr_t force_array{};if(!read(process.h,p.dyna+0xa0,force_array))throw std::runtime_error("Cannot read original force accumulator array");
                        p.forces=force_array+p.index*0x18;
                        trace<<"{\"kind\":\"entry_relationship\",\"owned_fixture\":"<<(owned?"true":"false")<<",\"callback_arg0\":\"0x"<<std::hex<<p.callback_arg0
                            <<"\",\"manager\":\"0x"<<p.manager<<"\",\"vehicle\":\"0x"<<p.vehicle<<"\",\"dyna\":\"0x"<<p.dyna<<"\",\"states\":\"0x"<<p.states<<"\",\"forces\":\"0x"<<p.forces<<std::dec<<"\"}\n";
                        if(abort_fixture){deliberate_abort=true;throw std::runtime_error("Deliberate owned-fixture abort before resuming breakpoint");}
                        if(!read(process.h,p.forces,p.forces_before)||!read(process.h,p.states+p.index*0x58,p.rigid_before))throw std::runtime_error("Cannot read synchronized force inputs");
                        std::memcpy(&p.dt,&c.Xmm1,4);pending[event.dwThreadId]=p;++entered;
                        c.Dr1=ret;c.Dr7=(c.Dr7&~DWORD64(0xf00000))|4;
                    }else if((c.Dr6&2)&&pending.contains(event.dwThreadId)){
                        const auto p=pending.at(event.dwThreadId);std::array<float,6> forces{};std::array<float,22> state{};
                        if(!read(process.h,p.forces,forces)||!read(process.h,p.states+p.index*0x58,state))throw std::runtime_error("Cannot read synchronized force result");
                        trace<<"{\"pair\":"<<completed<<",\"owned_fixture\":"<<(owned?"true":"false")<<",\"pid\":"<<pid<<",\"thread\":"<<event.dwThreadId<<",\"force_rva\":\"0x"<<std::hex<<offset<<std::dec<<"\",\"dt\":"<<p.dt
                            <<",\"raw_clock_word\":"<<p.raw_clock<<",\"item\":"<<p.item<<",\"index\":"<<p.index<<",\"context\":\"0x"<<std::hex<<p.context
                            <<"\",\"manager\":\"0x"<<p.manager<<"\",\"vehicle\":\"0x"<<p.vehicle<<"\",\"dyna\":\"0x"<<p.dyna<<"\",\"states\":\"0x"<<p.states
                            <<"\",\"configuration\":\"0x"<<p.configuration<<std::dec<<"\",\"forces\":[";
                        for(unsigned k=0;k<6;k++){if(k)trace<<',';trace<<forces[k];}trace<<"],\"rigid\":[";
                        for(unsigned k=0;k<22;k++){if(k)trace<<',';trace<<state[k];}trace<<"],\"forces_before\":[";
                        for(unsigned k=0;k<6;k++){if(k)trace<<',';trace<<p.forces_before[k];}trace<<"],\"rigid_before\":[";
                        for(unsigned k=0;k<22;k++){if(k)trace<<',';trace<<p.rigid_before[k];}trace<<"],\"internal_tick_verified\":false}\n";
                        pending.erase(event.dwThreadId);++completed;c.Dr1=0;c.Dr7&=~DWORD64(4);
                    }else continuation=DBG_EXCEPTION_NOT_HANDLED;
                    if(continuation==DBG_CONTINUE){c.Dr6=0;c.EFlags|=0x10000;if(!SetThreadContext(thread.h,&c))throw std::runtime_error("Cannot resume hardware breakpoint");}
                    if(completed==pairs)capture.restore_while_stopped();
                }else continuation=DBG_EXCEPTION_NOT_HANDLED;
            }
        }catch(...){
            // Restore while every target thread is still stopped. Continuing
            // first can race the same execution breakpoint on the error path.
            try{capture.restore_while_stopped();}catch(...){++capture.restore_failures;}
            ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation);capture.detach();
            if(deliberate_abort)break;throw;
        }
        if(!ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation))throw std::runtime_error("Cannot continue debug event");
    }
    capture.detach();trace.flush();if(!trace)throw std::runtime_error("Cannot persist synchronized trace");
    std::cout<<"PHYSICS_DEBUG_CAPTURE entries="<<entered<<" pairs="<<completed<<" owned_fixture="<<owned<<" deliberate_abort="<<deliberate_abort<<" executable_bytes_patched=false detached="<<capture.detached<<" restore_failures="<<capture.restore_failures<<'\n';
    if(!capture.detached||capture.restore_failures)throw std::runtime_error("Debugger cleanup did not fully verify");
    if(completed!=pairs&&!deliberate_abort)throw std::runtime_error("Requested force pairs not reached within eight seconds");
    if(owned&&WaitForSingleObject(child_process.h,5000)!=WAIT_OBJECT_0)throw std::runtime_error("Owned fixture did not exit after clean detach");
    if(owned){DWORD code{};if(!GetExitCodeProcess(child_process.h,&code)||code!=0)throw std::runtime_error("Owned fixture did not exit normally");}
}catch(const std::exception& e){std::cerr<<"PHYSICS_DEBUG_CAPTURE_ERROR "<<e.what()<<'\n';return 1;}
