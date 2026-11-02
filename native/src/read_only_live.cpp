#include "tm2020/read_only_live.hpp"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <wincrypt.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <map>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
#include <thread>
#include <chrono>
namespace tm2020::live {
namespace {
void require(bool ok,const char* msg){
    if(!ok)throw std::runtime_error(msg);
}
struct Process {
    HANDLE handle{};
    explicit Process(HANDLE h):handle(h){}
    ~Process(){if(handle)CloseHandle(handle);}
    Process(const Process&)=delete;Process& operator=(const Process&)=delete;
};
}
std::string file_sha256(const std::filesystem::path& p){
    HCRYPTPROV prov{};
    HCRYPTHASH h{};
    require(CryptAcquireContextW(&prov,nullptr,nullptr,PROV_RSA_AES,CRYPT_VERIFYCONTEXT)!=0,
            "Cannot obtain Windows SHA-256 provider");
    try {
        require(CryptCreateHash(prov,CALG_SHA_256,0,0,&h)!=0,"SHA256 start failed");
        std::ifstream f(p,std::ios::binary);
        require(bool(f),"Game executable not readable");
        // The game's PE reserves only 1 MiB for default threads. Keeping this
        // buffer on the stack overflowed an injected worker before its trace.
        std::vector<char> chunk(1<<20);
        while(f) {
            f.read(chunk.data(),chunk.size());
            auto n=f.gcount();
            if(n>0)require(CryptHashData(h,reinterpret_cast<const BYTE*>(chunk.data()),
                                       static_cast<DWORD>(n),0)!=0,"SHA256 chunk failed");
        }
        BYTE raw[32]{};DWORD len=32;
        require(CryptGetHashParam(h,HP_HASHVAL,raw,&len,0)!=0&&len==32,"SHA256 finalize failed");
        const auto hex="0123456789abcdef";
        std::string result;
        for(auto b:raw){result+=hex[b>>4];result+=hex[b&15];}
        CryptDestroyHash(h);CryptReleaseContext(prov,0);
        return result;
    }catch(...){
        if(h)CryptDestroyHash(h);
        CryptReleaseContext(prov,0);
        throw;
    }
}
namespace {
template <typename T>
T med(std::vector<T> values){
    auto middle=values.begin()+values.size()/2;
    std::nth_element(values.begin(),middle,values.end());
    return *middle;
}
double dist(Vec3 a,Vec3 b){
    return std::hypot(a.x-b.x,std::hypot(a.y-b.y,a.z-b.z));
}
std::array<double,4> canonical(std::array<double,4> q){
    const auto it=std::max_element(q.begin(),q.end(),[](double x,double y){
        return std::abs(x)<std::abs(y);
    });
    if(*it<0)for(auto& x:q)x=-x;
    return q;
}
}
struct ReadOnlyObserver::Impl {
    Process process;
    std::uint32_t pid{};
    std::uint64_t creation_time{};
    std::vector<std::uintptr_t> addresses;
    std::vector<std::uintptr_t> visual_addresses;
    double consensus_radius=.5;
    bool reflected_layout_matches_build=false;
    Impl(const std::filesystem::path& path):process(nullptr){
        std::ifstream in(path);
        require(bool(in),"Could not read V3 pose manifest");
        auto get=[&](){
            std::string line;
            if(!std::getline(in,line))throw std::runtime_error("Invalid short manifest");
            return line;
        };
        require(get()=="TM2020_POSE_CANDIDATES_V3","Only current XYZ V3 supported");
        pid=std::stoul(get());
        auto start=std::stoull(get());
        creation_time=start;
        const auto fileSHA=get();
        reflected_layout_matches_build=(fileSHA==visual_state_build_sha256);
        require(fileSHA.size()==64,"SHA must be 64 hex characters");
        require(get()=="XYZ_CANDIDATE_ONLY","Wrong coordinate convention");
        // Authored reference X,Z only, not validated physical altitude.
        (void)std::stod(get());(void)std::stod(get());
        auto n=std::stoul(get());
        require(n>=4&&n<=64,"Candidate count outside safe bounds");
        for(unsigned i=0;i<n;i++){
            auto a=std::stoull(get(),nullptr,16);
            require(a>0x10010 && a<0x00007FFFFFF00000ull,
                    "Noncanonical game memory candidate");
            addresses.push_back(static_cast<std::uintptr_t>(a));
        }
        std::sort(addresses.begin(),addresses.end());
        require(std::adjacent_find(addresses.begin(),addresses.end())==addresses.end(),
                "Duplicate candidate address");
        for(std::size_t i=1;i<addresses.size();i++)
            require((addresses[i]>>12)!=(addresses[i-1]>>12),
                    "Duplicate 4KiB page disguised as independent replica");
        process.handle=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|PROCESS_VM_READ,FALSE,pid);
        require(bool(process.handle),"Game process closed or read-only permission denied");
        require(GetProcessId(process.handle)==pid,"Process PID alias mismatch");
        FILETIME c{},e{},k{},u{};
        require(GetProcessTimes(process.handle,&c,&e,&k,&u)!=0,"Cannot read game process creation timestamp");
        const std::uint64_t created=(std::uint64_t(c.dwHighDateTime)<<32)|c.dwLowDateTime;
        require(created==start,"Stale manifest: game process started again");
        std::array<wchar_t,32768> image{};
        DWORD length=static_cast<DWORD>(image.size());
        require(QueryFullProcessImageNameW(process.handle,0,image.data(),&length)!=0,
                "Cannot identify target executable");
        const auto exe=std::filesystem::path(std::wstring(image.data(),length));
        require(_wcsicmp(exe.filename().c_str(),L"Trackmania.exe")==0,
                "Game executable does not match");
        require(file_sha256(exe)==fileSHA,"Trackmania executable hash not pinned to manifest");
    }
    std::optional<NumericPoseCandidate> sample() const {
        struct Copy {Vec3 pos;std::optional<std::array<double,4>> quat;};
        std::vector<Copy> values;
        values.reserve(addresses.size());
        for(auto addr:addresses){
            float raw[7]{};
            SIZE_T count=0;
            if(!ReadProcessMemory(process.handle,
                                  reinterpret_cast<LPCVOID>(addr-16),
                                  raw,sizeof(raw),&count)||count!=sizeof(raw))continue;
            Vec3 p{raw[4],raw[5],raw[6]};
            if(!std::isfinite(p.x)||!std::isfinite(p.y)||!std::isfinite(p.z)||
               std::abs(p.x)>=100000||std::abs(p.y)>=100000||std::abs(p.z)>=100000)
                continue;
            std::array<double,4> q{raw[0],raw[1],raw[2],raw[3]};
            double norm=0;
            for(auto x:q)norm+=x*x;
            std::optional<std::array<double,4>> oriented;
            if(std::isfinite(norm)&&std::abs(norm-1.)<0.003)
                oriented=canonical(q);
            values.push_back({p,oriented});
        }
        if(values.size()<3)return std::nullopt;
        std::vector<double> x,y,z;
        for(const auto& v:values){
            x.push_back(v.pos.x);y.push_back(v.pos.y);z.push_back(v.pos.z);
        }
        NumericPoseCandidate result;
        result.xyz={med(x),med(y),med(z)};
        for(const auto& v:values)
            if(dist(v.pos,result.xyz)<consensus_radius)result.position_agreeing_copies++;
        result.readable_copies=static_cast<std::uint32_t>(values.size());
        if(result.position_agreeing_copies<3||
           result.position_agreeing_copies*2<=values.size())
            return std::nullopt;
        std::vector<std::array<double,4>> quats;
        for(const auto& v:values)
            if(v.quat && dist(v.pos,result.xyz)<0.5)quats.push_back(*v.quat);
        if(quats.size()>=4) {
            std::array<double,4> q{};
            for(int i=0;i<4;i++){
                std::vector<double> axis;
                for(const auto& value:quats)axis.push_back(value[i]);
                q[i]=med(axis);
            }
            for(const auto& candidate:quats){
                double error=0;
                for(int i=0;i<4;i++)error+=(q[i]-candidate[i])*(q[i]-candidate[i]);
                if(error<0.0001)result.orientation_agreeing_copies++;
            }
            if(result.orientation_agreeing_copies>=4)
                result.raw_quaternion_candidate=Quaternion{q[0],q[1],q[2],q[3]};
        }
        // Defaults stay FALSE: no claim of authoritative physics or 100Hz.
        return result;
    }
};
ReadOnlyObserver::ReadOnlyObserver(const std::filesystem::path& manifest,double radius)
    :impl_(std::make_unique<Impl>(manifest)) {
    require(std::isfinite(radius)&&radius>0&&radius<=5,"Invalid position consensus radius");
    impl_->consensus_radius=radius;
}
ReadOnlyObserver::~ReadOnlyObserver()=default;
ReadOnlyObserver::ReadOnlyObserver(ReadOnlyObserver&&) noexcept=default;
ReadOnlyObserver& ReadOnlyObserver::operator=(ReadOnlyObserver&&) noexcept=default;
std::optional<NumericPoseCandidate> ReadOnlyObserver::poll() const {
    if(!impl_)return std::nullopt;
    return impl_->sample();
}
std::uint32_t ReadOnlyObserver::process_id() const noexcept {
    return impl_?impl_->pid:0;
}
std::size_t ReadOnlyObserver::source_count() const noexcept {
    return impl_?impl_->addresses.size():0;
}
std::vector<std::optional<ReflectedVisualState>> ReadOnlyObserver::poll_visual_copies() const {
    std::vector<std::optional<ReflectedVisualState>> result;
    if(!impl_)return result;
    if(!impl_->reflected_layout_matches_build)return result;
    const auto& sources=impl_->visual_addresses.empty()?impl_->addresses:impl_->visual_addresses;
    result.reserve(sources.size());
    for(auto address:sources){
        std::array<std::byte,visual_state_bytes> raw{};SIZE_T count{};
        if(address<visual_position_offset ||
           !ReadProcessMemory(impl_->process.handle,reinterpret_cast<LPCVOID>(address-visual_position_offset),
                              raw.data(),raw.size(),&count)||count!=raw.size())result.emplace_back();
        else result.push_back(decode_visual_state(raw));
    }
    return result;
}
std::optional<FreshVisualSample> ReadOnlyObserver::poll_fresh_visual(std::optional<Vec3> anchor,bool active) const {
    const auto copies=poll_visual_copies();
    return select_fresh_visual(copies,anchor,active);
}
bool ReadOnlyObserver::restore_visual_sources(const std::filesystem::path& path){
    if(!impl_||!impl_->reflected_layout_matches_build)return false;
    std::ifstream in(path);std::string tag,sha;std::uint64_t created{};std::uint32_t pid{};std::size_t n{};
    if(!(in>>tag>>pid>>created>>sha>>n)||tag!="TM2020_VISUAL_CACHE_V1"||pid!=impl_->pid||created!=impl_->creation_time||
       sha!=visual_state_build_sha256||n<3||n>64)return false;
    std::vector<std::uintptr_t> addresses(n);
    for(auto& a:addresses)if(!(in>>std::hex>>a)||a<=0x10050||a>=0x00007FFFFFF00000ull)return false;
    std::sort(addresses.begin(),addresses.end());
    for(std::size_t i=1;i<n;i++)if((addresses[i]>>12)==(addresses[i-1]>>12))return false;
    auto previous=std::move(impl_->visual_addresses);impl_->visual_addresses=std::move(addresses);
    const auto a=poll_fresh_visual();std::this_thread::sleep_for(std::chrono::milliseconds(60));const auto b=poll_fresh_visual();
    if(!a||!b||a->state.race_start_time!=b->state.race_start_time||
       static_cast<std::int32_t>(b->clock_candidate_ms-a->clock_candidate_ms)<=0||
       dist(a->state.position,b->state.position)>2.){
        impl_->visual_addresses=std::move(previous);return false;
    }
    return true;
}
void ReadOnlyObserver::save_visual_sources(const std::filesystem::path& path) const {
    require(impl_&&impl_->reflected_layout_matches_build&&impl_->visual_addresses.size()>=3,"No discovered visual sources to cache");
    std::ofstream out(path);require(bool(out),"Cannot create visual cache");
    out<<"TM2020_VISUAL_CACHE_V1\n"<<impl_->pid<<'\n'<<impl_->creation_time<<'\n'<<visual_state_build_sha256<<'\n'<<impl_->visual_addresses.size()<<'\n';
    for(auto address:impl_->visual_addresses)out<<std::hex<<address<<'\n';
    out.flush();require(bool(out),"Visual cache write failed");
}
std::size_t ReadOnlyObserver::discover_visual_states(std::size_t max_mb,double radius,std::optional<Vec3> known_start){
    require(impl_&&impl_->reflected_layout_matches_build,"Reflected offsets do not match this executable hash");
    require(max_mb>0&&max_mb<=16384&&std::isfinite(radius)&&radius>0&&radius<=10,"Invalid reflected discovery bounds");
    if(known_start)require(std::isfinite(known_start->x)&&std::isfinite(known_start->y)&&std::isfinite(known_start->z),"Invalid known start");
    const auto numeric=poll();require(known_start||numeric,"Need known map start or live pose consensus before reflected discovery");
    const Vec3 anchor=known_start?*known_start:numeric->xyz;
    // This build's reflected layout is not portable to arbitrary future builds.
    // The existing manifest has already SHA-pinned the opened executable.
    struct Candidate{std::uintptr_t address;std::uint32_t clock;};
    std::map<std::uintptr_t,Candidate> pages;
    std::vector<std::byte> block((1<<20)+visual_state_bytes);
    std::uintptr_t address=0x10000;std::uint64_t scanned=0;MEMORY_BASIC_INFORMATION r{};
    while(VirtualQueryEx(impl_->process.handle,reinterpret_cast<LPCVOID>(address),&r,sizeof(r))==sizeof(r)){
        const auto base=reinterpret_cast<std::uintptr_t>(r.BaseAddress),end=base+r.RegionSize;
        if(end<=address)break;address=end;
        if(r.State!=MEM_COMMIT||r.Type!=MEM_PRIVATE||(r.Protect&(PAGE_NOACCESS|PAGE_GUARD)))continue;
        for(auto p=base;p<end&&scanned<max_mb*1048576ull;){
            const auto n=static_cast<std::size_t>(std::min<std::uint64_t>({block.size(),end-p,max_mb*1048576ull-scanned}));
            SIZE_T got{};
            if(ReadProcessMemory(impl_->process.handle,reinterpret_cast<LPCVOID>(p),block.data(),n,&got)){
                for(std::size_t at=0x50;at+0x310<=got;at+=4){
                    std::uint32_t tag{};std::memcpy(&tag,block.data()+at-0x50,sizeof(tag));
                    if(tag!=0x02000006)continue;
                    float xyz[3]{};std::memcpy(xyz,block.data()+at,12);
                    if(!std::isfinite(xyz[0])||!std::isfinite(xyz[1])||!std::isfinite(xyz[2])||
                       std::abs(xyz[0]-anchor.x)>radius||std::abs(xyz[1]-anchor.y)>radius||std::abs(xyz[2]-anchor.z)>radius)continue;
                    const auto s=decode_visual_state(std::span(block.data()+at-0x50,visual_state_bytes));
                    if(!s||s->raw_header_words[0]!=0x02000006||s->gear<0||s->gear>8)continue;
                    bool wheels=true;for(const auto& w:s->wheels)
                        wheels&=w.damper_length>=0&&w.damper_length<3&&std::abs(w.steer_angle)<4&&w.icing>=0&&w.icing<=1.01;
                    if(!wheels)continue;
                    const auto page=(p+at)>>12;const Candidate candidate{p+at,s->raw_header_words[3]};
                    const auto previous=pages.find(page);
                    if(previous==pages.end()||static_cast<std::int32_t>(candidate.clock-previous->second.clock)>0)pages[page]=candidate;
                }
            }
            scanned+=n;const auto advance=n>visual_state_bytes?n-visual_state_bytes:n;if(!advance)break;p+=advance;
        }
        if(scanned>=max_mb*1048576ull)break;
    }
    std::vector<Candidate> selected;for(const auto& [page,c]:pages){(void)page;selected.push_back(c);}
    std::sort(selected.begin(),selected.end(),[](auto a,auto b){return static_cast<std::int32_t>(a.clock-b.clock)>0;});
    if(selected.size()>64)selected.resize(64);
    require(selected.size()>=3,"Too few reflected state pages; previous sources preserved");
    impl_->visual_addresses.clear();for(auto c:selected)impl_->visual_addresses.push_back(c.address);
    return impl_->visual_addresses.size();
}
}
