// Locate typed physics bindings after restart, using the pinned callback and
// independent manager/item/vehicle backlinks. No UI, input or process writes.
#include "tm2020/read_only_live.hpp"
#include "tm2020/recovered_rigid.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <vector>
using namespace tm2020::recovered;
void check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Handle {
    HANDLE value{};
    explicit Handle(HANDLE h):value(h){}
    ~Handle(){if(value&&value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
};
template<class T>bool read(HANDLE p,std::uint64_t at,T& value){
    SIZE_T got{};
    return at>=0x10000 && ReadProcessMemory(p,reinterpret_cast<void*>(at),&value,sizeof(value),&got)
           &&got==sizeof(value);
}
std::uint64_t creation(HANDLE p){
    FILETIME a{},b{},c{},d{};check(GetProcessTimes(p,&a,&b,&c,&d)!=0,"Cannot read process identity");
    return (std::uint64_t(a.dwHighDateTime)<<32)|a.dwLowDateTime;
}
struct Binding {std::uint64_t manager,vehicle,config,state;std::uint32_t index,id;RigidState rigid;};
bool binding(HANDLE p,std::uint64_t callback,std::uint64_t hit,Binding& out,unsigned* reached=nullptr){
    const auto stage=[&](unsigned n){if(reached)*reached=n;};stage(0);
    if(hit<0x20)return false;
    const auto item=hit-0x20;
    std::uint64_t owner{},manager{},items{},users{},ids{},states{},models{},config{},vehicle{},back{},model{};
    std::uint32_t count{},index{},id{},mapped{};
    if(!read(p,item+0x10,owner)||!read(p,owner+0x110,manager))return false;
    stage(1);
    if(!read(p,manager+0x20,items)||!read(p,manager+0x28,count)||count==0||count>4096
       ||item<items||(item-items)%56!=0)return false;
    const auto wide=(item-items)/56;
    if(wide>=count)return false;
    index=static_cast<std::uint32_t>(wide);
    stage(2);
    if(!read(p,manager+0x40,users)||!read(p,manager+0xb0,ids)
       ||!read(p,users+index*16+8,vehicle)||!read(p,vehicle+0x10,id)||id>=1000000
       ||!read(p,ids+id*4,mapped)||mapped!=index)return false;
    stage(3);
    // The vehicle header and the registered force context are distinct objects.
    // Validate membership through the force context's actual vehicle span.
    std::uint64_t vehicle_list{};std::uint32_t vehicle_count{};
    if(!read(p,owner+0x48,vehicle_list)||!read(p,owner+0x50,vehicle_count)
       ||vehicle_count==0||vehicle_count>4096)return false;
    bool member=false;
    for(std::uint32_t j=0;j<vehicle_count;++j){
        std::uint64_t value{};
        if(!read(p,vehicle_list+j*8,value))return false;
        member=member||value==vehicle;
    }
    if(!member||!read(p,vehicle+0x88,config)||config<0x10000
       ||!read(p,item+0x20,back)||back!=callback)return false;
    stage(4);
    for(const unsigned offset:{0x10u,0x20u,0x30u,0x40u,0x50u,0x60u,0x70u,0x80u}){
        std::uint64_t pointer{};std::uint32_t n{};
        if(!read(p,manager+offset,pointer)||pointer<0x10000||!read(p,manager+offset+8,n)
           ||n<=index||n>1000000)return false;
    }
    stage(5);
    if(!read(p,manager+0x70,states)||!read(p,manager+0x10,models)
       ||!read(p,models+index*8,model)||model<0x10000)return false;
    RigidState rigid{};
    const auto state=states+index*88;
    if(!read(p,state,rigid))return false;
    stage(6);
    float norm{};
    for(float q:rigid.quaternion){if(!std::isfinite(q))return false;norm+=q*q;}
    if(std::abs(norm-1.f)>.001f)return false;
    std::array<float,9> matrix{};quaternion_to_matrix(matrix,rigid.quaternion);
    for(unsigned j=0;j<9;++j)if(!std::isfinite(rigid.rotation[j])||std::abs(matrix[j]-rigid.rotation[j])>.001f)return false;
    for(const auto* v:{&rigid.position,&rigid.linear_velocity,&rigid.angular_velocity})
        for(float x:*v)if(!std::isfinite(x)||std::abs(x)>100000.f)return false;
    std::uint32_t variant{};
    if(!read(p,config+0x1790,variant)||variant>32)return false;
    stage(7);
    out={manager,vehicle,config,state,index,id,rigid};return true;
}
std::string hex(std::uint64_t x){std::ostringstream o;o<<"0x"<<std::hex<<x;return o.str();}
struct ServiceSlots {std::uint32_t dyna{},collision{},vehicle{};};
struct SceneRoot {std::uint64_t address{},context{},entity_list{},parameter_object{},scene_manager{};
                  std::uint32_t entities{},parameter_flags{};};
bool registry(HANDLE p,const Binding& b,const ServiceSlots& slots,std::uint64_t context){
    if(context<0x10000||context%8||slots.dyna>=4096||slots.collision>=4096||slots.vehicle>=4096
       ||slots.dyna==slots.collision||slots.dyna==slots.vehicle||slots.collision==slots.vehicle)return false;
    std::uint64_t dyna{},collision{},owner{},items{},expected_collision{},expected_owner{};
    return read(p,context+0x10+slots.dyna*8,dyna)&&dyna==b.manager
        &&read(p,b.manager,expected_collision)&&expected_collision>=0x10000
        &&read(p,b.manager+0x20,items)&&read(p,items+b.index*56+0x10,expected_owner)
        &&read(p,context+0x10+slots.collision*8,collision)&&collision==expected_collision
        &&read(p,context+0x10+slots.vehicle*8,owner)&&owner==expected_owner;
}
bool scene_root(HANDLE p,const Binding& b,const ServiceSlots& slots,std::uint64_t context,
                std::uint64_t scene,std::uint64_t module_begin,std::uint64_t module_size,SceneRoot& out){
    if(scene<0x10000||scene%8||!registry(p,b,slots,context))return false;
    std::uint64_t linked{},vtable{},first{},list{},params{},scene_manager{},last{};
    std::uint32_t count{},flags{};
    if(!read(p,scene+0x7c8,linked)||linked!=context||!read(p,scene,vtable)
       ||vtable<module_begin||vtable-module_begin>=module_size||!read(p,vtable,first)
       ||first<module_begin||first-module_begin>=module_size
       ||!read(p,scene+0x660,list)||list<0x10000||!read(p,scene+0x668,count)||!count||count>4096
       ||!read(p,list+(count-1)*8,last)||last<0x10000
       ||!read(p,scene+0x968,params)||params<0x10000||!read(p,params+0x34,flags)
       ||!read(p,scene+0x7d0,scene_manager)||scene_manager<0x10000)return false;
    out={scene,context,list,params,scene_manager,count,flags};return true;
}
template<class Visit>std::uint64_t scan_private_words(HANDLE p,std::uint64_t limit,Visit visit){
    constexpr std::size_t chunk=1<<20,overlap=64;
    std::vector<std::byte> bytes(chunk+overlap);
    std::uint64_t scanned{},address=0x10000;MEMORY_BASIC_INFORMATION region{};
    while(scanned<limit*1048576&&VirtualQueryEx(p,reinterpret_cast<void*>(address),&region,sizeof(region))==sizeof(region)){
        const auto start=reinterpret_cast<std::uint64_t>(region.BaseAddress),end=start+region.RegionSize;
        if(end<=address)break;address=end;const auto protect=region.Protect&255;
        if(region.State!=MEM_COMMIT||region.Type!=MEM_PRIVATE||(region.Protect&(PAGE_GUARD|PAGE_NOACCESS))
           ||(protect!=PAGE_READWRITE&&protect!=PAGE_WRITECOPY))continue;
        for(auto at=start;at<end&&scanned<limit*1048576;){
            const auto count=std::min<std::uint64_t>({bytes.size(),end-at,limit*1048576-scanned});SIZE_T got{};
            if(ReadProcessMemory(p,reinterpret_cast<void*>(at),bytes.data(),count,&got))
                for(std::size_t j=0;j+8<=got;j+=8){std::uint64_t value{};
                    std::memcpy(&value,bytes.data()+j,8);visit(at+j,value);}
            scanned+=count;at+=count>overlap?count-overlap:count;
        }
    }
    return scanned;
}
ServiceSlots service_slots(HANDLE p,std::uint64_t base){
    struct Getter{std::uint32_t entry,word;std::array<unsigned char,7> bytes;};
    constexpr std::array<Getter,3> getters{{
        {0x7ba440,0x2053b84,{0x8b,0x05,0x3e,0x97,0x89,0x01,0xc3}},
        {0x6c4380,0x202ddbc,{0x8b,0x05,0x36,0x9a,0x96,0x01,0xc3}},
        {0x7c5d20,0x2053bf4,{0x8b,0x05,0xce,0xde,0x88,0x01,0xc3}}}};
    constexpr std::array<unsigned char,8> lookup{0x8b,0xc2,0x48,0x8b,0x44,0xc1,0x10,0xc3};
    std::array<unsigned char,8> actual{};
    check(read(p,base+0x6c26a0,actual)&&actual==lookup,"Context lookup instructions differ");
    std::array<std::uint32_t,3> values{};
    for(unsigned i=0;i<getters.size();++i){std::array<unsigned char,7> raw{};
        check(read(p,base+getters[i].entry,raw)&&raw==getters[i].bytes,"Service getter instructions differ");
        check(read(p,base+getters[i].word,values[i])&&values[i]<4096,"Uninitialized service registry index");}
    check(values[0]!=values[1]&&values[0]!=values[2]&&values[1]!=values[2],"Aliased service registry indices");
    return {values[0],values[1],values[2]};
}
template<class T,std::size_t N>void put(std::array<std::byte,N>& bytes,std::size_t at,const T& v){
    check(at+sizeof(v)<=N,"Owned fixture extent");std::memcpy(bytes.data()+at,&v,sizeof(v));
}
int selftest(){
    std::array<std::byte,0x200> manager{},owner{};
    std::array<std::byte,0x2000> vehicle{};std::array<std::byte,0x1800> config{};
    std::array<std::byte,56> item{};std::array<std::byte,16> users{};
    std::array<std::uint64_t,1> models{},vehicles{};std::array<std::uint32_t,3> ids{};
    std::array<std::byte,16> auxiliary{};std::array<RigidState,1> states{};
    const auto ptr=[](const auto& v){return reinterpret_cast<std::uint64_t>(v.data());};
    const auto callback=reinterpret_cast<std::uint64_t>(&selftest);
    models[0]=ptr(config);
    for(auto offset:{0x10u,0x20u,0x30u,0x40u,0x50u,0x60u,0x70u,0x80u}){
        put(manager,offset,ptr(auxiliary));put(manager,offset+8,std::uint32_t(1));
    }
    put(manager,0x10,ptr(models));put(manager,0x20,ptr(item));put(manager,0x40,ptr(users));
    put(manager,0x70,ptr(states));put(manager,0xb0,ptr(ids));
    put(owner,0x110,ptr(manager));put(vehicle,0,ptr(owner));put(vehicle,0x10,std::uint32_t(0));
    vehicles[0]=ptr(vehicle);put(owner,0x48,ptr(vehicles));put(owner,0x50,std::uint32_t(1));
    put(vehicle,0x88,ptr(config));put(item,0x10,ptr(owner));put(item,0x20,callback);
    put(users,8,ptr(vehicle));Binding result{};unsigned rejected{};
    const auto verify=[&](){return binding(GetCurrentProcess(),callback,ptr(item)+0x20,result);};
    check(verify()&&result.manager==ptr(manager)&&result.vehicle==ptr(vehicle),"Owned binding was not discovered");
    put(owner,0x110,std::uint64_t(0));check(!verify(),"Broken owner accepted");++rejected;put(owner,0x110,ptr(manager));
    put(manager,0x78,std::uint32_t(0));check(!verify(),"Empty state span accepted");++rejected;put(manager,0x78,std::uint32_t(1));
    ids[0]=1;check(!verify(),"Wrong primary ID accepted");++rejected;ids[0]=0;
    put(item,0x20,std::uint64_t(0));check(!verify(),"Wrong callback accepted");++rejected;put(item,0x20,callback);
    states[0].rotation[0]=0;check(!verify(),"Incoherent rotation accepted");++rejected;states[0].rotation[0]=1;
    put(config,0x1790,std::uint32_t(100));check(!verify(),"Invalid variant accepted");++rejected;put(config,0x1790,std::uint32_t(0));
    vehicles[0]=0;check(!verify(),"Vehicle absent from force context accepted");++rejected;vehicles[0]=ptr(vehicle);
    check(verify(),"Restored owned binding rejected");
    put(vehicle,0x10,std::uint32_t(2));ids[0]=42;ids[2]=0;
    check(verify()&&result.id==2,"Nonzero item ID incorrectly depends on ID zero");
    std::array<std::uint64_t,64> context{},vtable{},entities{};
    std::array<std::byte,0xb00> scene{},params{};
    const ServiceSlots slots{3,5,7};const auto context_at=ptr(context);
    context[2+slots.dyna]=ptr(manager);context[2+slots.collision]=ptr(auxiliary);
    context[2+slots.vehicle]=ptr(owner);put(manager,0,ptr(auxiliary));
    check(registry(GetCurrentProcess(),result,slots,context_at),"Owned registry rejected");
    context[2+slots.vehicle]=ptr(manager);check(!registry(GetCurrentProcess(),result,slots,context_at),"Wrong force service accepted");
    context[2+slots.vehicle]=ptr(owner);
    check(!registry(GetCurrentProcess(),result,{3,3,7},context_at),"Aliased services accepted");
    vtable[0]=ptr(vtable);entities[0]=ptr(vehicle);
    put(scene,0,ptr(vtable));put(scene,0x7c8,context_at);put(scene,0x7d0,ptr(owner));
    put(scene,0x660,ptr(entities));put(scene,0x668,std::uint32_t(1));put(scene,0x968,ptr(params));
    SceneRoot root{};
    const auto valid_root=[&](){return scene_root(GetCurrentProcess(),result,slots,context_at,
        ptr(scene),ptr(vtable),sizeof(vtable),root);};
    check(valid_root(),"Owned scene registry root rejected");
    put(scene,0x7c8,std::uint64_t(0));check(!valid_root(),"Foreign scene context accepted");put(scene,0x7c8,context_at);
    put(scene,0x668,std::uint32_t(4097));check(!valid_root(),"Scene entity bound ignored");put(scene,0x668,std::uint32_t(1));
    put(scene,0,std::uint64_t(0));check(!valid_root(),"Nonimage scene vtable accepted");put(scene,0,ptr(vtable));
    check(valid_root(),"Restored scene root rejected");
    std::cout<<"PASS OWNED_BINDING_DISCOVERY valid_roundtrip=true broken_bindings_rejected="<<rejected
             <<" registry_and_scene_graph=true game_process_accessed=false\n";
    return 0;
}
int main(int argc,char**argv)try{
    if(argc==2&&std::string(argv[1])=="--self-test")return selftest();
    const bool rebind=argc==5&&std::string(argv[1])=="--rebind-scene";
    const bool include_scene=rebind||(argc>=2&&std::string(argv[1])=="--discover-scene");
    check((argc==4||argc==5)&&(std::string(argv[1])=="--discover"||include_scene),
          "Usage: manager_discovery --discover[-scene] original.exe output.json [scanMB]");
    const std::filesystem::path exe=std::filesystem::canonical(argv[2]),output=argv[3];
    check(!std::filesystem::exists(output),"Discovery never overwrites a report");
    check(tm2020::live::file_sha256(exe)==executable_sha256,"Unknown game build");
    const auto limit=argc==5&&!rebind?std::stoull(argv[4]):4096;
    check(limit>=64&&limit<=16384,"Scan bound must be 64..16384 MiB");
    Handle processes(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
    PROCESSENTRY32W entry{};entry.dwSize=sizeof(entry);
    check(Process32FirstW(processes.value,&entry)!=0,"Cannot enumerate processes");
    DWORD pid{};unsigned matches{};
    do{if(_wcsicmp(entry.szExeFile,L"Trackmania.exe")==0){pid=entry.th32ProcessID;++matches;}}
    while(Process32NextW(processes.value,&entry));
    check(matches==1,"Need exactly one running game");
    Handle process(OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid));
    check(process.value!=nullptr,"Cannot open read-only game handle");
    const auto created=creation(process.value);
    std::array<wchar_t,32768> name{};DWORD size=DWORD(name.size());
    check(QueryFullProcessImageNameW(process.value,0,name.data(),&size)!=0,"Cannot identify game path");
    check(std::filesystem::equivalent(exe,std::filesystem::path(std::wstring(name.data(),size))),"Wrong process path");
    Handle modules(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid));
    MODULEENTRY32W module{};module.dwSize=sizeof(module);
    check(Module32FirstW(modules.value,&module)!=0&&_wcsicmp(module.szModule,L"Trackmania.exe")==0,"Cannot identify main module");
    const auto base=reinterpret_cast<std::uint64_t>(module.modBaseAddr),callback=base+0x8427d0;
    constexpr std::size_t chunk=1<<20,overlap=64;
    std::vector<std::byte> bytes(chunk+overlap);
    std::set<std::uint64_t> seen;std::vector<Binding> found;
    std::array<std::uint64_t,8> stages{};
    std::uint64_t hinted_scene{},hinted_registry{},hinted_manager{};
    if(rebind){
        std::ifstream in(argv[4]);std::string line;
        auto get=[&](){check(bool(std::getline(in,line)),"Truncated scene rebind target");return line;};
        check(get()=="TM2020_SCENE_STAGE_TARGET_V1","Unsupported scene rebind target");
        check(std::stoul(get())==pid&&std::stoull(get())==created,"Rebind source process identity differs");
        check(get()==executable_sha256&&std::stoull(get(),nullptr,0)==base,"Rebind source image differs");
        hinted_scene=std::stoull(get(),nullptr,0);hinted_registry=std::stoull(get(),nullptr,0);
        hinted_manager=std::stoull(get(),nullptr,0);
        std::uint64_t items{};std::uint32_t count{};
        check(read(process.value,hinted_manager+0x20,items)&&read(process.value,hinted_manager+0x28,count)
            &&count>0&&count<=4096,"Hinted manager has no bounded active item span");
        for(std::uint32_t i=0;i<count;++i){Binding candidate{};
            if(binding(process.value,callback,items+i*56+0x20,candidate)&&candidate.manager==hinted_manager){
                found.push_back(candidate);break;}}
        check(found.size()==1,"Current scene vehicle binding is invalid");
    }
    std::uint64_t scanned{},address=0x10000;MEMORY_BASIC_INFORMATION region{};
    while(!rebind&&scanned<limit*1048576 && VirtualQueryEx(process.value,reinterpret_cast<void*>(address),&region,sizeof(region))==sizeof(region)){
        const auto start=reinterpret_cast<std::uint64_t>(region.BaseAddress),end=start+region.RegionSize;
        if(end<=address)break;
        address=end;
        const auto protect=region.Protect&255;
        if(region.State!=MEM_COMMIT||region.Type!=MEM_PRIVATE||(region.Protect&(PAGE_GUARD|PAGE_NOACCESS))
           ||(protect!=PAGE_READWRITE&&protect!=PAGE_WRITECOPY))continue;
        for(auto at=start;at<end&&scanned<limit*1048576;){
            const auto count=std::min<std::uint64_t>({bytes.size(),end-at,limit*1048576-scanned});SIZE_T got{};
            if(ReadProcessMemory(process.value,reinterpret_cast<void*>(at),bytes.data(),count,&got)){
                for(std::size_t j=0;j+8<=got;j+=8){
                    std::uint64_t pointer{};std::memcpy(&pointer,bytes.data()+j,8);
                    if(pointer!=callback)continue;
                    Binding candidate{};unsigned reached{};
                    const bool valid=binding(process.value,callback,at+j,candidate,&reached);
                    ++stages.at(reached);
                    if(valid&&seen.insert(candidate.manager).second){
                        check(found.size()<64,"Too many typed bindings");found.push_back(candidate);
                    }
                }
            }
            scanned+=count;at+=count>overlap?count-overlap:count;
        }
    }
    check(creation(process.value)==created,"Process identity changed during discovery");
    for(const auto& b:found){
        std::uint64_t items{};Binding again{};
        check(read(process.value,b.manager+0x20,items)&&binding(process.value,callback,items+b.index*56+0x20,again)
              &&again.vehicle==b.vehicle&&again.config==b.config,"Binding changed during discovery");
    }
    ServiceSlots slots{};std::vector<std::pair<std::size_t,std::uint64_t>> contexts;
    std::vector<std::pair<std::size_t,SceneRoot>> scenes;
    std::uint64_t context_scanned{},scene_scanned{};
    if(include_scene){
        slots=service_slots(process.value,base);
        std::cout<<"PHYSICS_BINDING_SCAN candidates="<<found.size()<<" bytes="<<scanned<<std::endl;
        std::set<std::pair<std::size_t,std::uint64_t>> seen_contexts,seen_scenes;
        if(rebind){SceneRoot root{};
            check(scene_root(process.value,found[0],slots,hinted_registry,hinted_scene,base,module.modBaseSize,root),
                "Hinted scene services/root failed current typed validation");
            contexts.emplace_back(0,hinted_registry);scenes.emplace_back(0,root);}
        if(!rebind&&!found.empty())context_scanned=scan_private_words(process.value,limit,[&](auto at,auto value){
            for(std::size_t j=0;j<found.size();++j){const auto offset=0x10+std::uint64_t(slots.dyna)*8;
                if(value==found[j].manager&&at>=offset){const auto candidate=at-offset;
                    if(registry(process.value,found[j],slots,candidate)&&seen_contexts.emplace(j,candidate).second){
                        check(contexts.size()<64,"Context candidate bound");contexts.emplace_back(j,candidate);}}}
        });
        std::cout<<"CONTEXT_REGISTRY_SCAN candidates="<<contexts.size()<<" bytes="<<context_scanned<<std::endl;
        if(!rebind&&!contexts.empty())scene_scanned=scan_private_words(process.value,limit,[&](auto at,auto value){
            for(const auto& [j,context]:contexts){SceneRoot root{};
                if(value==context&&at>=0x7c8&&scene_root(process.value,found[j],slots,context,at-0x7c8,base,module.modBaseSize,root)
                   &&seen_scenes.emplace(j,root.address).second){check(scenes.size()<64,"Scene candidate bound");scenes.emplace_back(j,root);}}
        });
        const auto again=service_slots(process.value,base);
        check(again.dyna==slots.dyna&&again.collision==slots.collision&&again.vehicle==slots.vehicle
              &&creation(process.value)==created,"Service identity changed during discovery");
        for(const auto& [j,context]:contexts)check(registry(process.value,found[j],slots,context),"Context graph changed");
        for(const auto& [j,s]:scenes){SceneRoot again_root{};
            check(scene_root(process.value,found[j],slots,s.context,s.address,base,module.modBaseSize,again_root),"Scene graph changed");}
    }
    std::ofstream report(output);check(bool(report),"Cannot write discovery report");
    report<<std::setprecision(9)<<"{\"schema\":\"tm2020_readonly_physics_binding_v1\",\"pid\":"<<pid
          <<",\"processCreationFiletime\":"<<std::quoted(std::to_string(created))
          <<",\"executableSha256\":\""<<executable_sha256<<"\",\"moduleBase\":"<<std::quoted(hex(base))
          <<",\"readOnly\":true,\"authoritativePlayerOwnerVerified\":false,\"typedSceneHintsRevalidated\":"<<(rebind?"true":"false")
          <<",\"scannedBytes\":"<<scanned<<",\"candidates\":[";
    for(std::size_t j=0;j<found.size();++j){const auto& b=found[j];if(j)report<<',';
        report<<"{\"manager\":"<<std::quoted(hex(b.manager))<<",\"vehicle\":"<<std::quoted(hex(b.vehicle))
              <<",\"configuration\":"<<std::quoted(hex(b.config))<<",\"rigidState\":"<<std::quoted(hex(b.state))
              <<",\"bodyIndex\":"<<b.index<<",\"itemId\":"<<b.id<<",\"position\":["<<b.rigid.position[0]
              <<','<<b.rigid.position[1]<<','<<b.rigid.position[2]<<"],\"typedBacklinksRechecked\":true}";
    }
    report<<"],\"candidateStages\":[";
    for(unsigned j=0;j<stages.size();++j){if(j)report<<',';report<<stages[j];}
    report<<"]";
    if(include_scene){
        report<<",\"sceneRegistryDiscovery\":{\"schema\":\"tm2020_readonly_scene_registry_v1\",\"serviceGetterInstructionsVerified\":true"
              <<",\"dynaSlot\":"<<slots.dyna<<",\"collisionSlot\":"<<slots.collision<<",\"vehicleSlot\":"<<slots.vehicle
              <<",\"contextScannedBytes\":"<<context_scanned<<",\"sceneScannedBytes\":"<<scene_scanned
              <<",\"atomicSnapshot\":false,\"completeSceneQualified\":false,\"registries\":[";
        for(std::size_t i=0;i<contexts.size();++i){if(i)report<<',';
            report<<"{\"bindingIndex\":"<<contexts[i].first<<",\"address\":"<<std::quoted(hex(contexts[i].second))<<'}';}
        report<<"],\"sceneRoots\":[";
        for(std::size_t i=0;i<scenes.size();++i){if(i)report<<',';const auto& [j,s]=scenes[i];
            report<<"{\"bindingIndex\":"<<j<<",\"address\":"<<std::quoted(hex(s.address))
                  <<",\"registry\":"<<std::quoted(hex(s.context))<<",\"entityList\":"<<std::quoted(hex(s.entity_list))
                  <<",\"entityCount\":"<<s.entities<<",\"parameters\":"<<std::quoted(hex(s.parameter_object))
                  <<",\"sceneManager\":"<<std::quoted(hex(s.scene_manager))<<",\"parameterFlags\":"<<s.parameter_flags<<'}';}
        report<<"]}";
    }
    report<<"}\n";report.flush();check(bool(report),"Cannot save discovery report");
    std::cout<<"PASS PHYSICS_BINDING_DISCOVERY candidates="<<found.size()<<" scannedMB="<<scanned/1048576
             <<" read_only=true authoritative_player=false\n";
    std::cout<<"BINDING_STAGES";for(auto n:stages)std::cout<<' '<<n;std::cout<<'\n';
    if(include_scene)std::cout<<"SCENE_REGISTRIES "<<contexts.size()<<" SCENE_ROOTS "<<scenes.size()<<" original_getters_verified=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
