// Read-only Win32 process probe for Trackmania 2020 RE.
// No DLL injection, remote thread, memory writes, hook/patch or bypass.
// Works without elevated privileges when process permissions allow.
// RVAs below were discovered by OFFLINE search of game v2026.2.2.1751;
// their contents are not validated vehicle state offsets.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

struct Handle {
    HANDLE h{INVALID_HANDLE_VALUE};
    explicit Handle(HANDLE p):h(p){}
    ~Handle(){if(h&&h!=INVALID_HANDLE_VALUE)CloseHandle(h);}
    Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
};
static bool read(HANDLE process,const void* address,void* output,size_t count){
    SIZE_T got=0;
    return ReadProcessMemory(process,address,output,count,&got)&&got==count;
}
static bool selftest(){
    auto self=GetCurrentProcess();
    const HMODULE main=GetModuleHandleW(nullptr);
    if(!main)throw std::runtime_error("No self module");
    std::array<char,2> signature{};
    if(!read(self,main,signature.data(),signature.size()) ||
       signature[0]!='M'||signature[1]!='Z')
        throw std::runtime_error("Cannot read self PE header");
    char magic[]="tm2020-self-owned-memory-research";
    std::array<char,sizeof(magic)> copied{};
    if(!read(self,magic,copied.data(),copied.size())||
       std::strcmp(magic,copied.data())!=0)
        throw std::runtime_error("Self memory read mismatch");
    std::cout<<"PASS SELFTEST: OpenProcess/ReadProcessMemory safety probe; own PE and own data\n";
    return true;
}
static DWORD findTrackmaniaPID(){
    Handle snap(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
    if(snap.h==INVALID_HANDLE_VALUE)throw std::runtime_error("Process enumeration failed");
    PROCESSENTRY32W e{};e.dwSize=sizeof(e);
    if(!Process32FirstW(snap.h,&e))return 0;
    do {
        if(_wcsicmp(e.szExeFile,L"Trackmania.exe")==0)return e.th32ProcessID;
    }while(Process32NextW(snap.h,&e));
    return 0;
}
static int probe(){
    const auto pid=findTrackmaniaPID();
    if(!pid) {
        std::cout<<"NOT_RUNNING: Trackmania.exe is not active; no process was launched.\n";
        return 0;
    }
    Handle process(OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid));
    if(!process.h) {
        std::cout<<"NOT_PERMITTED pid="<<pid<<" OpenProcess refused. No privileges escalated.\n";
        return 0;
    }
    Handle modules(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid));
    if(modules.h==INVALID_HANDLE_VALUE) {
        std::cout<<"NOT_PERMITTED pid="<<pid<<" Cannot enumerate modules.\n";
        return 0;
    }
    MODULEENTRY32W entry{};entry.dwSize=sizeof(entry);
    if(!Module32FirstW(modules.h,&entry))throw std::runtime_error("Module enumeration failed");
    bool found=false;
    do {
        if(_wcsicmp(entry.szModule,L"Trackmania.exe")!=0)continue;
        found=true;
        const uintptr_t base=reinterpret_cast<uintptr_t>(entry.modBaseAddr);
        std::array<uint8_t,2> mz{};
        if(!read(process.h,reinterpret_cast<void*>(base),mz.data(),mz.size())||
           mz[0]!='M'||mz[1]!='Z'){
            std::cout<<"NOT_PERMITTED cannot read process module bytes. No bypass attempted.\n";
            return 0;
        }
        std::cout<<"PASS READ_ONLY_GAME_PROBE pid="<<pid
                 <<" moduleBase=0x"<<std::hex<<base<<std::dec
                 <<" moduleBytes="<<entry.modBaseSize<<" MZ=valid\n";
        // These strings are selected based on the earlier static RE and are
        // not believed to be physical state or usable game addresses.
        struct Target {const char* name;uintptr_t rva;};
        constexpr std::array<Target,4> terms{{
            {"CSceneVehicleVis",0x1be75e8},
            {"ReactorBoost",0x1be12e0},
            {"InputSteer",0x1be7878},
            {"GroundContact",0x1be78e0}
        }};
        for(auto& t:terms) {
            if(t.rva+64>entry.modBaseSize)continue;
            std::array<char,64> bytes{};
            const auto addr=reinterpret_cast<void*>(base+t.rva);
            if(!read(process.h,addr,bytes.data(),bytes.size()))continue;
            std::string display;
            for(const char c:bytes) {
                if(c==0||display.size()==48)break;
                if(c>=32&&c<=126)display+=c;
                else {display.clear();break;}
            }
            std::cout<<"  candidate symbol "<<t.name<<" RVA=0x"<<std::hex<<t.rva
                     <<std::dec<<" text="<<display<<"\n";
        }
        break;
    }while(Module32NextW(modules.h,&entry));
    if(!found)std::cout<<"NO_MAIN_MODULE Trackmania.exe module could not be inspected.\n";
    return 0;
}
int main(int argc,char**argv)try {
    if(argc!=2)throw std::invalid_argument("Usage: tm2020_game_probe --selftest|--probe");
    if(std::strcmp(argv[1],"--selftest")==0)return selftest()?0:1;
    if(std::strcmp(argv[1],"--probe")==0)return probe();
    throw std::invalid_argument("Invalid option");
}catch(const std::exception& e){
    std::cerr<<"READ_ONLY_PROBE ERROR "<<e.what()<<"\n";
    return 1;
}
