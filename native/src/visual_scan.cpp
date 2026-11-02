// Structural, read-only current-build VISUAL state scan. Bounded byte budget.
#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>
int main(int argc,char** argv)try{
    if(argc!=5)throw std::invalid_argument("Usage: visual_scan manifest-v3 output.csv maxMegabytes radiusMeters");
    tm2020::live::ReadOnlyObserver observer(argv[1]);const auto pose=observer.poll();
    if(!pose)throw std::runtime_error("No pose consensus");
    const auto mb=std::stoull(argv[3]);const auto radius=std::stod(argv[4]);
    if(mb<1||mb>16384||!std::isfinite(radius)||radius<=0||radius>10)throw std::invalid_argument("Invalid scan bounds");
    HANDLE process=OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ,FALSE,observer.process_id());
    if(!process)throw std::runtime_error("Read-only access failed");
    struct Guard{HANDLE p;~Guard(){CloseHandle(p);}} guard{process};
    std::ofstream out(argv[2]);if(!out)throw std::runtime_error("Cannot create CSV");
    out<<"position_address,state_address,allocation_base,x,y,z,vx,vy,vz,front_speed,steer,gas,brake,gear,ground,engine,discontinuity\n";
    std::vector<std::byte> block((1<<20)+tm2020::live::visual_state_bytes);
    std::uintptr_t address=0x10000;std::uint64_t scanned{},pose_matches{},accepted{};std::size_t denied{};
    MEMORY_BASIC_INFORMATION r{};
    while(VirtualQueryEx(process,reinterpret_cast<LPCVOID>(address),&r,sizeof(r))==sizeof(r)){
        const auto base=reinterpret_cast<std::uintptr_t>(r.BaseAddress);
        const auto end=base+r.RegionSize;if(end<=address)break;address=end;
        if(r.State!=MEM_COMMIT||r.Type!=MEM_PRIVATE||(r.Protect&(PAGE_NOACCESS|PAGE_GUARD)))continue;
        for(auto p=base;p<end;){
            if(scanned>=mb*1048576)break;
            const auto n=static_cast<std::size_t>(std::min<std::uint64_t>({block.size(),end-p,mb*1048576-scanned}));
            SIZE_T got{};
            if(ReadProcessMemory(process,reinterpret_cast<LPCVOID>(p),block.data(),n,&got)){
                for(std::size_t offset=0x50;offset+0x310<=got;offset+=4){
                    float xyz[3]{};std::memcpy(xyz,block.data()+offset,12);
                    if(!std::isfinite(xyz[0])||!std::isfinite(xyz[1])||!std::isfinite(xyz[2])||
                       std::abs(xyz[0]-pose->xyz.x)>radius||std::abs(xyz[1]-pose->xyz.y)>radius||
                       std::abs(xyz[2]-pose->xyz.z)>radius)continue;
                    pose_matches++;
                    const auto state=tm2020::live::decode_visual_state(std::span(block.data()+offset-0x50,tm2020::live::visual_state_bytes));
                    if(!state||!state->engine_on)continue;
                    bool wheels=true;for(const auto& w:state->wheels)
                        wheels&=w.damper_length>=0&&w.damper_length<3&&std::abs(w.steer_angle)<4&&w.icing>=0&&w.icing<=1.01;
                    if(!wheels)continue;
                    accepted++;const auto& s=*state;
                    out<<"0x"<<std::hex<<(p+offset)<<",0x"<<(p+offset-0x50)<<",0x"<<reinterpret_cast<std::uintptr_t>(r.AllocationBase)<<std::dec
                       <<std::setprecision(9)<<','<<s.position.x<<','<<s.position.y<<','<<s.position.z
                       <<','<<s.world_velocity.x<<','<<s.world_velocity.y<<','<<s.world_velocity.z<<','<<s.front_speed
                       <<','<<s.input_steer<<','<<s.input_gas<<','<<s.input_brake<<','<<s.gear
                       <<','<<s.ground_contact<<','<<s.engine_on<<','<<unsigned(s.discontinuity_count)<<'\n';
                }
            }else denied++;
            scanned+=n;const auto advance=n>tm2020::live::visual_state_bytes?n-tm2020::live::visual_state_bytes:n;
            p+=advance;if(!advance)break;
        }
        if(scanned>=mb*1048576)break;
    }
    std::cout<<"VISUAL_STRUCT_SCAN scannedMB="<<scanned/1048576<<" pose_matches="<<pose_matches<<" structural_candidates="<<accepted
             <<" denied="<<denied<<" budget_exhausted="<<(scanned>=mb*1048576)<<" player_owner_verified=false\n";
}catch(const std::exception& e){std::cerr<<"VISUAL_SCAN_ERROR "<<e.what()<<'\n';return 1;}
