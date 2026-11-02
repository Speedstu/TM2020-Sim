// Read-only candidate vector snapshot from installed Trackmania process.
// Captures only plausible 3-float position vectors, NOT full process pages,
// strings, credentials or arbitrary executable data.
// Hypothesis generation ONLY. A moving position plus independent visual
// verification is required before an address can be called vehicle telemetry.
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <TlHelp32.h>
#include <array>
#include <algorithm>
#include <cmath>
#include <cstddef>
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
#pragma pack(push,1)
struct Header {
    char magic[8]{'T','M','V','E','C','1','\0','\0'};
    uint32_t version{1};
    uint32_t entry_size{20};
    uint64_t process_id{};
    uint64_t bytes_scanned{};
    uint64_t entries{};
};
struct VecRec {uint64_t address{};float xyz[3]{};};
#pragma pack(pop)
static_assert(sizeof(VecRec)==20);
struct Handle {
    HANDLE val{};
    explicit Handle(HANDLE h):val(h){}
    ~Handle(){if(val&&val!=INVALID_HANDLE_VALUE)CloseHandle(val);}
    Handle(const Handle&)=delete;
    Handle& operator=(const Handle&)=delete;
};
DWORD game_pid(){
    Handle s(CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0));
    PROCESSENTRY32W e{};e.dwSize=sizeof e;
    if(s.val==INVALID_HANDLE_VALUE||!Process32FirstW(s.val,&e))return 0;
    do {if(_wcsicmp(e.szExeFile,L"Trackmania.exe")==0)return e.th32ProcessID;}
    while(Process32NextW(s.val,&e));
    return 0;
}
bool likely(float x,float y,float z){
    if(!std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z))return false;
    if(x<=-8192||x>=8192||y<=-512||y>=2048||z<=-8192||z>=8192)return false;
    if(std::abs(x)<5&&std::abs(z)<5)return false;
    return true;
}
std::vector<VecRec> read_candidates(const fs::path& file,Header& h,uint64_t limitMB) {
    std::ifstream in(file,std::ios::binary);
    if(!in||!in.read((char*)&h,sizeof h))throw std::runtime_error("Cannot read candidate capture header");
    if(std::memcmp(h.magic,"TMVEC1\0\0",8)!=0||h.version!=1||h.entry_size!=20||
       h.entries>10'000'000||sizeof(Header)+h.entries*sizeof(VecRec)>limitMB*1024*1024)
        throw std::runtime_error("Invalid vector snapshot schema");
    std::vector<VecRec> values(h.entries);
    if(h.entries&&!in.read((char*)values.data(),h.entries*sizeof(VecRec)))
        throw std::runtime_error("Truncated vector snapshot");
    if(in.peek()!=EOF)throw std::runtime_error("Extra data in vector snapshot");
    return values;
}
int capture(const fs::path& output,uint64_t maxMB) {
    DWORD pid=game_pid();
    if(!pid)throw std::runtime_error("Trackmania must be running in SOLO mode");
    Handle h(OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid));
    if(!h.val)throw std::runtime_error("Read-only OpenProcess denied");
    constexpr uint64_t pageMax=0x00007FFFFFFF0000ULL;
    const uint64_t maxBytes=maxMB*1024*1024;
    constexpr uint64_t maxEntries=1'000'000;
    std::vector<VecRec> found;found.reserve(500000);
    std::vector<std::byte> buffer(1'048'576+8);
    uint64_t consumed=0, scanned=0,regions=0,blocks=0,readFails=0;
    for(uint64_t address=0x10000;address<pageMax&&consumed<maxBytes&&found.size()<maxEntries;){
        MEMORY_BASIC_INFORMATION mbi{};
        if(VirtualQueryEx(h.val,(LPCVOID)address,&mbi,sizeof mbi)!=sizeof mbi){
            address+=0x1000;
            continue;
        }
        const auto regionBase=reinterpret_cast<uint64_t>(mbi.BaseAddress);
        const auto regionSize=static_cast<uint64_t>(mbi.RegionSize);
        const uint64_t next=regionBase+regionSize;
        if(next<=address)break;
        address=next;
        const DWORD protect=mbi.Protect&0xffu;
        const bool readable=protect==PAGE_READWRITE||protect==PAGE_WRITECOPY||
                            protect==PAGE_EXECUTE_READWRITE||protect==PAGE_EXECUTE_WRITECOPY;
        if(mbi.State!=MEM_COMMIT||mbi.Type!=MEM_PRIVATE||!readable||
           (mbi.Protect&(PAGE_GUARD|PAGE_NOACCESS)))continue;
        regions++;
        uint64_t size=std::min(regionSize,maxBytes-consumed);
        for(uint64_t off=0;off<size&&found.size()<maxEntries;){
            const uint64_t loc=regionBase+off;
            const size_t requested=static_cast<size_t>(std::min<uint64_t>(buffer.size(),regionSize-off));
            SIZE_T got=0;
            const BOOL ok=ReadProcessMemory(h.val,(LPCVOID)loc,buffer.data(),requested,&got);
            if(!ok||got<16){readFails++;off+=1'048'576;continue;}
            const size_t count=std::min<std::size_t>(got,1'048'576);
            // float triples at word-aligned positions within process memory.
            const size_t first=(4-(loc%4))%4;
            for(size_t i=first;i+12<=got&&i<count;i+=4){
                std::array<float,3> v{};
                std::memcpy(v.data(),buffer.data()+i,12);
                if(!likely(v[0],v[1],v[2]))continue;
                VecRec rec{};rec.address=loc+i;
                std::copy(v.begin(),v.end(),rec.xyz);
                found.push_back(rec);
                if(found.size()>=maxEntries)break;
            }
            off+=count;scanned+=count;blocks++;
        }
        consumed+=size;
    }
    Header hdr{};hdr.process_id=pid;hdr.bytes_scanned=scanned;hdr.entries=found.size();
    fs::create_directories(output.parent_path());
    std::ofstream out(output,std::ios::binary);
    if(!out||!out.write((char*)&hdr,sizeof hdr)||
       !out.write((char*)found.data(),found.size()*sizeof(VecRec)))
        throw std::runtime_error("Unable to write compact numeric vectors on H:");
    std::cout<<"PASS CANDIDATE_VECTOR_CAPTURE pid="<<pid
             <<" scannedMB="<<scanned/1048576
             <<" regions="<<regions
             <<" readBlocks="<<blocks
             <<" blockedReads="<<readFails
             <<" candidateTriples="<<found.size()
             <<" cutoffReached="<<(found.size()>=maxEntries)
             <<" actualVehiclePositionConfirmed=false"
             <<" output="<<output.string()<<"\n";
    return 0;
}
int compare(const fs::path& a,const fs::path& b,const fs::path& result){
    Header h1{},h2{};
    auto x=read_candidates(a,h1,512),y=read_candidates(b,h2,512);
    if(h1.process_id!=h2.process_id)
        throw std::runtime_error("Cannot compare snapshots from different game processes");
    struct Difference {uint64_t address;float a[3],b[3];double distance;};
    std::vector<Difference> diffs;
    size_t i=0,j=0;
    while(i<x.size()&&j<y.size()){
        if(x[i].address<y[j].address){i++;continue;}
        if(x[i].address>y[j].address){j++;continue;}
        double dist=0;
        for(int k=0;k<3;k++){
            const double d=double(x[i].xyz[k])-y[j].xyz[k];
            dist+=d*d;
        }
        dist=std::sqrt(dist);
        if(dist>=0.1&&dist<=200.){
            Difference d{};d.address=x[i].address;d.distance=dist;
            for(int k=0;k<3;k++){d.a[k]=x[i].xyz[k];d.b[k]=y[j].xyz[k];}
            diffs.push_back(d);
        }
        i++;j++;
    }
    // Read-only observation candidates, not verified vehicle offsets.
    std::sort(diffs.begin(),diffs.end(),[](const Difference& a,const Difference& b){
        return a.distance<b.distance;
    });
    fs::create_directories(result.parent_path());
    std::ofstream csv(result);
    if(!csv)throw std::runtime_error("Could not create diff result");
    csv<<"address,xyz0,xyz1,xyz2,next0,next1,next2,distance_m_candidate\n";
    csv<<std::fixed<<std::setprecision(6);
    constexpr size_t maxReport=10000;
    for(size_t k=0;k<std::min(maxReport,diffs.size());++k){
        const auto& d=diffs[k];
        csv<<"0x"<<std::hex<<d.address<<std::dec<<","<<d.a[0]<<","<<d.a[1]
           <<","<<d.a[2]<<","<<d.b[0]<<","<<d.b[1]<<","<<d.b[2]
           <<","<<d.distance<<"\n";
    }
    std::cout<<"PASS CANDIDATE_VECTOR_DIFF pid="<<h1.process_id
             <<" baseline="<<x.size()<<" after="<<y.size()
             <<" changedCandidates="<<diffs.size()
             <<" reported="<<std::min(maxReport,diffs.size())
             <<" actualVehiclePositionConfirmed=false"
             <<" output="<<result.string()<<"\n";
    return 0;
}
int main(int argc,char**argv)try{
    if(argc>=3 && std::string(argv[1])=="--capture"){
        uint64_t maxMB=argc>=4?std::stoull(argv[3]):768;
        if(maxMB<16||maxMB>2048)throw std::runtime_error("Memory scan limit must be 16..2048 MB");
        return capture(argv[2],maxMB);
    }
    if(argc==5&&std::string(argv[1])=="--compare")
        return compare(argv[2],argv[3],argv[4]);
    std::cerr<<"Usage: tm2020_live_vector_probe --capture <H:\\snapshot.tmvec> [max_MB]\n"
               "       tm2020_live_vector_probe --compare <first.tmvec> <later.tmvec> <H:\\diff.csv>\n";
    return 2;
}catch(const std::exception& e){std::cerr<<"LIVE_VECTOR_ERROR "<<e.what()<<"\n";return 1;}
