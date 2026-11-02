// Historical read-only TM2020 pointer-chain compatibility probe.
// Source reference: Polybagel/TM2020-TAS (MIT), tas/main.cpp.
// This historic chain is NOT established valid for 2026.2.2.1751.
// Do not write to target process; never use guessed pointers for bot control.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <Psapi.h>
#include <array>
#include <cstdint>
#include <cmath>
#include <iostream>
#include <iomanip>
#include <limits>
#include <stdexcept>
#include <string>
#include <filesystem>

struct Handle {
    HANDLE h{};
    explicit Handle(HANDLE a):h(a){}
    ~Handle(){if(h && h!=INVALID_HANDLE_VALUE)CloseHandle(h);}
    Handle(const Handle&)=delete;Handle& operator=(const Handle&)=delete;
};
static bool read_exact(HANDLE h,uintptr_t addr,void* out,size_t count){
    if(addr<0x10000 || addr>0x00007FFFFFFFFFFFULL || count==0) return false;
    SIZE_T n=0;
    return ReadProcessMemory(h,reinterpret_cast<LPCVOID>(addr),out,count,&n)&&n==count;
}
static DWORD find_process(){
    Handle snap(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
    if(snap.h==INVALID_HANDLE_VALUE)return 0;
    PROCESSENTRY32W e{};e.dwSize=sizeof e;
    if(!Process32FirstW(snap.h,&e))return 0;
    do{if(_wcsicmp(e.szExeFile,L"Trackmania.exe")==0)return e.th32ProcessID;}
    while(Process32NextW(snap.h,&e));
    return 0;
}
int main() try {
    const DWORD pid=find_process();
    if(!pid){std::cout<<"NOT_RUNNING historical chain not tested\n";return 0;}
    Handle process(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|PROCESS_VM_READ,FALSE,pid));
    if(!process.h)throw std::runtime_error("Read-only OpenProcess denied");
    Handle modules(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid));
    MODULEENTRY32W m{};m.dwSize=sizeof(m);
    if(!Module32FirstW(modules.h,&m))throw std::runtime_error("Cannot enumerate modules");
    while(_wcsicmp(m.szModule,L"Trackmania.exe")!=0){
        if(!Module32NextW(modules.h,&m))throw std::runtime_error("Main exe module absent");
    }
    constexpr uintptr_t oldRva=0x01e340f8;
    constexpr std::array<uint32_t,7> offsets{{0x2a8,0x1c0,0x30,0x160,0x198,0xd20,0x2c}};
    const uintptr_t base=reinterpret_cast<uintptr_t>(m.modBaseAddr);
    if(oldRva>=m.modBaseSize)throw std::runtime_error("Historic static RVA no longer in game module");
    uintptr_t address=base+oldRva;
    std::cout<<std::hex;
    std::cout<<"HISTORICAL 2020 CHAIN gameModule=0x"<<base<<" rootRVA=0x"<<oldRva<<"\n";
    for(size_t depth=0;depth<offsets.size();++depth){
        uintptr_t pointer=0;
        if(!read_exact(process.h,address,&pointer,sizeof pointer)){
            std::cout<<"CHAIN_MISS depth="<<depth<<" at=0x"<<address
                     <<" reason=unreadable; VALIDATED=false\n";
            return 0;
        }
        if(pointer<0x10000||pointer>0x00007FFFFFFFFFFFULL){
            std::cout<<"CHAIN_MISS depth="<<depth<<" at=0x"<<address
                     <<" pointer=0x"<<pointer<<" reason=invalid_pointer; VALIDATED=false\n";
            return 0;
        }
        if(pointer>UINTPTR_MAX-offsets[depth])throw std::runtime_error("pointer overflow");
        address=pointer+offsets[depth];
        std::cout<<"  depth="<<std::dec<<depth<<std::hex
                 <<" ptr=0x"<<pointer<<" resolved=0x"<<address<<"\n";
    }
    std::array<float,3> xyz{};
    if(!read_exact(process.h,address,xyz.data(),sizeof xyz)){
        std::cout<<"CHAIN_MISS finalPositionAddr=0x"<<address<<" reason=unreadable; VALIDATED=false\n";
        return 0;
    }
    bool physical=true;
    for(float v:xyz)if(!std::isfinite(v)||std::abs(v)>1e6)physical=false;
    std::cout<<std::dec<<std::fixed<<std::setprecision(4)
             <<"HISTORIC_CHAIN_CANDIDATE coords=("<<xyz[0]<<","<<xyz[1]<<","<<xyz[2]<<")"
             <<" finitePlausible="<<physical
             <<" actualVehicleStateVerified=false\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"HISTORICAL_CHAIN_ERROR "<<e.what()<<"\n";return 1;
}
