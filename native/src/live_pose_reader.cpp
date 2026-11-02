// Trackmania2020 research: validated-read-only OBSERVER for a PID-bound
// experimental pose-candidate manifest. No injection, hooks, memory writes,
// privilege escalation or gameplay input. A position that matches multiple
// rendering copies is NOT proof of the internal physics owner.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wincrypt.h>
#include <array>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
struct ScopedProcess {
    HANDLE h{};
    explicit ScopedProcess(HANDLE handle):h(handle){}
    ~ScopedProcess(){if(h)CloseHandle(h);}
    ScopedProcess(const ScopedProcess&)=delete;
};
struct XYZ {double x{},y{},z{};};
struct Manifest {
    unsigned long pid{};
    uint64_t processCreationFiletime{};
    std::string sha256;
    XYZ start{};
    std::vector<uintptr_t> addresses;
};
static void require(bool yes,const char* msg){
    if(!yes)throw std::runtime_error(msg);
}
static Manifest load_manifest(const fs::path& file) {
    std::ifstream in(file);
    require(bool(in),"Missing pose hypothesis manifest");
    std::string line;
    auto get=[&]()->std::string {
        std::string v;
        if(!std::getline(in,v))throw std::runtime_error("Incomplete pose manifest");
        return v;
    };
    require(get()=="TM2020_POSE_CANDIDATES_V3","Reject older or unknown manifest format");
    Manifest m;
    m.pid=std::stoul(get());
    m.processCreationFiletime=std::stoull(get());
    require(m.processCreationFiletime>100000000000000000ULL,"Invalid process creation filetime");
    m.sha256=get();
    require(m.sha256.size()==64,"Invalid source binary hash");
    for(char c:m.sha256)require(std::isxdigit(static_cast<unsigned char>(c))!=0,"Invalid hash hex");
    require(get()=="XYZ_CANDIDATE_ONLY","Unsupported/missing coordinate layout");
    m.start.x=std::stod(get());m.start.z=std::stod(get());
    auto n=std::stoul(get());
    require(n>=4 && n<=64,"Expected 4-64 independent position copies");
    for(unsigned i=0;i<n;i++){
        auto address=std::stoull(get(),nullptr,16);
        require(address>=0x10000 && address<0x00007FFFFFFF0000ull,"Noncanonical address in manifest");
        m.addresses.push_back(static_cast<uintptr_t>(address));
    }
    require(!std::getline(in,line) || line.empty(),"Unexpected extra manifest bytes");
    std::sort(m.addresses.begin(),m.addresses.end());
    require(std::adjacent_find(m.addresses.begin(),m.addresses.end())==m.addresses.end(),"Duplicate memory addresses");
    for(std::size_t i=1;i<m.addresses.size();++i)
        require((m.addresses[i]>>12)!=(m.addresses[i-1]>>12),"Not independent memory pages");
    return m;
}
static std::string sha256(const fs::path& file) {
    HCRYPTPROV provider{};
    HCRYPTHASH hash{};
    if(!CryptAcquireContextW(&provider,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT))
        throw std::runtime_error("Windows SHA256 provider unavailable");
    auto release=[&](){
        if(hash)CryptDestroyHash(hash);
        if(provider)CryptReleaseContext(provider,0);
    };
    try {
        require(CryptCreateHash(provider,CALG_SHA_256,0,0,&hash)!=0,"Windows SHA256 hash failed");
        std::ifstream stream(file,std::ios::binary);
        require(bool(stream),"Could not open installed Trackmania binary");
        std::array<char,1<<20> buffer{};
        while(stream){
            stream.read(buffer.data(),buffer.size());
            auto n=stream.gcount();
            if(n>0)require(CryptHashData(hash,reinterpret_cast<const BYTE*>(buffer.data()),
                                        static_cast<DWORD>(n),0)!=0,"Windows SHA256 update failed");
        }
        std::array<BYTE,32> digest{};
        DWORD len=static_cast<DWORD>(digest.size());
        require(CryptGetHashParam(hash,HP_HASHVAL,digest.data(),&len,0)!=0&&len==32,"Windows SHA256 finalize failed");
        static constexpr char hexdigits[]="0123456789abcdef";
        std::string result;
        for(auto v:digest){result+=hexdigits[v>>4];result+=hexdigits[v&15];}
        release();
        return result;
    } catch(...) {release();throw;}
}
static XYZ robust_center(const std::vector<XYZ>& values){
    require(!values.empty(),"No coordinates available");
    auto med=[&](int a){
        std::vector<double> v;
        for(const auto& x:values)v.push_back(a==0?x.x:a==1?x.y:x.z);
        auto k=v.begin()+v.size()/2;
        std::nth_element(v.begin(),k,v.end());
        return *k;
    };
    return {med(0),med(1),med(2)};
}
static double distance(XYZ a,XYZ b) {
    return std::hypot(a.x-b.x,std::hypot(a.y-b.y,a.z-b.z));
}
static void selftest(){
    const std::vector<XYZ> values{{1200,34,1360},{1200.005,34.005,1360.005},{1200.001,33.998,1360},{1500,500,1800}};
    const auto center=robust_center(values);
    require(distance(center,{1200,34,1360})<0.02,"Robust median test failed");
    int votes=0;
    for(auto v:values)votes+=distance(v,center)<0.1;
    require(votes==3,"Outlier exclusion test failed");
    std::cout<<"PASS OBSERVER_SELFTEST median, outlier exclusion, no live process accessed\n";
}
static void sample(const fs::path& manifest,const fs::path& csv,int count){
    require(count>=10&&count<=6000,"Sampling count must be 10 to 6000");
    const auto m=load_manifest(manifest);
    ScopedProcess proc(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|PROCESS_VM_READ,FALSE,m.pid));
    require(bool(proc.h),"Target process was closed or read-only permission denied");
    // Windows process handles may resolve PIDs differing in low alignment bits;
    // insist on the canonical PID returned by the OS rather than trusting OpenProcess.
    require(GetProcessId(proc.h)==m.pid,"Requested PID is not the actual target process ID");
    FILETIME creation{},exit{},kernel{},user{};
    require(GetProcessTimes(proc.h,&creation,&exit,&kernel,&user)!=0,"Cannot verify process creation time");
    const uint64_t liveCreated=(uint64_t(creation.dwHighDateTime)<<32)|creation.dwLowDateTime;
    require(liveCreated==m.processCreationFiletime,
            "Process was restarted or PID reused: refusing stale absolute addresses");
    std::array<wchar_t,32768> path{};
    DWORD length=static_cast<DWORD>(path.size());
    require(QueryFullProcessImageNameW(proc.h,0,path.data(),&length)!=0,"Cannot identify game executable");
    const fs::path exe(std::wstring(path.data(),length));
    require(_wcsicmp(exe.filename().c_str(),L"Trackmania.exe")==0,"Target PID does not refer to Trackmania.exe");
    require(sha256(exe)==m.sha256,"Game build changed: refusing old offset manifest");
    fs::create_directories(csv.parent_path());
    std::ofstream out(csv);
    require(bool(out),"Cannot create H: research CSV");
    out<<"sample,elapsed_ms,observed_x,observed_y,observed_z,agreement,readable_copies,"
          "max_copy_error_m,reference_start_horizontal_delta_m,vehicle_state_verified,"
          "candidate_orientation_copies,qraw0,qraw1,qraw2,qraw3,orientation_verified\n";
    out<<std::fixed<<std::setprecision(6);
    int good=0,disagree=0,orientationGood=0;
    XYZ initial{},last{};
    auto now=std::chrono::steady_clock::now;
    const auto begin=now();
    double largestShift=0;
    for(int tick=0;tick<count;++tick) {
        std::vector<XYZ> points;
        struct QuatSample {XYZ position; std::array<double,4> q;};
        std::vector<QuatSample> quatCandidates;
        points.reserve(m.addresses.size());
        quatCandidates.reserve(m.addresses.size());
        for(const auto addr:m.addresses) {
            // Read exactly 28 bytes spanning 4 candidate quaternion floats
            // followed by 3 world-position floats. No other game memory saved.
            float f[7]{};
            SIZE_T got=0;
            if(!ReadProcessMemory(proc.h,reinterpret_cast<LPCVOID>(addr-16),f,sizeof f,&got)||got!=sizeof f)
                continue;
            XYZ p{f[4],f[5],f[6]}; // GBX corroborated XYZ order.
            if(!std::isfinite(p.x)||!std::isfinite(p.y)||!std::isfinite(p.z)||
               std::abs(p.x)>=100000||std::abs(p.y)>=100000||std::abs(p.z)>=100000)
                continue;
            points.push_back(p);
            std::array<double,4> q{f[0],f[1],f[2],f[3]};
            double n2=0;
            for(const double a:q)n2+=a*a;
            // Unit quaternion is a *candidate*, not a confirmed car rotation.
            if(std::isfinite(n2)&&std::abs(n2-1.0)<0.002)
                quatCandidates.push_back({p,q});
        }
        int votes=0;
        XYZ representative{};
        double maxError=0;
        if(points.size()>=3){
            representative=robust_center(points);
            for(const auto& p:points){
                const double err=distance(p,representative);
                votes+=(err<0.5);
                maxError=std::max(maxError,err);
            }
        }
        const bool valid=points.size()>=3 && votes>=3 && votes*2>static_cast<int>(points.size());
        std::vector<std::array<double,4>> qValid;
        if(valid){
            for(const auto& q:quatCandidates)
                if(distance(q.position,representative)<0.5)
                    qValid.push_back(q.q);
        }
        std::array<double,4> qMedian{};
        int qVotes=0;
        if(qValid.size()>=4){
            for(int j=0;j<4;j++){
                std::vector<double> column;
                for(const auto& q:qValid)column.push_back(q[j]);
                auto mid=column.begin()+column.size()/2;
                std::nth_element(column.begin(),mid,column.end());
                qMedian[j]=*mid;
            }
            for(const auto& q:qValid){
                double e=0;
                for(int j=0;j<4;j++)e+=(q[j]-qMedian[j])*(q[j]-qMedian[j]);
                if(e<0.0001)++qVotes;
            }
        }
        const bool quaternionConsensus=qVotes>=4;
        if(quaternionConsensus)orientationGood++;
        const double elapsed=std::chrono::duration<double,std::milli>(now()-begin).count();
        if(valid){
            if(!good)initial=representative;
            last=representative;
            ++good;
            largestShift=std::max(largestShift,distance(initial,representative));
            const double startError=std::hypot(representative.x-m.start.x,representative.z-m.start.z);
            out<<tick<<","<<elapsed<<","<<representative.x<<","<<representative.y<<","
               <<representative.z<<","<<votes<<","<<points.size()<<","<<maxError<<","
               <<startError<<",false,"<<qVotes<<",";
            if(quaternionConsensus)
                out<<qMedian[0]<<","<<qMedian[1]<<","<<qMedian[2]<<","<<qMedian[3];
            else out<<",,,";
            out<<",false\n";
        } else {
            ++disagree;
            out<<tick<<","<<elapsed<<",,,,0,"<<points.size()<<",,,false,0,,,,,false\n";
        }
        if(tick+1<count)Sleep(10);
    }
    std::cout<<"OBSERVED_CANDIDATE_POSE pid="<<m.pid
       <<" requestedSamples="<<count<<" consensusSamples="<<good
       <<" failedConsensusSamples="<<disagree
       <<" candidateCopies="<<m.addresses.size()
       <<" quaternionCandidateConsensusSamples="<<orientationGood
       <<" firstXYZ=("<<initial.x<<","<<initial.y<<","<<initial.z<<")"
       <<" lastXYZ=("<<last.x<<","<<last.y<<","<<last.z<<")"
       <<" maxShift="<<largestShift
       <<" physicsStateVerified=false physics100HzVerified=false"
       <<" output="<<csv.string()<<"\n";
    require(good>=count/2,"Pose candidate replicas mostly disagree or no longer readable");
}
int main(int argc,char**argv)try{
    if(argc==2&&std::string(argv[1])=="--selftest"){selftest();return 0;}
    if(argc!=5||std::string(argv[1])!="--sample")
        throw std::invalid_argument("Usage: tm2020_pose_reader --selftest | --sample <manifest> <output.csv> <count>");
    sample(argv[2],argv[3],std::stoi(argv[4]));
    return 0;
}catch(const std::exception& e){
    std::cerr<<"POSE_OBSERVER_ERROR "<<e.what()<<"\n";
    return 1;
}
