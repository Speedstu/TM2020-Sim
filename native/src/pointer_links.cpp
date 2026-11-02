// Trackmania2020 local/offline read-only bounded reverse pointer reference scanner.
// Scans only committed readable PRIVATE pages and MAIN MODULE mapped image pages.
// Does NOT dump page contents, inject DLLs, patch, hook, send inputs or elevate.
// Parent references from static data are hypotheses, not verified stable game
// vehicle owner pointers. Any reverse pointer chain requires fresh validation
// in a second restarted game session before SDK use.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <TlHelp32.h>
#include <wincrypt.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
struct Handle {
    HANDLE h{};
    explicit Handle(HANDLE v):h(v){}
    ~Handle(){if(h)CloseHandle(h);}
    Handle(const Handle&)=delete;
};
struct TargetManifest{
    DWORD pid{};
    uint64_t startTime{};
    std::string sha256;
    std::vector<uintptr_t> addresses;
};
struct Link {
    uintptr_t source{},value{},target{},delta{};
    bool staticModule{};
};
static void require(bool yes,const char* why){
    if(!yes)throw std::runtime_error(why);
}
static TargetManifest parse(const fs::path& p){
    std::ifstream in(p);
    require(bool(in),"Missing session-only candidate manifest");
    auto next=[&](){
        std::string x;
        if(!std::getline(in,x))throw std::runtime_error("Incomplete manifest");
        return x;
    };
    require(next()=="TM2020_POSE_CANDIDATES_V3","Only V3 manifests supported");
    TargetManifest m;
    m.pid=std::stoul(next());
    m.startTime=std::stoull(next());
    m.sha256=next();
    require(m.sha256.size()==64,"Invalid binary checksum");
    require(next()=="XYZ_CANDIDATE_ONLY","Unexpected candidate layout");
    (void)std::stod(next());(void)std::stod(next());
    const auto n=std::stoul(next());
    require(n>=4&&n<=64,"Need 4..64 read-only position hypotheses");
    for(unsigned i=0;i<n;i++)m.addresses.push_back(std::stoull(next(),nullptr,16));
    std::sort(m.addresses.begin(),m.addresses.end());
    require(std::adjacent_find(m.addresses.begin(),m.addresses.end())==m.addresses.end(),
            "Duplicate target address");
    return m;
}
static std::string sha256(const fs::path& file){
    HCRYPTPROV provider{};
    HCRYPTHASH h{};
    require(CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)!=0,
            "Windows SHA-256 provider unavailable");
    try {
        require(CryptCreateHash(provider,CALG_SHA_256,0,0,&h)!=0,"Cannot start SHA-256");
        std::ifstream stream(file,std::ios::binary);
        require(bool(stream),"Missing game exe on disk");
        std::array<char,1048576> buf{};
        while(stream) {
            stream.read(buf.data(),buf.size());
            const auto n=stream.gcount();
            if(n>0)require(CryptHashData(h,reinterpret_cast<const BYTE*>(buf.data()),
                         static_cast<DWORD>(n),0)!=0,"Cannot hash game exe");
        }
        BYTE raw[32]{};DWORD n=32;
        require(CryptGetHashParam(h,HP_HASHVAL,raw,&n,0)!=0&&n==32,"Bad digest");
        static constexpr char chars[]="0123456789abcdef";
        std::string s;
        for(auto c:raw){s+=chars[c>>4];s+=chars[c&15];}
        CryptDestroyHash(h);CryptReleaseContext(provider,0);
        return s;
    }catch(...){
        if(h)CryptDestroyHash(h);
        CryptReleaseContext(provider,0);
        throw;
    }
}
static bool find_target(const std::vector<uintptr_t>& targets,uintptr_t value,
                        uintptr_t maxOffset,uintptr_t& target,uintptr_t& offset){
    auto it=std::lower_bound(targets.begin(),targets.end(),value);
    if(it==targets.end()||*it-value>maxOffset)return false;
    target=*it;
    offset=target-value;
    return true;
}
static void selftest() {
    const std::vector<uintptr_t> targets{0x1000,0x3000,0x4000};
    uintptr_t goal=0,diff=0;
    require(find_target(targets,0x0e80,0x200,goal,diff) && goal==0x1000&&diff==0x180,
           "Pointer-base-to-position offset lookup broken");
    require(!find_target(targets,0x1010,0x200,goal,diff),
           "Reject pointer after target position");
    require(!find_target(targets,0x2000,0x500,goal,diff),
           "Reject pointer too distant from its intended value");
    std::cout<<"PASS POINTER_REVERSE_SELFTEST offset-range search, negative bounds, no game process used\n";
}
struct ScanResult {
    std::vector<Link> matches;
    uint64_t scanned{},pages{},readFailures{};
    bool capped{};
};
static ScanResult scan(HANDLE process,uintptr_t exeBase,uintptr_t exeLength,
                       const std::vector<uintptr_t>& search,uintptr_t offsetLimit,
                       uint64_t maxReadBytes,size_t maxResults,bool onlyMainImage=false) {
    ScanResult result;
    if(search.empty())return result;
    std::vector<unsigned char> buf(524288+8);
    // This mirrors the successful numeric snapshot's bounded read-only query.
    const uintptr_t lower=onlyMainImage?exeBase:0x10000;
    const uintptr_t upper=onlyMainImage?(exeBase+exeLength):0x00007FFFFFF00000ull;
    for(uintptr_t address=lower;address<upper
        && result.scanned<maxReadBytes && result.matches.size()<maxResults;){
        MEMORY_BASIC_INFORMATION memory{};
        if(VirtualQueryEx(process,reinterpret_cast<void*>(address),&memory,sizeof memory)!=sizeof memory){
            address+=0x1000;
            continue;
        }
        const auto base=reinterpret_cast<uintptr_t>(memory.BaseAddress);
        const auto total=static_cast<uint64_t>(memory.RegionSize);
        const auto next=base+total;
        if(next<=address)break;
        address=next;
        const auto prot=memory.Protect&0xffu;
        const bool readable=(prot==PAGE_READWRITE||prot==PAGE_WRITECOPY||
                             prot==PAGE_READONLY||prot==PAGE_EXECUTE_READWRITE||
                             prot==PAGE_EXECUTE_WRITECOPY||prot==PAGE_EXECUTE_READ);
        const bool inMainModule=(base>=exeBase && base<exeBase+exeLength);
        if(memory.State!=MEM_COMMIT||!readable ||
           (memory.Protect&(PAGE_GUARD|PAGE_NOACCESS)) ||
           (onlyMainImage && !inMainModule) ||
           (memory.Type!=MEM_PRIVATE && !(memory.Type==MEM_IMAGE&&inMainModule)))
            continue;
        ++result.pages;
        uint64_t off=0;
        const uint64_t limit=std::min<uint64_t>(total,maxReadBytes-result.scanned);
        while(off<limit && result.matches.size()<maxResults){
            const uintptr_t current=base+off;
            const SIZE_T requested=static_cast<SIZE_T>(std::min<uint64_t>(524288,total-off));
            SIZE_T got=0;
            if(!ReadProcessMemory(process,reinterpret_cast<void*>(current),
                                 buf.data(),requested,&got)||got<8){
                ++result.readFailures;
                off+=requested; // bounded forward progress on inaccessible pages
                continue;
            }
            for(size_t i=(8-current%8)%8;i+8<=got;i+=8) {
                uintptr_t ptr=0;
                std::memcpy(&ptr,buf.data()+i,8);
                if(ptr<0x10000||ptr>0x00007FFFFFF00000ull)continue;
                uintptr_t target=0,delta=0;
                if(find_target(search,ptr,offsetLimit,target,delta)){
                    result.matches.push_back({current+i,ptr,target,delta,inMainModule});
                    if(result.matches.size()>=maxResults)break;
                }
            }
            off+=got;
            result.scanned+=got;
        }
    }
    result.capped=result.scanned>=maxReadBytes||result.matches.size()>=maxResults;
    return result;
}
static void json_links(std::ofstream& out,const std::vector<Link>& links,size_t maxCount){
    const auto count=std::min(maxCount,links.size());
    for(size_t i=0;i<count;i++){
        if(i)out<<",";
        const auto& e=links[i];
        out<<"{\"source\":\"0x"<<std::hex<<e.source
           <<"\",\"targetBase\":\"0x"<<e.value<<"\",\"targetPosition\":\"0x"<<e.target
           <<"\",\"byteOffset\":"<<std::dec<<e.delta
           <<",\"sourceInGameImage\":"<<(e.staticModule?"true":"false")<<"}";
    }
}
static int run(int argc,char**argv){
    require(argc==5,"Usage tm2020_pointer_links --scan <manifest-v3> <output.json> <maxMB 128..2048>");
    const TargetManifest m=parse(argv[2]);
    const auto outpath=fs::path(argv[3]);
    const auto maxMB=std::stoull(argv[4]);
    require(maxMB>=128&&maxMB<=2048,"Scan cap must be 128..2048MiB");
    Handle handle(OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,m.pid));
    require(bool(handle.h),"Game PID not running/read permission denied");
    require(GetProcessId(handle.h)==m.pid,"Windows resolved a different canonical game PID");
    FILETIME created{},exited{},kernel{},user{};
    require(GetProcessTimes(handle.h,&created,&exited,&kernel,&user)!=0,"Cannot identify process start");
    const auto started=(uint64_t(created.dwHighDateTime)<<32)|created.dwLowDateTime;
    require(started==m.startTime,"Process was restarted: manifest no longer valid");
    std::array<wchar_t,32768> path{};
    DWORD len=static_cast<DWORD>(path.size());
    require(QueryFullProcessImageNameW(handle.h,0,path.data(),&len)!=0,"Cannot identify executable");
    const fs::path gameExe(std::wstring(path.data(),len));
    require(_wcsicmp(gameExe.filename().c_str(),L"Trackmania.exe")==0,
            "PID points to a different executable");
    require(sha256(gameExe)==m.sha256,"Game executable hash is stale");
    Handle mods(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE|TH32CS_SNAPMODULE32,m.pid));
    require(mods.h&&mods.h!=INVALID_HANDLE_VALUE,"Cannot enumerate game image modules");
    MODULEENTRY32W info{};info.dwSize=sizeof info;
    require(Module32FirstW(mods.h,&info)!=0,"No loaded game modules");
    while(_wcsicmp(info.szModule,L"Trackmania.exe")!=0) {
        require(Module32NextW(mods.h,&info)!=0,"Game executable image not found");
    }
    const auto mainBase=reinterpret_cast<uintptr_t>(info.modBaseAddr);
    const auto mainSize=static_cast<uintptr_t>(info.modBaseSize);
    const uint64_t cap=maxMB*1048576ull;
    // Prioritize main executable image independently of the private heap cap.
    // Old scans walked from low addresses and exhausted the cap before .data
    // was ever visited, making claims of "no static roots" unjustified.
    const auto imageDirect=scan(handle.h,mainBase,mainSize,m.addresses,2048,
                                256ull*1048576,30000,true);
    // L1: pointer to an object located <= 2048 bytes before a candidate.
    const auto first=scan(handle.h,mainBase,mainSize,m.addresses,2048,cap,30000);
    std::vector<uintptr_t> firstSources;
    firstSources.reserve(first.matches.size());
    for(const auto& e:first.matches)firstSources.push_back(e.source);
    std::sort(firstSources.begin(),firstSources.end());
    firstSources.erase(std::unique(firstSources.begin(),firstSources.end()),firstSources.end());
    // L2: pointer to the enclosing parent structure containing an L1 slot.
    const auto imageToFirst=scan(handle.h,mainBase,mainSize,firstSources,1024,
                                 256ull*1048576,30000,true);
    const auto second=scan(handle.h,mainBase,mainSize,firstSources,1024,cap,30000);
    std::vector<uintptr_t> secondSources;
    secondSources.reserve(second.matches.size());
    for(const auto& e:second.matches)secondSources.push_back(e.source);
    std::sort(secondSources.begin(),secondSources.end());
    secondSources.erase(std::unique(secondSources.begin(),secondSources.end()),secondSources.end());
    const auto imageToSecond=scan(handle.h,mainBase,mainSize,secondSources,1024,
                                  256ull*1048576,30000,true);
    // L3: a further dynamic owner/manager reference hop. This can reveal
    // deeper static roots but is still only a positional address hypothesis.
    const auto third=scan(handle.h,mainBase,mainSize,secondSources,1024,cap,30000);
    std::vector<uintptr_t> thirdSources;
    thirdSources.reserve(third.matches.size());
    for(const auto& e:third.matches)thirdSources.push_back(e.source);
    std::sort(thirdSources.begin(),thirdSources.end());
    thirdSources.erase(std::unique(thirdSources.begin(),thirdSources.end()),thirdSources.end());
    const auto imageToThird=scan(handle.h,mainBase,mainSize,thirdSources,1024,
                                 256ull*1048576,30000,true);
    auto rootCount=[](const auto& links){
        return std::count_if(links.begin(),links.end(),[](const Link& l){return l.staticModule;});
    };
    fs::create_directories(outpath.parent_path());
    std::ofstream out(outpath);
    require(bool(out),"Cannot create H: pointer research JSON");
    out<<"{\"schema\":\"tm2020_session_pointer_reverse_hypotheses_v3\","
       <<"\"imageScanIndependentlyPrioritized\":true,"
       <<"\"imageDirectMatches\":"<<imageDirect.matches.size()<<","
       <<"\"imageToLevel1Matches\":"<<imageToFirst.matches.size()<<","
       <<"\"imageToLevel2Matches\":"<<imageToSecond.matches.size()<<","
       <<"\"imageToLevel3Matches\":"<<imageToThird.matches.size()<<","
       <<"\"imageDirectScanIncomplete\":"<<(imageDirect.capped?"true":"false")<<","
       <<"\"imageLevel1ScanIncomplete\":"<<(imageToFirst.capped?"true":"false")<<","
       <<"\"imageLevel2ScanIncomplete\":"<<(imageToSecond.capped?"true":"false")<<","
       <<"\"imageLevel3ScanIncomplete\":"<<(imageToThird.capped?"true":"false")<<","
       <<"\"imageFirstExamples\":[",
       json_links(out,imageDirect.matches,300);
    out<<"],\"imageToLevel1Examples\":[";
    json_links(out,imageToFirst.matches,300);
    out<<"],\"imageToLevel2Examples\":[";
    json_links(out,imageToSecond.matches,imageToSecond.matches.size());
    out<<"],\"imageToLevel3Examples\":[";
    json_links(out,imageToThird.matches,imageToThird.matches.size());
    out<<"],\"pid\":"<<m.pid<<",\"exe_sha256\":\""<<m.sha256<<"\","
       <<"\"sourceCandidateCount\":"<<m.addresses.size()<<","
       <<"\"scanCapMBPerLevel\":"<<maxMB<<","
       <<"\"level1Matches\":"<<first.matches.size()<<","
       <<"\"level1StaticImageMatches\":"<<rootCount(first.matches)<<","
       <<"\"level1ScannedMB\":"<<first.scanned/1048576<<","
       <<"\"level1ReadsDenied\":"<<first.readFailures<<","
       <<"\"level1Incomplete\":"<<(first.capped?"true":"false")<<","
       <<"\"level2Matches\":"<<second.matches.size()<<","
       <<"\"level3Matches\":"<<third.matches.size()<<","
       <<"\"level3ScannedMB\":"<<third.scanned/1048576<<","
       <<"\"level3Incomplete\":"<<(third.capped?"true":"false")<<","
       <<"\"level2StaticImageMatches\":"<<rootCount(second.matches)<<","
       <<"\"level2ScannedMB\":"<<second.scanned/1048576<<","
       <<"\"level2Incomplete\":"<<(second.capped?"true":"false")<<","
       <<"\"authoritativePhysicsOwnerVerified\":false,"
       <<"\"stableAcrossRestartVerified\":false,"
       <<"\"gameProcessModified\":false,"
       <<"\"note\":\"Read-only probable pointer edges, NOT a verified reusable chain. Exact pointer-field structure/physics owner requires restart verification.\","
       <<"\"level1Examples\":[";
    json_links(out,first.matches,first.matches.size());
    out<<"],\"level2Examples\":[";
    json_links(out,second.matches,second.matches.size());
    out<<"],\"level3Examples\":[";
    json_links(out,third.matches,third.matches.size());
    out<<"]}\n";
    std::cout<<"PASS BOUNDED_REVERSE_POINTER_PROBE pid="<<m.pid
             <<" imageDirect="<<imageDirect.matches.size()
             <<" imageViaL1="<<imageToFirst.matches.size()
             <<" imageViaL2="<<imageToSecond.matches.size()
             <<" imageViaL3="<<imageToThird.matches.size()
             <<" L1="<<first.matches.size()
             <<" L1image="<<rootCount(first.matches)
             <<" L2="<<second.matches.size()
             <<" L3="<<third.matches.size()
             <<" L2image="<<rootCount(second.matches)
             <<" levelScannedMB="<<first.scanned/1048576<<","<<second.scanned/1048576
             <<" complete="<<(!first.capped&&!second.capped&&!third.capped)
             <<" physicsOwnerVerified=false gameMemoryModified=false"
             <<" json="<<outpath.string()<<"\n";
    return 0;
}
int main(int argc,char**argv)try{
    if(argc==2&&std::string(argv[1])=="--selftest"){selftest();return 0;}
    if(argc>=2&&std::string(argv[1])=="--scan")return run(argc,argv);
    throw std::invalid_argument("Usage: tm2020_pointer_links --selftest | --scan manifest-v3 output.json scanMB");
}catch(const std::exception& e){
    std::cerr<<"POINTER_RESEARCH_ERROR "<<e.what()<<"\n";return 1;
}
