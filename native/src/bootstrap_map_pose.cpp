// TM2020 C++20 OFFLINE LOCAL GAME POSE BOOTSTRAP.
// Converts an existing bounded numeric-only TMVEC snapshot and native TM map
// into a short-lived V3 pose candidate manifest. Runtime has no Python and
// never writes to the game process or hooks its code.
// Results remain *candidates* until moving/reset evidence identifies vehicle.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <wincrypt.h>
#include "tm2020.hpp"
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
#pragma pack(push,1)
struct SnapshotHead{
    char magic[8]{};
    uint32_t version{},entryBytes{};
    uint64_t pid{},scanned{},count{};
};
struct RawPosition{
    uint64_t address{};
    float xyz[3]{};
};
#pragma pack(pop)
static_assert(sizeof(SnapshotHead)==40 && sizeof(RawPosition)==20);
struct Owned {
    HANDLE h{};
    explicit Owned(HANDLE a):h(a){}
    ~Owned(){if(h&&h!=INVALID_HANDLE_VALUE)CloseHandle(h);}
    Owned(const Owned&)=delete;
};
struct Candidate {
    std::array<float,3> pos{};
    std::array<float,4> q{};
    std::vector<uintptr_t> slots;
    std::set<uintptr_t> distinctPages;
    double startError{};
};
static void check(bool okay,const char* msg){
    if(!okay)throw std::runtime_error(msg);
}
static std::string hex(uintptr_t a){
    std::ostringstream stream;
    stream<<"0x"<<std::hex<<a;
    return stream.str();
}
static std::string sha256(const fs::path& path){
    HCRYPTPROV prov{};
    HCRYPTHASH h{};
    check(CryptAcquireContextW(&prov,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)!=0,
          "SHA256 provider unavailable");
    try {
        check(CryptCreateHash(prov,CALG_SHA_256,0,0,&h)!=0,"SHA256 init failed");
        std::ifstream f(path,std::ios::binary);
        check(bool(f),"Cannot read target exe");
        std::array<char,1<<20> buf{};
        while(f){
            f.read(buf.data(),buf.size());
            const auto count=f.gcount();
            if(count>0)check(CryptHashData(h,reinterpret_cast<const BYTE*>(buf.data()),
                                         static_cast<DWORD>(count),0)!=0,"SHA256 streaming failed");
        }
        BYTE digest[32]{};
        DWORD n=32;
        check(CryptGetHashParam(h,HP_HASHVAL,digest,&n,0)!=0&&n==32,"SHA256 finalize failed");
        std::string result;
        const auto alphabet="0123456789abcdef";
        for(const auto a:digest){result+=alphabet[a>>4];result+=alphabet[a&15];}
        CryptDestroyHash(h);CryptReleaseContext(prov,0);
        return result;
    }catch(...){
        if(h)CryptDestroyHash(h);
        CryptReleaseContext(prov,0);
        throw;
    }
}
static tm2020::Vec3 authored_start(const tm2020::Map& map){
    const auto all=map.course_markers();
    std::vector<tm2020::Vec3> starts;
    for(const auto& marker:all)
        if(marker.kind==tm2020::CourseMarkerKind::Start)
            starts.push_back(marker.position);
    check(starts.size()==1,"Expected exactly one authored map start");
    check(std::isfinite(starts.front().x) && std::isfinite(starts.front().z),
          "Nonfinite map start position");
    return starts.front();
}
static bool valid_candidate(const std::array<float,3>& xyz,
                            const std::array<float,4>& q,
                            double centerX,double centerZ){
    const double distance=std::hypot(xyz[0]-centerX,xyz[2]-centerZ);
    if(!std::isfinite(distance)||distance>0.75||
       !std::isfinite(xyz[1])||xyz[1]<-50||xyz[1]>200) return false;
    double norm2=0;
    for(const auto a:q){
        if(!std::isfinite(a))return false;
        norm2+=double(a)*a;
    }
    return std::abs(norm2-1.)<0.003;
}
static std::array<float,4> canonical_quat(std::array<float,4> q){
    const auto where=std::max_element(q.begin(),q.end(),[](auto a,auto b){
        return std::abs(a)<std::abs(b);
    });
    if(*where<0)
        for(auto& a:q)a=-a;
    return q;
}
static std::string key(const std::array<float,3>& xyz,
                       const std::array<float,4>& q) {
    // Fixed quantization only to group independent-looking copies; not physics.
    std::ostringstream out;
    for(auto a:xyz)out<<std::lround(a*100.)<<',';
    for(auto a:q)out<<std::lround(a*100.)<<',';
    return out.str();
}
static int bootstrap(const fs::path& mapFile,const fs::path& snapshot,
                     const fs::path& output){
    const auto map=tm2020::Map::load(mapFile);
    const auto start=authored_start(map);
    std::ifstream input(snapshot,std::ios::binary);
    check(bool(input),"TMVEC bounded source snapshot unavailable");
    SnapshotHead head{};
    check(bool(input.read(reinterpret_cast<char*>(&head),sizeof head)),"Truncated TMVEC header");
    check(std::memcmp(head.magic,"TMVEC1\0\0",8)==0 &&
          head.version==1&&head.entryBytes==sizeof(RawPosition)&&
          head.count>0&&head.count<=1'000'000&&
          fs::file_size(snapshot)==sizeof head+head.count*sizeof(RawPosition),
          "Invalid numeric-only TMVEC snapshot schema/size");
    const DWORD pid=static_cast<DWORD>(head.pid);
    check(uint64_t(pid)==head.pid,"Invalid TMVEC PID");
    Owned proc(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|PROCESS_VM_READ,FALSE,pid));
    check(bool(proc.h),"Cannot attach to this running process in read-only mode");
    check(GetProcessId(proc.h)==pid,"Unexpected canonical process PID");
    wchar_t image[32768]{};
    DWORD imageLen=32768;
    check(QueryFullProcessImageNameW(proc.h,0,image,&imageLen)!=0,
          "Cannot validate executable name");
    const fs::path exe(std::wstring(image,imageLen));
    check(_wcsicmp(exe.filename().c_str(),L"Trackmania.exe")==0,
          "TMVEC source PID does not correspond to Trackmania.exe");
    FILETIME created{},exit{},kernel{},user{};
    check(GetProcessTimes(proc.h,&created,&exit,&kernel,&user)!=0,
          "Cannot obtain game process creation time");
    const uint64_t creation=(uint64_t(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    const std::string gameHash=sha256(exe);
    std::map<std::string,Candidate> groups;
    std::size_t spatialHits=0,validQuats=0;
    RawPosition record{};
    for(uint64_t i=0;i<head.count;i++) {
        check(bool(input.read(reinterpret_cast<char*>(&record),sizeof record)),
              "Truncated TMVEC position entry");
        if(std::hypot(double(record.xyz[0])-start.x,
                      double(record.xyz[2])-start.z)>0.75 ||
           record.xyz[1]<-50||record.xyz[1]>200)continue;
        spatialHits++;
        if(record.address<0x10010 || record.address>0x00007FFFFFF00000ull)continue;
        float raw[7]{};
        SIZE_T n=0;
        // Four FLOATs before XYZ, bounded 28-byte read.
        if(!ReadProcessMemory(proc.h,
            reinterpret_cast<LPCVOID>(static_cast<uintptr_t>(record.address)-16),
            raw,sizeof(raw),&n)||n!=sizeof(raw))continue;
        std::array<float,3> pos{raw[4],raw[5],raw[6]};
        std::array<float,4> quaternion{raw[0],raw[1],raw[2],raw[3]};
        // The snapshot must still represent the CURRENT state; do not mix
        // a snapshot from before a car movement/reset with live memory.
        if(std::hypot(pos[0]-record.xyz[0],
                      std::hypot(pos[1]-record.xyz[1],pos[2]-record.xyz[2]))>0.015)
            continue;
        if(!valid_candidate(pos,quaternion,start.x,start.z))continue;
        validQuats++;
        quaternion=canonical_quat(quaternion);
        const auto k=key(pos,quaternion);
        auto& group=groups[k];
        group.pos=pos;group.q=quaternion;
        group.slots.push_back(static_cast<uintptr_t>(record.address));
        group.distinctPages.insert(static_cast<uintptr_t>(record.address)>>12);
        group.startError=std::hypot(pos[0]-start.x,pos[2]-start.z);
    }
    std::vector<Candidate> ranked;
    for(auto& [k,group]:groups)
        if(group.distinctPages.size()>=4)
            ranked.push_back(std::move(group));
    check(!ranked.empty(),"No four-page consistent start-grid pose candidates");
    std::sort(ranked.begin(),ranked.end(),[](const Candidate& a,const Candidate& b){
        if(std::abs(a.startError-b.startError)>0.001)return a.startError<b.startError;
        if(a.distinctPages.size()!=b.distinctPages.size())
            return a.distinctPages.size()>b.distinctPages.size();
        return std::abs(a.pos[1]-34.)<std::abs(b.pos[1]-34.);
    });
    const auto& best=ranked.front();
    std::set<uintptr_t> seen;
    std::vector<uintptr_t> addresses;
    for(auto slot:best.slots) {
        if(seen.insert(slot>>12).second)addresses.push_back(slot);
        if(addresses.size()>=16)break;
    }
    check(addresses.size()>=4,"No quorum of independently situated candidate copies");
    fs::create_directories(output.parent_path());
    std::ofstream out(output);
    check(bool(out),"Cannot save PID-bound research-only manifest");
    out<<"TM2020_POSE_CANDIDATES_V3\n"<<pid<<"\n"<<creation<<"\n"
       <<gameHash<<"\nXYZ_CANDIDATE_ONLY\n"
       <<std::setprecision(10)<<start.x<<"\n"<<start.z<<"\n"
       <<addresses.size()<<"\n";
    for(const auto address:addresses)out<<hex(address)<<"\n";
    out.close();
    const auto report=output.string()+".meta.json";
    std::ofstream stats(report);
    check(bool(stats),"Cannot save bootstrap provenance report");
    stats<<"{\"schema\":\"tm2020_native_gbx_start_bootstrap_v1\","
         <<"\"pid\":"<<pid<<",\"mapUid\":\""<<map.uid<<"\","
         <<"\"numericMemoryBytesScanned\":"<<head.scanned<<","
         <<"\"spatialHits\":"<<spatialHits<<","
         <<"\"unitQuaternionCandidates\":"<<validQuats<<","
         <<"\"selectedCopies\":"<<addresses.size()<<","
         <<"\"selectedIndependentPages\":"<<best.distinctPages.size()<<","
         <<"\"referenceStartXZ\":["<<start.x<<","<<start.z<<"],"
         <<"\"selectedXYZ\":["<<best.pos[0]<<","<<best.pos[1]<<","<<best.pos[2]<<"],"
         <<"\"selectedQuaternionCandidate\":["
         <<best.q[0]<<","<<best.q[1]<<","<<best.q[2]<<","<<best.q[3]<<"],"
         <<"\"actualVehicleOwnerConfirmed\":false,"
         <<"\"internalPhysicsTickConfirmed\":false,"
         <<"\"gameCodeModified\":false}\n";
    std::cout<<std::fixed<<std::setprecision(4)
             <<"PASS NATIVE_MAP_POSE_BOOTSTRAP mapUID="<<map.uid
             <<" pid="<<pid
             <<" spatialHits="<<spatialHits
             <<" quaternionCandidates="<<validQuats
             <<" selectedCopies="<<addresses.size()
             <<" startErrorXZ="<<best.startError
             <<" selectedXYZ=("<<best.pos[0]<<","<<best.pos[1]<<","<<best.pos[2]<<")"
             <<" physicalOwnerVerified=false CppRuntimeOnly=true"
             <<" result="<<output.string()<<"\n";
    return 0;
}
static void selftest(){
    check(valid_candidate({1200.f,34.014f,1360.f},{0,0,1,0},1200,1360),
          "True synthetic map start should be accepted");
    check(!valid_candidate({1300.f,34.f,1360.f},{0,0,1,0},1200,1360),
          "Wrong start not rejected");
    check(!valid_candidate({1200.f,34.f,1360.f},{0,0,2,0},1200,1360),
          "Non-unit quaternion not rejected");
    check(canonical_quat({0,0,-1,0})[2]==1,"Quaternion double cover not normalized");
    check(key({1200,34,1360},{0,0,1,0})==key({1200,34,1360},canonical_quat({0,0,-1,0})),
          "Equivalent quaternion samples grouped inconsistently");
    std::cout<<"PASS NATIVE_MAP_POSE_BOOTSTRAP_SELFTEST geometry, quaternion, double cover grouping\n";
}
int main(int argc,char**argv)try{
    if(argc==2&&std::string(argv[1])=="--selftest"){selftest();return 0;}
    if(argc==5&&std::string(argv[1])=="--bootstrap")
        return bootstrap(argv[2],argv[3],argv[4]);
    throw std::invalid_argument("Usage: tm2020_bootstrap_map --selftest | --bootstrap <native.tmmap> <numeric.tmvec> <manifest-v3.txt>");
}catch(const std::exception& e){
    std::cerr<<"NATIVE_BOOTSTRAP_ERROR "<<e.what()<<"\n";
    return 1;
}
