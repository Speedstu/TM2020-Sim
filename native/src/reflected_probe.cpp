// Complete reflected VISUAL state hypotheses, not authoritative physics.
#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#pragma pack(push,1)
struct SnapshotHead{char magic[8];std::uint32_t version,entry_bytes;std::uint64_t pid,scanned,count;};
struct Position{std::uint64_t address;float xyz[3];};
#pragma pack(pop)
int main(int argc,char** argv)try{
    if(argc!=4)throw std::invalid_argument("Usage: reflected_probe manifest-v3 snapshot.tmvec output.csv");
    tm2020::live::ReadOnlyObserver observer(argv[1]);
    auto pose=observer.poll();if(!pose)throw std::runtime_error("No current pose consensus");
    std::ifstream in(argv[2],std::ios::binary);SnapshotHead h{};
    in.read(reinterpret_cast<char*>(&h),sizeof(h));
    if(!in||std::string(h.magic,6)!="TMVEC1"||h.entry_bytes!=20||h.pid!=observer.process_id()||h.count>10000000)
        throw std::runtime_error("Invalid numeric snapshot");
    HANDLE handle=OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,observer.process_id());
    if(!handle)throw std::runtime_error("Read-only process access failed");
    struct Guard{HANDLE h;~Guard(){CloseHandle(h);}} guard{handle};
    std::ofstream out(argv[3]);if(!out)throw std::runtime_error("Cannot create output");
    out<<"position_address,allocation_base,type,decoded,input_steer,input_gas,input_brake,x,y,z,vx,vy,vz,front_speed,gear,ground,flags\n";
    std::size_t candidates{},decoded{};
    for(std::uint64_t i=0;i<h.count;i++){
        Position p{};in.read(reinterpret_cast<char*>(&p),sizeof(p));if(!in)throw std::runtime_error("Truncated snapshot");
        if(std::hypot(double(p.xyz[0])-1200.,double(p.xyz[2])-1360.)>2.0||std::abs(p.xyz[1]-34.014)>3)continue;
        std::array<std::byte,tm2020::live::visual_state_bytes> bytes{};SIZE_T got{};
        if(!ReadProcessMemory(handle,reinterpret_cast<LPCVOID>(p.address-0x50),bytes.data(),bytes.size(),&got)||got!=bytes.size())continue;
        float xyz[3]{};std::memcpy(xyz,bytes.data()+0x50,12);
        if(std::hypot(xyz[0]-pose->xyz.x,xyz[2]-pose->xyz.z)>2)continue;
        candidates++;const auto s=tm2020::live::decode_visual_state(bytes);if(s)decoded++;
        auto f=[&](std::size_t at){float x{};std::memcpy(&x,bytes.data()+at,4);return x;};
        std::uint32_t flags{};std::memcpy(&flags,bytes.data()+0x88,4);
        MEMORY_BASIC_INFORMATION region{};VirtualQueryEx(handle,reinterpret_cast<LPCVOID>(p.address),&region,sizeof(region));
        out<<"0x"<<std::hex<<p.address<<",0x"<<reinterpret_cast<std::uintptr_t>(region.AllocationBase)<<std::dec
           <<','<<region.Type<<','<<bool(s)<<','<<f(0x10)<<','<<f(0x14)<<','<<f(0x18)
           <<','<<xyz[0]<<','<<xyz[1]<<','<<xyz[2]<<','<<f(0x5c)<<','<<f(0x60)<<','<<f(0x64)
           <<','<<f(0x74)<<','<<(s?s->gear:-999)<<','<<(s?s->ground_contact:false)<<','<<flags<<'\n';
    }
    std::cout<<"REFLECTED_STATE_PROBE shortlist="<<candidates<<" decoded="<<decoded<<" physics_owner=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
