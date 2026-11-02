// Bounded read-only search for the statically recovered NSceneDyna SItemState.
// Optional short ordinary keyboard pulse correlates candidates; no owner claim.
#include "tm2020/recovered_rigid.hpp"
#include "tm2020/read_only_live.hpp"
#include "tm2020/local_input.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <chrono>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <thread>
using namespace tm2020::recovered;
bool plausible(const RigidState& s){
    float norm=0;for(float q:s.quaternion){if(!std::isfinite(q))return false;norm+=q*q;}
    if(std::abs(norm-1)>1e-3)return false;
    std::array<float,9> expected{};quaternion_to_matrix(expected,s.quaternion);
    for(std::size_t k=0;k<9;k++)if(!std::isfinite(s.rotation[k])||std::abs(s.rotation[k]-expected[k])>1e-3)return false;
    for(const auto* v:{&s.position,&s.linear_velocity,&s.angular_velocity})for(float x:*v)if(!std::isfinite(x)||std::abs(x)>100000)return false;
    return true;
}
template<class F>std::uint64_t scan(HANDLE process,std::size_t mb,F visit){
    constexpr std::size_t step=1<<20,overlap=0x100;
    std::vector<std::byte> bytes(step+overlap);std::uintptr_t address=0x10000;MEMORY_BASIC_INFORMATION region{};std::uint64_t count=0;
    while(VirtualQueryEx(process,reinterpret_cast<void*>(address),&region,sizeof(region))==sizeof(region)){
        const auto base=reinterpret_cast<std::uintptr_t>(region.BaseAddress),end=base+region.RegionSize;if(end<=address)break;address=end;
        const auto protect=region.Protect&0xff;
        if(region.State!=MEM_COMMIT||region.Type!=MEM_PRIVATE||region.Protect&(PAGE_GUARD|PAGE_NOACCESS)||
           (protect!=PAGE_READWRITE&&protect!=PAGE_WRITECOPY&&protect!=PAGE_EXECUTE_READWRITE&&protect!=PAGE_EXECUTE_WRITECOPY))continue;
        for(auto at=base;at<end&&count<mb*1048576ull;){
            const auto n=std::min<std::uint64_t>({bytes.size(),end-at,mb*1048576ull-count});SIZE_T got{};
            if(ReadProcessMemory(process,reinterpret_cast<void*>(at),bytes.data(),n,&got))visit(at,std::span(bytes.data(),got));
            count+=n;at+=n>overlap?n-overlap:n;
        }
        if(count>=mb*1048576ull)break;
    }return count;
}
template<class T>bool read(HANDLE process,std::uintptr_t address,T& value){
    SIZE_T got{};return ReadProcessMemory(process,reinterpret_cast<void*>(address),&value,sizeof(value),&got)&&got==sizeof(value);
}
int main(int argc,char** argv)try{
    if((argc!=7&&argc!=8)||std::string(argv[1])!="--confirm-local-solo")throw std::invalid_argument("Usage: physics_probe --confirm-local-solo manifest replay output-prefix scanMB observe|keyboard [manager-address]");
    tm2020::live::ReadOnlyObserver identity(argv[2]);const auto reference=tm2020::Replay::load(argv[3]);
    const auto anchor=reference.states.front().position;const auto mb=std::stoull(argv[5]);const bool pulse=std::string(argv[6])=="keyboard";
    if(mb<64||mb>16384||(std::string(argv[6])!="observe"&&!pulse))throw std::invalid_argument("Invalid probe limits/backend");
    const HANDLE process=OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,identity.process_id());
    if(!process)throw std::runtime_error("Read-only process open failed");struct Handle{HANDLE h;~Handle(){CloseHandle(h);}} owned{process};
    std::set<std::uintptr_t> candidates;
    std::uintptr_t targeted_manager{};std::uint64_t scanned{};
    if(argc==8){
        targeted_manager=std::stoull(argv[7],nullptr,0);std::uintptr_t states{},models{},model{},ids{};std::uint32_t index{};
        if(targeted_manager<0x10000||!read(process,targeted_manager+0x70,states)||!read(process,targeted_manager+0x10,models)||
           !read(process,targeted_manager+0xb0,ids)||!read(process,ids,index)||index>1024||!read(process,models+index*8,model))
            throw std::runtime_error("Target manager's independent accessor relationships invalid");
        RigidState state;const auto address=states+index*0x58;
        if(!read(process,address,state)||!plausible(state))throw std::runtime_error("Target state is not a coherent recovered layout");
        candidates.insert(address);
        std::ofstream sample(std::string(argv[4])+".manager-sample.json");
        sample<<"{\"schema\":\"tm2020_manager_hypothesis_v1\",\"pid\":"<<identity.process_id()<<",\"manager\":\"0x"<<std::hex<<targeted_manager
            <<"\",\"states\":\"0x"<<states<<"\",\"models\":\"0x"<<models<<"\",\"model\":\"0x"<<model<<"\",\"id_map\":\"0x"<<ids<<std::dec
            <<"\",\"id_zero_state_index\":"<<index<<",\"model_binary32_by_offset\":{";
        for(unsigned off=0;off<0x50;off+=4){std::uint32_t bits{};if(!read(process,model+off,bits))throw std::runtime_error("Cannot read model field");
            if(off)sample<<',';sample<<'\"'<<off<<"\":"<<bits;}
        std::uintptr_t user_data{},vehicle{},configuration{};std::uint32_t vehicle_id{},mapped_index{},selector{};
        const bool relationship=read(process,targeted_manager+0x40,user_data)&&read(process,user_data+index*16+8,vehicle)&&vehicle>=0x10000&&
            read(process,vehicle+0x10,vehicle_id)&&vehicle_id<1000000&&read(process,ids+vehicle_id*4,mapped_index)&&mapped_index==index&&
            read(process,vehicle+0x88,configuration)&&configuration>=0x10000&&read(process,configuration+0x1790,selector)&&selector<=16;
        sample<<"},\"vehicle_data_relationship_verified\":"<<(relationship?"true":"false");
        if(relationship)sample<<",\"vehicle_item_id\":"<<vehicle_id<<",\"force_variant_selector\":"<<selector
            <<",\"user_data\":\"0x"<<std::hex<<user_data<<"\",\"vehicle\":\"0x"<<vehicle<<"\",\"configuration\":\"0x"<<configuration<<std::dec<<'\"';
        std::uintptr_t vehicle_manager{},backlink{};
        const bool closed=relationship&&read(process,user_data+index*16,vehicle_manager)&&vehicle_manager>=0x10000&&
            read(process,vehicle_manager+0x110,backlink)&&backlink==targeted_manager;
        sample<<",\"vehicle_manager_dyna_backlink_verified\":"<<(closed?"true":"false");
        if(closed)sample<<",\"vehicle_manager\":\"0x"<<std::hex<<vehicle_manager<<std::dec<<'\"';
        std::uintptr_t header_manager{},header_backlink{};
        const bool header_closed=relationship&&read(process,vehicle,header_manager)&&header_manager>=0x10000&&
            read(process,header_manager+0x110,header_backlink)&&header_backlink==targeted_manager;
        sample<<",\"vehicle_header_manager_backlink_verified\":"<<(header_closed?"true":"false");
        if(header_closed)sample<<",\"vehicle_header_manager\":\"0x"<<std::hex<<header_manager<<std::dec<<'\"';
        if(relationship){
            std::uint32_t mode{},all{};std::array<std::uint32_t,3> spring{};
            if(!read(process,configuration+0x238,mode)||!read(process,configuration+0x23c,spring)||!read(process,vehicle+0x171c,all))
                throw std::runtime_error("Cannot read typed suspension parameters");
            sample<<",\"suspension_branch\":{\"mode\":"<<mode<<",\"require_all_contacts_word\":"<<all
                <<",\"stiffness_bits\":"<<spring[0]<<",\"damping_bits\":"<<spring[1]<<",\"rest_length_bits\":"<<spring[2]<<'}';
        }
        sample<<",\"owner_verified\":false,\"internal_tick_verified\":false}\n";
        sample.flush();if(!sample)throw std::runtime_error("Cannot write manager sample");
    }else scanned=scan(process,mb,[&](std::uintptr_t base,std::span<const std::byte> bytes){
        for(std::size_t i=0;i+sizeof(RigidState)<=bytes.size();i+=4){
            float xyz[3];std::memcpy(xyz,bytes.data()+i+0x24,12);
            if(!std::isfinite(xyz[0])||!std::isfinite(xyz[1])||!std::isfinite(xyz[2])||
               std::abs(xyz[0]-anchor.x)>2||std::abs(xyz[1]-anchor.y)>5||std::abs(xyz[2]-anchor.z)>2)continue;
            RigidState s;std::memcpy(&s,bytes.data()+i,sizeof(s));if(plausible(s)&&candidates.size()<512)candidates.insert(base+i);
        }
    });
    std::cout<<"RIGID_CANDIDATES="<<candidates.size()<<" scannedMB="<<scanned/1048576<<std::endl;
    if(candidates.empty())throw std::runtime_error("No coherent 0x58 rigid states near map start");
    std::ofstream manifest(std::string(argv[4])+".candidates.txt");manifest<<identity.process_id()<<'\n'<<executable_sha256<<'\n';
    for(auto address:candidates)manifest<<std::hex<<address<<'\n';manifest.close();if(!manifest)throw std::runtime_error("Cannot write candidates manifest");
    // Keep headers as hypotheses. Validate state index/alignment plus all
    // independent pointers used by the actual manager's accessors.
    std::ofstream links(std::string(argv[4])+".manager-hypotheses.csv");links<<"manager_candidate,states_base,state_index,state_address,models_array,model_address,id_map,angular_limit,owner_verified\n";
    std::set<std::pair<std::uintptr_t,std::uintptr_t>> seen;
    if(!targeted_manager)scan(process,mb,[&](std::uintptr_t base,std::span<const std::byte> bytes){
        for(std::size_t i=0;i+8<=bytes.size();i+=8){
            std::uintptr_t pointer{};std::memcpy(&pointer,bytes.data()+i,8);
            if(pointer<*candidates.begin()-0x58*1024||pointer>*candidates.rbegin()||(pointer&7))continue;
            auto hit=candidates.lower_bound(pointer);
            while(hit!=candidates.end()&&*hit-pointer<=0x58*1024&&(*hit-pointer)%0x58)++hit;
            if(hit==candidates.end()||*hit-pointer>0x58*1024)continue;
            const auto manager=base+i-0x70,index=(*hit-pointer)/0x58;
            std::uintptr_t models{},model{},ids{};float limit{};
            if(pointer<0x10000||!seen.emplace(manager,*hit).second||!read(process,manager+0x10,models)||
               !read(process,manager+0xb0,ids)||models<0x10000||ids<0x10000||
               !read(process,models+index*8,model)||model<0x10000||!read(process,model+0x4c,limit)||
               !std::isfinite(limit)||limit<0||limit>10000)continue;
            RigidState state;if(!read(process,*hit,state)||!plausible(state))continue;
            links<<"0x"<<std::hex<<manager<<",0x"<<pointer<<std::dec<<','<<index<<",0x"<<std::hex<<*hit<<",0x"<<models<<",0x"<<model<<",0x"<<ids<<std::dec<<','<<limit<<",false\n";
        }
    });links.close();if(!links)throw std::runtime_error("Cannot write manager hypotheses");
    std::unique_ptr<tm2020::live::LocalInput> input;
    if(pulse)input=std::make_unique<tm2020::live::LocalInput>(identity.process_id(),tm2020::live::InputBackend::Keyboard);
    std::ofstream trace(std::string(argv[4])+".csv");trace<<"wall_s,state_address,valid,command_gas,x,y,z,vx,vy,vz,wx,wy,wz,qw,qx,qy,qz,owner_verified\n"<<std::setprecision(9);
    std::ofstream wheels;
    if(targeted_manager){
        wheels.open(std::string(argv[4])+".wheels.csv");wheels<<"wall_s,vehicle,wheel,valid";
        for(unsigned off=0;off<0xb8;off+=4)wheels<<",bits_"<<std::hex<<off<<std::dec;wheels<<'\n'<<std::setprecision(9);
        if(!wheels)throw std::runtime_error("Cannot open wheel trace");
    }
    using Clock=std::chrono::steady_clock;const auto start=Clock::now();std::size_t valid{};
    for(std::size_t step=0;step<300;step++){
        const double elapsed=std::chrono::duration<double>(Clock::now()-start).count();const double gas=pulse&&elapsed>=.5&&elapsed<1.5?1.:0.;
        if(input)input->apply({0,gas,0});
        if(targeted_manager){
            std::uintptr_t users{},ids{},vehicle{};std::uint32_t index{},id{},mapped{};
            const bool linked=read(process,targeted_manager+0xb0,ids)&&read(process,ids,index)&&index<=1024&&
                read(process,targeted_manager+0x40,users)&&read(process,users+index*16+8,vehicle)&&vehicle>=0x10000&&
                read(process,vehicle+0x10,id)&&id<1000000&&read(process,ids+id*4,mapped)&&mapped==index;
            for(unsigned k=0;k<4;k++){
                std::array<std::uint32_t,0xb8/4> record{};const bool ok=linked&&read(process,vehicle+0x1780+k*0xb8,record);
                wheels<<elapsed<<",0x"<<std::hex<<vehicle<<std::dec<<','<<k<<','<<ok;
                for(auto word:record)wheels<<','<<word;wheels<<'\n';
            }
        }
        for(auto address:candidates){
            RigidState s;const bool ok=read(process,address,s)&&plausible(s);valid+=ok;
            trace<<elapsed<<",0x"<<std::hex<<address<<std::dec<<','<<ok<<','<<gas;
            if(ok){for(const auto* v:{&s.position,&s.linear_velocity,&s.angular_velocity})for(float x:*v)trace<<','<<x;for(float x:s.quaternion)trace<<','<<x;}
            else trace<<",,,,,,,,,,,,,";
            trace<<",false\n";
        }
        std::this_thread::sleep_until(start+std::chrono::milliseconds((step+1)*10));
    }
    if(input){input->neutral();input->restart();}
    trace.flush();if(!trace)throw std::runtime_error("Cannot write rigid trace");
    if(wheels.is_open()){wheels.flush();if(!wheels)throw std::runtime_error("Cannot write wheel trace");}
    std::cout<<"PASS RIGID_LAYOUT_PROBE decoded="<<valid<<" state_bytes=88 process_write_access=false authoritative_owner_verified=false\n";
}catch(const std::exception& e){std::cerr<<"PHYSICS_PROBE_ERROR "<<e.what()<<'\n';return 1;}
