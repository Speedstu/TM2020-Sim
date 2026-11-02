// Trackmania 2020 experimental static .data anchored pointer chain probe.
// Official 2026.2.2.1751 build only; independent read-only process observer.
// Never hooks/injects/patches any memory or accesses online game input.
// Pointer chain was FOUND BY CANDIDATE SEARCH IN ONE SOLO SESSION, and is
// UNVERIFIED across process restarts. Do not use as confirmed physics owner.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <wincrypt.h>
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
struct Owned {
    HANDLE p{};
    explicit Owned(HANDLE v):p(v){}
    ~Owned(){if(p&&p!=INVALID_HANDLE_VALUE)CloseHandle(p);}
    Owned(const Owned&)=delete;
};
struct Manifest {
    DWORD referencePid{};
    uint64_t referenceCreation{};
    std::string expectedSHA;
    std::vector<uintptr_t> exampleCopyAddresses;
};
struct Vec3 {float x{},y{},z{};};
struct Quaternion {float a{},b{},c{},d{};};
static void demand(bool ok,const char* msg){
    if(!ok)throw std::runtime_error(msg);
}
static std::string hex(uintptr_t v){
    std::ostringstream s;s<<"0x"<<std::hex<<v;return s.str();
}
static Manifest reference_manifest(const fs::path& path) {
    std::ifstream f(path);
    demand(bool(f),"Read-only candidate reference manifest missing");
    auto next=[&](){
        std::string line;
        if(!std::getline(f,line))throw std::runtime_error("Incomplete candidate manifest");
        return line;
    };
    demand(next()=="TM2020_POSE_CANDIDATES_V3","Cannot use legacy ZYX manifest");
    Manifest m;
    m.referencePid=std::stoul(next());
    m.referenceCreation=std::stoull(next());
    m.expectedSHA=next();
    demand(m.expectedSHA.size()==64,"Invalid build hash");
    demand(next()=="XYZ_CANDIDATE_ONLY","Unexpected axes");
    (void)std::stod(next());(void)std::stod(next());
    const auto n=std::stoul(next());
    demand(n>=4&&n<=64,"Unreasonable reference replica count");
    for(unsigned i=0;i<n;++i)m.exampleCopyAddresses.push_back(std::stoull(next(),nullptr,16));
    return m;
}
static std::string sha256(const fs::path& path){
    HCRYPTPROV prov{};
    HCRYPTHASH hash{};
    demand(CryptAcquireContextW(&prov,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)!=0,"CryptoAPI provider unavailable");
    try {
        demand(CryptCreateHash(prov,CALG_SHA_256,0,0,&hash)!=0,"SHA init failed");
        std::ifstream f(path,std::ios::binary);
        demand(bool(f),"Cannot hash installed Trackmania.exe");
        std::array<char,1<<20> chunk{};
        while(f){
            f.read(chunk.data(),chunk.size());
            const auto count=f.gcount();
            if(count>0)demand(CryptHashData(hash,reinterpret_cast<BYTE*>(chunk.data()),
                                            static_cast<DWORD>(count),0)!=0,"SHA streaming failed");
        }
        std::array<BYTE,32> hashBytes{};
        DWORD n=32;
        demand(CryptGetHashParam(hash,HP_HASHVAL,hashBytes.data(),&n,0)!=0&&n==32,"SHA finalize failed");
        const char* symbols="0123456789abcdef";
        std::string result;
        for(const auto b:hashBytes) {
            result+=symbols[b>>4];
            result+=symbols[b&15];
        }
        CryptDestroyHash(hash);
        CryptReleaseContext(prov,0);
        return result;
    }catch(...){
        if(hash)CryptDestroyHash(hash);
        CryptReleaseContext(prov,0);
        throw;
    }
}
static DWORD find_pid() {
    Owned snap(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
    demand(snap.p&&snap.p!=INVALID_HANDLE_VALUE,"Cannot enumerate processes");
    PROCESSENTRY32W e{};e.dwSize=sizeof e;
    if(!Process32FirstW(snap.p,&e))return 0;
    do {
        if(_wcsicmp(e.szExeFile,L"Trackmania.exe")==0)return e.th32ProcessID;
    }while(Process32NextW(snap.p,&e));
    return 0;
}
static uintptr_t main_base(DWORD pid){
    Owned snap(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,pid));
    demand(snap.p&&snap.p!=INVALID_HANDLE_VALUE,"Cannot enumerate loaded modules");
    MODULEENTRY32W e{};e.dwSize=sizeof e;
    demand(Module32FirstW(snap.p,&e)!=0,"Module list unavailable");
    do {
        if(_wcsicmp(e.szModule,L"Trackmania.exe")==0)
            return reinterpret_cast<uintptr_t>(e.modBaseAddr);
    }while(Module32NextW(snap.p,&e));
    throw std::runtime_error("Trackmania.exe module absent");
}
static bool read_bytes(HANDLE h,uintptr_t addr,void* out,size_t bytes){
    if(addr<0x10000||addr>0x00007FFFFFF00000ull || addr>UINTPTR_MAX-bytes)return false;
    SIZE_T n=0;
    return ReadProcessMemory(h,reinterpret_cast<LPCVOID>(addr),out,bytes,&n)&&n==bytes;
}
static bool approx(Vec3 a,Vec3 b,double limit){
    return std::hypot(double(a.x)-b.x,std::hypot(double(a.y)-b.y,double(a.z)-b.z))<=limit;
}
struct Chain {
    uintptr_t rootSlot{},rootPointer{},taggedSlot{},taggedPointer{},
              parentSlot{},parentPointer{},xyzAddress{};
    Vec3 xyz{};
    Quaternion q{};
    bool firstPointerAligned{},tagBitPresent{},secondPointerAligned{};
};
static bool trace(HANDLE h,uintptr_t moduleBase,Chain& result) {
    constexpr uintptr_t rootRVA=0x020C3240;
    constexpr uintptr_t rootToTaggedSlot=0x2F8;
    constexpr uintptr_t taggedToParentSlot=0x350;
    constexpr uintptr_t parentToPosition=0x318;
    Chain x{};
    x.rootSlot=moduleBase+rootRVA;
    if(!read_bytes(h,x.rootSlot,&x.rootPointer,sizeof x.rootPointer))return false;
    x.firstPointerAligned=(x.rootPointer&7u)==0;
    if(!x.firstPointerAligned||x.rootPointer>UINTPTR_MAX-rootToTaggedSlot)return false;
    x.taggedSlot=x.rootPointer+rootToTaggedSlot;
    if(!read_bytes(h,x.taggedSlot,&x.taggedPointer,sizeof x.taggedPointer))return false;
    // Observed low-bit=1 in a single session; treating it as a possible tag
    // is a hypothesis. Require this bit to avoid silently reinterpreting
    // arbitrary addresses in other game versions/modes.
    x.tagBitPresent=(x.taggedPointer&1u)==1u;
    if(!x.tagBitPresent)return false;
    const auto untagged=x.taggedPointer&~uintptr_t(1);
    if((untagged&7u)!=0||untagged>UINTPTR_MAX-taggedToParentSlot)return false;
    x.parentSlot=untagged+taggedToParentSlot;
    if(!read_bytes(h,x.parentSlot,&x.parentPointer,sizeof x.parentPointer))return false;
    x.secondPointerAligned=(x.parentPointer&7u)==0;
    if(!x.secondPointerAligned||x.parentPointer>UINTPTR_MAX-parentToPosition)return false;
    x.xyzAddress=x.parentPointer+parentToPosition;
    if(!read_bytes(h,x.xyzAddress,&x.xyz,sizeof x.xyz))return false;
    if(!read_bytes(h,x.xyzAddress-16,&x.q,sizeof x.q))return false;
    if(!std::isfinite(x.xyz.x)||!std::isfinite(x.xyz.y)||!std::isfinite(x.xyz.z)||
       std::abs(x.xyz.x)>10000||std::abs(x.xyz.y)>10000||std::abs(x.xyz.z)>10000)
        return false;
    result=x;
    return true;
}
static void selftest(){
    const uintptr_t ptr=0x0000015805752bf1ull;
    demand((ptr&1)==1 && ((ptr&~uintptr_t(1))+0x350)==0x0000015805752f40ull,
           "Low-bit pointer assumption arithmetic failed");
    demand(sizeof(Vec3)==12 && sizeof(Quaternion)==16,"Unexpected float layout");
    std::cout<<"PASS ANCHORED_CHAIN_SELFTEST tested tagged-pointer arithmetic and layout; no game accessed\n";
}
static int probe(int argc,char**argv){
    demand(argc==4,"Usage: tm2020_anchored_chain --probe <known-v3-manifest> <report.json>");
    const auto known=reference_manifest(argv[2]);
    const auto pid=find_pid();
    demand(pid!=0,"Trackmania is not running; no process launched");
    Owned h(OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid));
    demand(bool(h.p),"No read-only game access");
    demand(GetProcessId(h.p)==pid,"PID alias unexpectedly resolved to another process");
    FILETIME created{},exit{},kernel{},user{};
    demand(GetProcessTimes(h.p,&created,&exit,&kernel,&user)!=0,"Cannot verify process start time");
    const auto started=(uint64_t(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    std::array<wchar_t,32768> name{};
    DWORD n=static_cast<DWORD>(name.size());
    demand(QueryFullProcessImageNameW(h.p,0,name.data(),&n)!=0,"Cannot query game executable");
    const fs::path exe(std::wstring(name.data(),n));
    demand(_wcsicmp(exe.filename().c_str(),L"Trackmania.exe")==0,"Wrong target game binary");
    demand(sha256(exe)==known.expectedSHA,"Game version hash differs from identified chain build");
    const auto base=main_base(pid);
    Chain x{};
    const bool success=trace(h.p,base,x);
    int matching=0,checked=0;
    const bool sameProcess=(pid==known.referencePid && started==known.referenceCreation);
    if(success&&sameProcess) {
        for(const auto addr:known.exampleCopyAddresses) {
            Vec3 comparison{};
            if(read_bytes(h.p,addr,&comparison,sizeof comparison)) {
                checked++;
                if(approx(x.xyz,comparison,0.5))matching++;
            }
        }
    }
    const bool verifiedAgainstIndependentCopies=sameProcess&&matching>=4;
    auto dest=fs::path(argv[3]);
    fs::create_directories(dest.parent_path());
    std::ofstream out(dest);
    demand(bool(out),"Cannot create research-only report on H:");
    out<<std::fixed<<std::setprecision(8)
       <<"{\"schema\":\"tm2020_build_pinned_candidate_global_chain_v1\","
       <<"\"gamePid\":"<<pid
       <<",\"originalReferencePid\":"<<known.referencePid
       <<",\"sameGameProcessAsDiscovery\":"<<(sameProcess?"true":"false")
       <<",\"candidateChainResolved\":"<<(success?"true":"false")
       <<",\"matchingIndependentXYZCopies\":"<<matching
       <<",\"independentlyCheckedCopies\":"<<checked
       <<",\"verifiedAgainstSameSessionCopies\":"<<(verifiedAgainstIndependentCopies?"true":"false")
       <<",\"validatedAcrossProcessRestart\":false,"
       <<"\"confirmedAuthoritativePhysicsOwner\":false,"
       <<"\"confirmed100HzVehicleTelemetry\":false,"
       <<"\"gameMemoryModified\":false,"
       <<"\"rootStaticRVA\":\"0x20c3240\","
       <<"\"rootToFlaggedSlot\":760,"
       <<"\"taggedParentToSlot\":848,"
       <<"\"parentToXYZ\":792,"
       <<"\"observedTaggedPointerLowBitRequired\":true,"
       <<"\"runtimeModuleBase\":\""<<hex(base)<<"\","
       <<"\"xyzAddress\":\""<<hex(x.xyzAddress)<<"\","
       <<"\"xyzCandidate\":["<<x.xyz.x<<","<<x.xyz.y<<","<<x.xyz.z<<"],"
       <<"\"quatCandidate\":["<<x.q.a<<","<<x.q.b<<","<<x.q.c<<","<<x.q.d<<"],"
       <<"\"note\":\"Same-build session-derived static .data global candidate. Independently validate restarted car physics and quaternion/inputs before SDK use.\"}\n";
    std::cout<<"ANCHORED_CHAIN_PROBE pid="<<pid
             <<" sameSession="<<sameProcess
             <<" chainResolved="<<success
             <<" replicaMatches="<<matching<<"/"<<checked
             <<" xyz=("<<x.xyz.x<<","<<x.xyz.y<<","<<x.xyz.z<<")"
             <<" rootRVA=0x20c3240 taggedBitRequired=true"
             <<" restartValidated=false physicsOwnerValidated=false\n";
    return success&&(!sameProcess||verifiedAgainstIndependentCopies)?0:1;
}
int main(int argc,char**argv)try {
    if(argc==2&&std::string(argv[1])=="--selftest"){selftest();return 0;}
    if(argc>=2&&std::string(argv[1])=="--probe")return probe(argc,argv);
    throw std::invalid_argument("Usage: tm2020_anchored_chain --selftest|--probe <reference-manifest-v3> <H:\\report.json>");
}catch(const std::exception& e){
    std::cerr<<"ANCHORED_CHAIN_ERROR "<<e.what()<<"\n";
    return 1;
}
