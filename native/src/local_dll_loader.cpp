// Ordinary LoadLibraryW loader for the user's local Solo research SDK.
// No manual mapping, hooks, hiding, protection bypass, or privilege elevation.
#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <array>
#include <filesystem>
#include <fstream>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <thread>
#include <chrono>
namespace fs=std::filesystem;
struct Handle {
    HANDLE value{};
    explicit Handle(HANDLE h):value(h){}
    ~Handle(){if(value&&value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
    Handle(const Handle&)=delete;
};
void require(bool b,const char* msg){if(!b)throw std::runtime_error(msg);}
void verify_local_client(DWORD pid,bool isolated=true){
    if(isolated){
    std::ifstream routes("Z:/proc/self/net/route"),ipv6("Z:/proc/self/net/ipv6_route");
    require(bool(routes)&&bool(ipv6),"Offline Wine network namespace cannot be verified");
    std::string line;std::getline(routes,line);
    while(std::getline(routes,line)){
        const auto end=line.find_first_of(" \t");require(line.substr(0,end)=="lo","Networked client loading refused");
    }
    while(std::getline(ipv6,line)){
        const auto end=line.find_last_not_of(" \t\r");
        if(end!=std::string::npos){const auto start=line.find_last_of(" \t",end);require(line.substr(start+1,end-start)=="lo","Networked IPv6 namespace refused");}
    }
    }
    Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid));
    require(bool(process.value),"Cannot identify local client");
    std::array<wchar_t,32768> image{};DWORD length=image.size();
    require(QueryFullProcessImageNameW(process.value,0,image.data(),&length)!=0,"Cannot read client image path");
    const fs::path exe(std::wstring(image.data(),length));
    require(_wcsicmp(exe.filename().c_str(),L"Trackmania.exe")==0,"Unexpected client image");
    require(tm2020::live::file_sha256(exe)==tm2020::live::visual_state_build_sha256,"Unsupported client build");
}
std::uintptr_t module_base(DWORD pid,const fs::path& name,bool full_path){
    HANDLE raw=INVALID_HANDLE_VALUE;DWORD error{};
    // Microsoft documents ERROR_BAD_LENGTH as transient while module lists
    // change. Retry only this error, with a bounded deadline and no privilege
    // changes. Other failures remain explicit.
    for(int attempt=0;attempt<100;attempt++){
        raw=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid);
        if(raw!=INVALID_HANDLE_VALUE)break;
        error=GetLastError();if(error!=ERROR_BAD_LENGTH)break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    Handle snapshot(raw);
    if(snapshot.value==INVALID_HANDLE_VALUE)throw std::runtime_error("Cannot enumerate target modules; Win32="+std::to_string(error));
    MODULEENTRY32W m{};m.dwSize=sizeof(m);
    if(Module32FirstW(snapshot.value,&m))do {
        const auto actual=full_path?fs::path(m.szExePath):fs::path(m.szModule);
        if(_wcsicmp(actual.c_str(),name.c_str())==0)return reinterpret_cast<std::uintptr_t>(m.modBaseAddr);
    }while(Module32NextW(snapshot.value,&m));
    return 0;
}
bool load(DWORD pid,const fs::path& dll){
    require(dll.is_absolute()&&fs::is_regular_file(dll),"DLL must be an existing absolute file");
    if(module_base(pid,dll,true))return false;
    // Validate the module architecture before asking Windows to load it.
    std::ifstream in(dll,std::ios::binary);std::array<char,64> dos{};in.read(dos.data(),dos.size());
    require(bool(in)&&dos[0]=='M'&&dos[1]=='Z',"Invalid DLL DOS header");
    std::uint32_t pe{};std::memcpy(&pe,dos.data()+0x3c,4);
    require(pe<fs::file_size(dll)&&pe<16*1024*1024,"Invalid DLL PE offset");
    in.seekg(pe);std::array<unsigned char,24> header{};in.read(reinterpret_cast<char*>(header.data()),header.size());
    require(bool(in)&&header[0]=='P'&&header[1]=='E'&&header[2]==0&&header[3]==0&&header[4]==0x64&&header[5]==0x86&&
        ((header[22]|(unsigned(header[23])<<8))&0x2000),"Expected x64 PE DLL");
    Handle process(OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_CREATE_THREAD|PROCESS_VM_OPERATION|PROCESS_VM_WRITE|PROCESS_VM_READ,FALSE,pid));
    require(bool(process.value),"Windows refused local DLL loading; no bypass attempted");
    BOOL wow64=FALSE;require(IsWow64Process(process.value,&wow64)&&!wow64,"Expected native x64 target");
    const auto local_entry=GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"LoadLibraryW");
    require(bool(local_entry),"LoadLibraryW unavailable");
    HMODULE owner{};
    require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(local_entry),&owner)!=0,"Cannot resolve forwarded loader owner");
    std::array<wchar_t,32768> owner_path{};
    require(GetModuleFileNameW(owner,owner_path.data(),static_cast<DWORD>(owner_path.size()))!=0,"Cannot resolve system loader module");
    const auto remote_owner=module_base(pid,fs::path(owner_path.data()).filename(),false);
    require(remote_owner!=0,"Target does not contain expected system loader module");
    const auto offset=reinterpret_cast<std::uintptr_t>(local_entry)-reinterpret_cast<std::uintptr_t>(owner);
    const auto path=dll.wstring();const auto bytes=(path.size()+1)*sizeof(wchar_t);
    void* remote_path=VirtualAllocEx(process.value,nullptr,bytes,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    require(remote_path!=nullptr,"Cannot allocate DLL path in local target");
    struct Allocation {
        HANDLE process;void* path;bool in_flight=false;
        ~Allocation(){if(path&&!in_flight)VirtualFreeEx(process,path,0,MEM_RELEASE);}
    } allocation{process.value,remote_path};
    SIZE_T written{};
    require(WriteProcessMemory(process.value,remote_path,path.c_str(),bytes,&written)&&written==bytes,"DLL path write failed");
    Handle thread(CreateRemoteThread(process.value,nullptr,0,reinterpret_cast<LPTHREAD_START_ROUTINE>(remote_owner+offset),remote_path,0,nullptr));
    require(bool(thread.value),"Windows refused local loader thread; no bypass attempted");
    allocation.in_flight=true;
    require(WaitForSingleObject(thread.value,10000)==WAIT_OBJECT_0,
        "Loader did not finish in 10s; path allocation retained because the thread may still read it");
    allocation.in_flight=false;
    // Do not truncate a 64-bit HMODULE to GetExitCodeThread's DWORD.
    require(module_base(pid,dll,true)!=0,"DLL not found in target module list after LoadLibraryW");
    return true;
}
void probe_sdk(DWORD pid,const fs::path& dll,const char* symbol="tm2020_policy_host_probe"){
    const auto remote=module_base(pid,dll,true);require(remote!=0,"Cannot qualify absent SDK module");
    const auto local=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
    require(local!=nullptr,"Cannot resolve local SDK probe export");
    struct Library{HMODULE p;~Library(){FreeLibrary(p);}} library{local};
    const auto entry=GetProcAddress(local,symbol);require(entry!=nullptr,"Module is not a qualifying SDK DLL");
    HMODULE entry_owner{};
    require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(entry),&entry_owner)&&entry_owner==local,"SDK probe export is forwarded outside the supplied module");
    const auto offset=reinterpret_cast<std::uintptr_t>(entry)-reinterpret_cast<std::uintptr_t>(local);
    Handle process(OpenProcess(PROCESS_CREATE_THREAD|PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,pid));
    require(bool(process.value),"Windows refused SDK qualification thread access");
    const bool runtime=std::string(symbol)=="tm2020_runtime_probe";
    Handle thread(CreateRemoteThread(process.value,nullptr,runtime?1048576:0,reinterpret_cast<LPTHREAD_START_ROUTINE>(remote+offset),nullptr,
        runtime?STACK_SIZE_PARAM_IS_A_RESERVATION:0,nullptr));
    require(bool(thread.value),"Windows refused SDK probe thread");
    const DWORD timeout=std::string(symbol)=="tm2020_internal_selftest"?120000:10000;
    require(WaitForSingleObject(thread.value,timeout)==WAIT_OBJECT_0,"SDK probe exceeded its bounded test deadline");
    DWORD result{};require(GetExitCodeThread(thread.value,&result),"Cannot read SDK probe result");
    if(result!=1)throw std::runtime_error(std::string(symbol)+" failed, exit="+std::to_string(result));
}
void run_bot(DWORD pid,const fs::path& dll,const fs::path& config){
    require(config.is_absolute()&&fs::is_regular_file(config),"Expected absolute bot config path");
    const auto remote=module_base(pid,dll,true);require(remote!=0,"Runtime module absent");
    const auto local=LoadLibraryExW(dll.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
    require(local!=nullptr,"Cannot resolve local runtime export");
    struct Library{HMODULE p;~Library(){FreeLibrary(p);}} library{local};
    const auto entry=GetProcAddress(local,"tm2020_bot_run");require(entry!=nullptr,"Runtime has no bot entry");
    HMODULE entry_owner{};
    require(GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(entry),&entry_owner)&&entry_owner==local,"Bot export is forwarded outside the supplied module");
    const auto offset=reinterpret_cast<std::uintptr_t>(entry)-reinterpret_cast<std::uintptr_t>(local);
    Handle process(OpenProcess(PROCESS_CREATE_THREAD|PROCESS_QUERY_INFORMATION|PROCESS_VM_READ|PROCESS_VM_WRITE|PROCESS_VM_OPERATION,FALSE,pid));
    require(bool(process.value),"Windows refused explicit bot worker access");
    const auto path=config.wstring();const auto bytes=(path.size()+1)*sizeof(wchar_t);
    void* parameter=VirtualAllocEx(process.value,nullptr,bytes,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE);
    require(parameter!=nullptr,"Cannot allocate runtime config path");
    struct Parameter{HANDLE process;void* p;bool running=false;~Parameter(){if(p&&!running)VirtualFreeEx(process,p,0,MEM_RELEASE);}} allocation{process.value,parameter};
    SIZE_T written{};require(WriteProcessMemory(process.value,parameter,path.c_str(),bytes,&written)&&written==bytes,"Config path write failed");
    Handle thread(CreateRemoteThread(process.value,nullptr,8*1048576,reinterpret_cast<LPTHREAD_START_ROUTINE>(remote+offset),parameter,
        STACK_SIZE_PARAM_IS_A_RESERVATION,nullptr));
    require(bool(thread.value),"Windows refused explicit bot worker thread");allocation.running=true;
    const auto began=GetTickCount64();DWORD wait{};
    do {wait=WaitForSingleObject(thread.value,1000);}while(wait==WAIT_TIMEOUT&&GetTickCount64()-began<240000);
    require(wait==WAIT_OBJECT_0,"Worker still pending/failed after bounded wait; parameter retained, no forced thread termination");
    allocation.running=false;DWORD result{};
    require(GetExitCodeThread(thread.value,&result)!=0,"Cannot read worker result");
    std::cout<<"INJECTED_WORKER_RETURNED pid="<<pid<<" result="<<result<<" config="<<config.string()<<std::endl;
    require(result==0,"Injected bot worker returned failure; inspect its status and retained trace");
}
int main(int argc,char** argv)try{
    const bool confirmed_local=argc==4&&std::string(argv[1])=="--run-confirmed-local-game";
    if((argc==3&&std::string(argv[1])=="--probe-local-game")||(argc==4&&std::string(argv[1])=="--run-local-game")||confirmed_local){
        Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
        require(snapshot.value!=INVALID_HANDLE_VALUE,"Cannot enumerate local game");
        PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);DWORD pid{};
        if(Process32FirstW(snapshot.value,&entry))do{
            if(_wcsicmp(entry.szExeFile,L"Trackmania.exe")==0){
                require(pid==0,"More than one local Trackmania process");pid=entry.th32ProcessID;
            }
        }while(Process32NextW(snapshot.value,&entry));
        require(pid!=0,"Trackmania is not running");
        verify_local_client(pid,!confirmed_local);
        const auto dll=fs::canonical(argv[2]);const bool added=load(pid,dll);
        probe_sdk(pid,dll,"tm2020_runtime_probe");
        if(argc==4)run_bot(pid,dll,fs::canonical(argv[3]));
        std::cout<<"LOCAL_GAME_SDK_PROBE pid="<<pid<<" added="<<added
                 <<" runtime_abi=1 worker_requested="<<(argc==4?"true":"false")<<"\n";return 0;
    }
    if(argc==4&&std::string(argv[1])=="--fixture-child"){
        const auto event=reinterpret_cast<HANDLE>(std::stoull(argv[2]));
        const auto ready=reinterpret_cast<HANDLE>(std::stoull(argv[3]));
        require(SetEvent(ready)!=0,"Cannot signal initialized fixture");CloseHandle(ready);
        // Must outlive the longest bounded SDK selftest. Exiting with ABI's
        // success value (1) on timeout can falsely qualify a killed probe.
        const auto result=WaitForSingleObject(event,180000);CloseHandle(event);return result==WAIT_OBJECT_0?0:125;
    }
    if(argc==3&&(std::string(argv[1])=="--selftest"||std::string(argv[1])=="--selftest-runtime"||std::string(argv[1])=="--selftest-internal")){
        const bool runtime=std::string(argv[1])=="--selftest-runtime";
        SECURITY_ATTRIBUTES security{sizeof(security),nullptr,TRUE};Handle event(CreateEventW(&security,TRUE,FALSE,nullptr));
        require(bool(event.value),"Cannot create fixture event");
        Handle ready(CreateEventW(&security,TRUE,FALSE,nullptr));require(bool(ready.value),"Cannot create fixture ready event");
        std::array<wchar_t,32768> executable{};GetModuleFileNameW(nullptr,executable.data(),static_cast<DWORD>(executable.size()));
        std::wstring command=L"\""+std::wstring(executable.data())+L"\" --fixture-child "+std::to_wstring(reinterpret_cast<std::uintptr_t>(event.value))+
            L" "+std::to_wstring(reinterpret_cast<std::uintptr_t>(ready.value));
        STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION child{};
        require(CreateProcessW(executable.data(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,nullptr,&startup,&child)!=0,"Cannot create owned fixture process");
        Handle child_process(child.hProcess),child_thread(child.hThread);
        struct Finish{HANDLE event,process;~Finish(){SetEvent(event);WaitForSingleObject(process,5000);}} finish{event.value,child.hProcess};
        require(WaitForSingleObject(ready.value,5000)==WAIT_OBJECT_0,"Owned fixture did not initialize in 5s");
        const auto dll=fs::canonical(argv[2]);
        require(load(child.dwProcessId,dll),"Fixture load was unexpectedly already present");
        require(!load(child.dwProcessId,dll),"Duplicate module load should be idempotent");
        probe_sdk(child.dwProcessId,dll,std::string(argv[1])=="--selftest-internal"?"tm2020_internal_selftest":(runtime?"tm2020_runtime_probe":"tm2020_policy_host_probe"));
        std::cout<<"PASS OWNED_PROCESS_DLL_LOAD path_verified=true aslr_owner_resolved=true duplicate_idempotent=true sdk_entry_executed=true game_accessed=false\n";
        return 0;
    }
    if((argc!=4&&argc!=6)||std::string(argv[1])!="--confirm-local-solo"||(argc==6&&std::string(argv[4])!="--run"))throw std::invalid_argument(
        "Usage: local_dll_loader --selftest[-runtime] dll | --confirm-local-solo pose-manifest dll [--run config]");
    tm2020::live::ReadOnlyObserver identity(argv[2]);
    verify_local_client(identity.process_id());
    DWORD foreground{};GetWindowThreadProcessId(GetForegroundWindow(),&foreground);
    require(foreground==identity.process_id(),"Trackmania must be foreground in local Solo");
    const auto dll=fs::canonical(argv[3]);const bool added=load(identity.process_id(),dll);
    probe_sdk(identity.process_id(),dll,argc==6?"tm2020_runtime_probe":"tm2020_policy_host_probe");
    if(argc==6)run_bot(identity.process_id(),dll,fs::canonical(argv[5]));
    std::cout<<"LOCAL_GAME_DLL_MODULE_VERIFIED pid="<<identity.process_id()<<" added="<<added
             <<" module="<<dll.string()<<" sdk_entry_executed=true "<<(argc==6?"runtime_abi=1":"policy_abi=1")
             <<" worker_requested="<<(argc==6?"true":"false")<<"\n";
}catch(const std::exception& e){std::cerr<<"DLL_LOADER_ERROR "<<e.what()<<'\n';return 1;}
