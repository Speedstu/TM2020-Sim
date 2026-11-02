// SHA-pinned, read-only capture of typed effective vehicle parameters.
#include "tm2020/read_only_live.hpp"
#include "tm2020/recovered_rigid.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <sstream>
using namespace tm2020::recovered;
struct ReadProcess {
 HANDLE h{};~ReadProcess(){if(h)CloseHandle(h);}
 template<class T>T get(std::uintptr_t address){T x{};SIZE_T got{};if(address<0x10000||!ReadProcessMemory(h,reinterpret_cast<void*>(address),&x,sizeof(x),&got)||got!=sizeof(x))throw std::runtime_error("Unreadable typed parameter");return x;}
};
void check(bool b,const char* s){if(!b)throw std::runtime_error(s);}
struct Curve {std::uint32_t flags{},pad{};std::uintptr_t points{};std::uint32_t count{},opaque_14{};};
struct Point {float x,y;};
void curve(std::ostream& out,ReadProcess& p,std::uintptr_t address){
 const auto c=p.get<Curve>(address);if(c.count>4096){std::cerr<<"CURVE_HEADER at=0x"<<std::hex<<address<<" points=0x"<<c.points<<std::dec<<" flags="<<c.flags<<" count="<<c.count<<" trailing_word="<<c.opaque_14<<"\n";throw std::runtime_error("Invalid curve extent");}std::vector<Point> points;for(std::uint32_t j=0;j<c.count;j++){const auto x=p.get<Point>(c.points+j*8);check(std::isfinite(x.x)&&std::isfinite(x.y)&&std::abs(x.x)<=1e6&&std::abs(x.y)<=1e6&&(points.empty()||x.x>points.back().x),"Invalid curve point");points.push_back(x);}
 const auto after=p.get<Curve>(address);check(std::memcmp(&c,&after,sizeof(c))==0,"Curve changed while copying");
 out<<"{\"flags\":"<<c.flags<<",\"count\":"<<c.count<<",\"points\":[";for(std::size_t j=0;j<points.size();j++){if(j)out<<',';std::array<std::uint32_t,2> bits{};std::memcpy(bits.data(),&points[j],8);out<<'['<<bits[0]<<','<<bits[1]<<']';}out<<"]}";
}
template<class C>void words(std::ostream& out,ReadProcess& p,std::uintptr_t address,const C& offsets){out<<'{';bool first=true;for(auto off:offsets){if(!first)out<<',';first=false;out<<'"'<<off<<"\":"<<p.get<std::uint32_t>(address+off);}out<<'}';}
int main(int argc,char** argv)try{
 check(argc==4,"Usage: capture manifest manager-address output.json");tm2020::live::ReadOnlyObserver identity(argv[1]);ReadProcess p{OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,identity.process_id())};check(p.h!=nullptr,"Cannot open read-only process");std::array<wchar_t,32768> image_path{};DWORD image_size=std::uint32_t(image_path.size());check(QueryFullProcessImageNameW(p.h,0,image_path.data(),&image_size)!=0&&tm2020::live::file_sha256(std::filesystem::path(std::wstring(image_path.data(),image_size)))==executable_sha256,"Unknown game build for typed vehicle layouts");const auto manager=std::stoull(argv[2],nullptr,0);
 const auto states=p.get<std::uintptr_t>(manager+0x70),models=p.get<std::uintptr_t>(manager+0x10),ids=p.get<std::uintptr_t>(manager+0xb0),users=p.get<std::uintptr_t>(manager+0x40);const auto index=p.get<std::uint32_t>(ids);check(index<4096,"Bad mapped index");const auto model=p.get<std::uintptr_t>(models+index*8),vehicle=p.get<std::uintptr_t>(users+index*16+8);const auto id=p.get<std::uint32_t>(vehicle+0x10);check(id<1000000&&p.get<std::uint32_t>(ids+id*4)==index,"Vehicle ID does not round trip");const auto config=p.get<std::uintptr_t>(vehicle+0x88),vm=p.get<std::uintptr_t>(vehicle);
 for(unsigned offset:{0x10u,0x20u,0x30u,0x40u,0x50u,0x60u,0x70u,0x80u})check(index<p.get<std::uint32_t>(manager+offset+8),"Mapped item exceeds live span count");
 const auto state=p.get<RigidState>(states+index*0x58);float qnorm{};for(float x:state.quaternion)qnorm+=x*x;check(std::abs(qnorm-1)<.001f,"Bad rigid state quaternion");std::array<float,9> expected{};quaternion_to_matrix(expected,state.quaternion);for(std::size_t k=0;k<9;k++)check(std::abs(expected[k]-state.rotation[k])<.001f,"Bad rigid state rotation");
 HANDLE snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,identity.process_id());check(snapshot!=INVALID_HANDLE_VALUE,"Cannot inspect main module");MODULEENTRY32W entry{};entry.dwSize=sizeof(entry);check(Module32FirstW(snapshot,&entry)!=0,"Cannot inspect module base");check(_wcsicmp(entry.szModule,L"Trackmania.exe")==0,"Unexpected main module");const auto base=reinterpret_cast<std::uintptr_t>(entry.modBaseAddr);CloseHandle(snapshot);
 const auto items=p.get<std::uintptr_t>(manager+0x20),item=items+index*0x38;
 const auto force_context=p.get<std::uintptr_t>(item+0x10),force_callback=p.get<std::uintptr_t>(item+0x20);
 check(force_callback==base+0x8427d0&&p.get<std::uintptr_t>(force_context+0x110)==manager,"Force callback context does not round trip");
 const auto vehicle_list=p.get<std::uintptr_t>(force_context+0x48);const auto vehicle_count=p.get<std::uint32_t>(force_context+0x50);
 check(vehicle_count>0&&vehicle_count<=4096,"Invalid force context vehicle list");bool member=false;
 for(std::uint32_t j=0;j<vehicle_count;j++)member=member||p.get<std::uintptr_t>(vehicle_list+j*8)==vehicle;
 check(member,"Vehicle absent from force context list");
 std::ostringstream out;out<<std::setprecision(9)<<"{\"schema\":\"tm2020_effective_vehicle_parameters_v1\",\"sha256\":\""<<executable_sha256<<"\",\"pid\":"<<identity.process_id()<<",\"readOnly\":true,\"managerVehicleIdRoundtrip\":true,\"authoritativeOwnerVerified\":false,\"internalTickVerified\":false,\"scalarMathDispatchFlag\":"<<p.get<std::uint32_t>(base+0x1f840e4)<<",\"material14Remap\":"<<p.get<std::uint32_t>(base+0x1faa04c);
 out<<",\"forceCallbackContextVerified\":true,\"forceContextDynaBacklinkVerified\":true,\"forceContextVehicleMembershipVerified\":true,\"forceCallbackRva\":\"0x8427d0\",\"forceContextVehicleCount\":"<<vehicle_count;
 out<<",\"solverConfigurationWords\":";std::array<unsigned,11> solver{};for(unsigned j=0;j<11;j++)solver[j]=j*4;words(out,p,base+0x1ebcd10,solver);
 out<<",\"vehicleManagerBacklink\":"<<(p.get<std::uintptr_t>(vm+0x110)==manager?"true":"false");
 out<<",\"positionConfigurationWords\":";words(out,p,base+0x1ebcd50,std::array<unsigned,3>{0,4,8});
 out<<",\"persistentGravityWords\":";words(out,p,manager+0x25c,std::array<unsigned,3>{0,4,8});
 const auto shape=p.get<std::uintptr_t>(p.get<std::uintptr_t>(manager+0x50)+index*8);
 out<<",\"bodyActivationSnapshot\":{\"sourceFlags\":"<<unsigned(p.get<std::uint8_t>(p.get<std::uintptr_t>(manager+0x30)+index))<<",\"itemFlags\":"<<p.get<std::uint32_t>(item+4)<<",\"massOffsetBits\":"<<p.get<std::uint32_t>(item+8)<<",\"gravityMultiplierBits\":"<<p.get<std::uint32_t>(item+12)<<",\"shapePresent\":"<<(shape?"true":"false")<<",\"shapeTag11\":"<<(shape?unsigned(p.get<std::uint8_t>(shape+0x11)):0)<<",\"sleepWord4\":"<<p.get<std::uint16_t>(p.get<std::uintptr_t>(manager+0x60)+index*8+4)<<",\"atomicPhysicsStageSnapshot\":false}";
 out<<",\"managerAuxiliary80Words\":";words(out,p,p.get<std::uintptr_t>(manager+0x80)+index*16,std::array<unsigned,4>{0,4,8,12});
 out<<",\"modelWords\":";std::array<unsigned,24> mw{};for(unsigned j=0;j<mw.size();j++)mw[j]=j*4;words(out,p,model,mw);
 out<<",\"configurationWords\":";const std::array<unsigned,42> offsets{0x238,0x23c,0x240,0x244,0x248,0x24c,0x250,0x258,0x324,0x328,0xcd4,0xd90,0xd94,0xd98,0x118c,0x1190,0x1538,0x153c,0x1540,0x1790,0x1808,0x180c,0x17a8,0x17ac,0x18d0,0x1928,0x192c,0x1a48,0x1ce0,0x1ce8,0x1cec,0x1cf0,0x1cf8,0x1d58,0x1d5c,0x1e84,0x1e8c,0x1ef4,0x1efc,0x1f00,0x1f04,0x1f08};words(out,p,config,offsets);
 out<<",\"configurationCurves\":{";const std::array<unsigned,12> co{0x638,0x9a8,0x9f8,0xcf0,0xd40,0x1548,0x17b8,0x18d8,0x19f8,0x1c90,0x1e90,0x2060};for(std::size_t j=0;j<co.size();j++){if(j)out<<',';out<<'"'<<co[j]<<"\":";curve(out,p,config+co[j]);}out<<'}';
 out<<",\"verticalThresholdWords\":";words(out,p,config,std::array<unsigned,4>{0x19e4,0x19e8,0x19ec,0x19f0});
 out<<",\"materials\":[";for(unsigned k=0;k<80;k++){const auto material=p.get<std::uintptr_t>(vm+0x6b8+k*8);check(material>=0x10000,"Missing material record");if(k)out<<',';out<<"{\"id\":"<<k<<",\"words\":";std::array<unsigned,15> mo{};for(unsigned j=0;j<mo.size();j++)mo[j]=0x18+j*4;words(out,p,material,mo);out<<",\"curves\":{";const std::array<unsigned,5> mc{0x88,0xd8,0x128,0x178,0x1c8};for(std::size_t j=0;j<mc.size();j++){if(j)out<<',';out<<'"'<<mc[j]<<"\":";curve(out,p,material+mc[j]);}out<<"}}";}out<<']';
 out<<",\"wheelModelWords\":[";for(unsigned k=0;k<4;k++){if(k)out<<',';const auto wm=p.get<std::uintptr_t>(vehicle+0x388+k*8);words(out,p,wm,std::array<unsigned,8>{0,4,8,0xc,0x10,0x14,0x18,0x28});}out<<']';
 check(p.get<std::uintptr_t>(manager+0x20)==items&&p.get<std::uintptr_t>(item+0x10)==force_context&&p.get<std::uintptr_t>(item+0x20)==force_callback&&p.get<std::uintptr_t>(force_context+0x110)==manager&&p.get<std::uintptr_t>(force_context+0x48)==vehicle_list&&p.get<std::uint32_t>(force_context+0x50)==vehicle_count,"Force context binding changed during capture");
 check(p.get<std::uintptr_t>(vehicle+0x88)==config&&p.get<std::uintptr_t>(users+index*16+8)==vehicle,"Vehicle binding changed during capture");out<<",\"bindingStableDuringCapture\":true,\"completeVehiclePhysics\":false}\n";std::ofstream destination(argv[3]);destination<<out.str();destination.flush();check(bool(destination),"Cannot write effective parameters");std::cout<<"PASS EFFECTIVE_PARAMETERS materials=80 curves=412 read_only=true live_owner_unqualified=true\n";
}catch(const std::exception& e){std::cerr<<"PARAMETER_CAPTURE_ERROR "<<e.what()<<'\n';return 1;}
