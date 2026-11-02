#include "tm2020.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cmath>
#include <cstring>
#include <fstream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <type_traits>
#include <utility>

namespace tm2020 {
namespace {
class Reader {
public:
    explicit Reader(const std::filesystem::path& p):stream_(p,std::ios::binary){
        if(!stream_)throw std::runtime_error("Cannot open binary dataset: "+p.string());
        stream_.seekg(0,std::ios::end);
        auto end=stream_.tellg();
        if(end<0 || end>static_cast<std::streamoff>(512ull*1024ull*1024ull))
            throw std::runtime_error("Data file too large or invalid");
        size_=static_cast<std::uint64_t>(end);
        stream_.seekg(0,std::ios::beg);
    }
    void bytes(void* p,std::size_t n){
        if(n>size_-offset_)throw std::runtime_error("Truncated native dataset");
        if(!stream_.read(static_cast<char*>(p),static_cast<std::streamsize>(n)))
            throw std::runtime_error("Binary dataset read failure");
        offset_+=n;
    }
    std::uint8_t u8(){std::uint8_t v{};bytes(&v,sizeof(v));return v;}
    std::int8_t i8(){return static_cast<std::int8_t>(u8());}
    std::uint16_t u16(){
        std::uint16_t v=u8();
        v|=static_cast<std::uint16_t>(u8())<<8;
        return v;
    }
    std::int16_t i16(){return static_cast<std::int16_t>(u16());}
    std::uint32_t u32(){std::uint32_t out=0;for(int i=0;i<4;i++)out|=std::uint32_t(u8())<<(8*i);return out;}
    std::int32_t i32(){return static_cast<std::int32_t>(u32());}
    std::uint64_t u64(){std::uint64_t out=0;for(int i=0;i<8;i++)out|=std::uint64_t(u8())<<(8*i);return out;}
    double f64(){
        const auto raw=u64();
        const auto value=std::bit_cast<double>(raw);
        if(!std::isfinite(value))throw std::runtime_error("Nonfinite vector/float value");
        return value;
    }
    Vec3 vec3(){return {f64(),f64(),f64()};}
    std::string str(){
        std::uint16_t n=u16();
        if(n>32768)throw std::runtime_error("Overlong native string");
        std::string s(n,'\0');bytes(s.data(),n);return s;
    }
    void magic(const char* wanted){
        char head[8];bytes(head,8);
        if(std::memcmp(head,wanted,8)!=0)throw std::runtime_error("Wrong dataset magic/version");
    }
    bool done()const noexcept{return offset_==size_;}
private:
    std::ifstream stream_;
    std::uint64_t size_{},offset_{};
};
void version_one(Reader& r){
    if(r.u32()!=1)throw std::runtime_error("Unsupported native dataset format");
}
}

Map Map::load(const std::filesystem::path& path){
    Reader r(path);r.magic("TMRMAP1\0");
    version_one(r);
    auto nb=r.u32(),ni=r.u32();
    if(nb>1'000'000u||ni>1'000'000u)throw std::runtime_error("Map exceeds capacity");
    Map out;out.uid=r.str();out.name=r.str();
    if(out.uid.empty())throw std::runtime_error("Missing map UID");
    out.blocks.reserve(nb);
    out.items.reserve(ni);
    for(std::uint32_t k=0;k<nb;k++){
        Block b;
        b.name=r.str();
        for(auto& x:b.grid)x=r.i32();
        b.direction=r.str();
        auto flags=r.u8();
        b.is_ground=(flags&1)!=0;
        b.is_free=(flags&2)!=0;
        b.has_position=r.u8()!=0;
        b.has_rotation=r.u8()!=0;
        if(b.has_position)b.position=r.vec3();
        if(b.has_rotation)b.yaw_pitch_roll=r.vec3();
        out.blocks.push_back(std::move(b));
    }
    for(std::uint32_t k=0;k<ni;k++){
        Item it;it.model=r.str();it.position=r.vec3();it.yaw_pitch_roll=r.vec3();
        out.items.push_back(std::move(it));
    }
    if(!r.done())throw std::runtime_error("Trailing bytes in native map dataset");
    return out;
}
std::vector<CourseMarker> Map::course_markers() const {
    std::vector<CourseMarker> out;
    // Native Stadium grid XY/Z dimension: horizontal 32m cells.
    // Block vertical grid coordinate is not an authoritative tire height.
    constexpr double cell=32.0;
    for (const auto& block:blocks) {
        CourseMarkerKind kind{};
        if(block.name=="RoadTechStart" || block.name=="RoadStart"){
            kind=CourseMarkerKind::Start;
        } else if(block.name.find("Checkpoint")!=std::string::npos){
            kind=CourseMarkerKind::Checkpoint;
        } else if(block.name.find("Finish")!=std::string::npos) {
            kind=CourseMarkerKind::Finish;
        } else {
            continue;
        }
        Vec3 pos{(block.grid[0]+0.5)*cell,0.0,(block.grid[2]+0.5)*cell};
        bool validY=false;
        if(block.has_position) {
            pos=block.position;
            validY=true;
        }
        out.push_back({kind,pos,block.name,validY,false});
    }
    for(const auto& item:items) {
        CourseMarkerKind kind{};
        if(item.model.find("GateFinish")!=std::string::npos){
            kind=CourseMarkerKind::Finish;
        } else if(item.model.find("GateCheckpoint")!=std::string::npos) {
            kind=CourseMarkerKind::Checkpoint;
        } else if(item.model.find("GateStart")!=std::string::npos) {
            kind=CourseMarkerKind::Start;
        } else continue;
        out.push_back({kind,item.position,item.model,true,true});
    }
    return out;
}

Replay Replay::load(const std::filesystem::path& path){
    Reader r(path);r.magic("TMRDSV1\0");
    version_one(r);
    const auto n=r.u32(),e=r.u32();
    if(n>100000u||e>1000000u)throw std::runtime_error("Replay counts exceed capacity");
    Replay out;out.finish_ms=r.i32();out.sampling_interval_ms=r.i32();
    out.uid=r.str();out.name=r.str();
    if(out.uid.empty()||out.sampling_interval_ms<=0||out.finish_ms<0)
        throw std::runtime_error("Bad replay metadata");
    out.states.reserve(n);out.changes.reserve(e);
    std::int32_t last=std::numeric_limits<std::int32_t>::min();
    for(std::uint32_t i=0;i<n;i++){
        State s;s.time_ms=r.i32();
        if(s.time_ms<=last)throw std::runtime_error("Vehicle samples not monotonically increasing");
        last=s.time_ms;
        s.position=r.vec3();
        s.rotation={r.f64(),r.f64(),r.f64(),r.f64()};
        s.velocity=r.vec3();
        s.speed_kmh=r.f64();
        s.yaw_rad=r.f64();
        s.controls.steer=r.f64();
        s.controls.gas=r.f64();
        s.controls.brake=r.f64();
        s.side_speed=r.f64();
        for(auto& material:s.contact_materials)material=r.u8();
        s.ground_contact=r.u8()!=0;
        out.states.push_back(s);
    }
    last=std::numeric_limits<std::int32_t>::min();
    for(std::uint32_t i=0;i<e;i++){
        InputEvent ev;
        ev.time_ms=r.i32();
        ev.steer_raw=r.i16();
        ev.gas=r.i8();ev.brake=r.i8();ev.respawn=r.i8();
        if(ev.time_ms<last)throw std::runtime_error("Input event times not monotonic");
        last=ev.time_ms;
        if(ev.steer_raw!=std::numeric_limits<std::int16_t>::min() &&
            (ev.steer_raw< -128 || ev.steer_raw>127))throw std::runtime_error("Steer outside range");
        if(ev.gas>1||ev.gas<-1||ev.brake>1||ev.brake<-1||ev.respawn>1||ev.respawn<-1)
            throw std::runtime_error("Invalid button state");
        out.changes.push_back(ev);
    }
    if(!r.done())throw std::runtime_error("Trailing bytes in native replay dataset");
    InputCommand current{};
    out.input_prefix.reserve(out.changes.size());
    for(const auto& e:out.changes){
        if(e.steer_raw!=std::numeric_limits<std::int16_t>::min())current.steer_raw=e.steer_raw;
        if(e.gas!=-1)current.gas=e.gas==1;
        if(e.brake!=-1)current.brake=e.brake==1;
        if(e.respawn!=-1)current.respawn=e.respawn==1;
        out.input_prefix.push_back(current);
    }
    return out;
}
const State& Replay::recorded_at(std::int32_t time_ms)const{
    if(states.empty()||time_ms<states.front().time_ms||time_ms>states.back().time_ms)
        throw std::out_of_range("Time outside recorded states");
    const auto it=std::upper_bound(states.begin(),states.end(),time_ms,
                                  [](auto query,const State& sample){return query<sample.time_ms;});
    return *(it-1);
}
InputCommand Replay::input_at(std::int32_t time_ms)const{
    // Preserve repeated events at identical times; later ones take precedence.
    const auto it=std::upper_bound(changes.begin(),changes.end(),time_ms,
                                  [](auto t,const InputEvent& e){return t<e.time_ms;});
    if(it==changes.begin())return {};
    return input_prefix[static_cast<std::size_t>(it-changes.begin()-1)];
}
std::size_t Replay::in_race_transitions()const{
    std::size_t result=0;
    for(std::size_t i=1;i<states.size();++i){
        if(states[i].time_ms>finish_ms)break;
        if(states[i].time_ms-states[i-1].time_ms==sampling_interval_ms)++result;
    }
    return result;
}
BCFeatures bc_features(const tm2020::State& s,const tm2020::State& future) {
    const double speed=s.speed_kmh/100.;
    const double dx=(future.position.x-s.position.x)/50.;
    const double dy=(future.position.y-s.position.y)/50.;
    const double dz=(future.position.z-s.position.z)/50.;
    const double yaw=s.yaw_rad;
    const double co=std::cos(yaw),si=std::sin(yaw);
    const double forward=dx*co+dz*si;
    const double lateral=-dx*si+dz*co;
    const double diff=std::remainder(future.yaw_rad-yaw,6.283185307179586476925286766559);
    double mats[6]{};
    for(const auto m:s.contact_materials){
        if(m==1||m==2)mats[0]+=0.25; // asphalt+concrete
        else if(m==3||m==8||m==9)mats[1]+=0.25; // dirt, rubber, sand
        else if(m==4)mats[2]+=0.25;
        else if(m==5)mats[3]+=0.25;
        else if(m==6||m==7)mats[4]+=0.25;
        else mats[5]+=0.25;
    }
    return {1.,speed,speed*speed,s.velocity.x/100.,s.velocity.y/100.,s.velocity.z/100.,
            s.side_speed/80.,co,si,forward,lateral,dy,dx,dz,diff,
            (future.speed_kmh-s.speed_kmh)/100.,s.ground_contact?1.:0., 
            mats[0],mats[1],mats[2],mats[3],mats[4],mats[5],lateral*speed};
}

Dataset::Dataset(Map layout,Replay observed):map_(std::move(layout)),replay_(std::move(observed)){
    if(map_.uid!=replay_.uid)throw std::invalid_argument("Replay/map UID mismatch");
}
double analog_steer_from_raw(std::int16_t raw){
    if(raw< -128||raw>127)throw std::out_of_range("Raw steering outside signed byte range");
    return (2.*raw-1.)/255.;
}
double live_steer_from_raw(std::int16_t raw){
    if(raw< -128||raw>127)throw std::out_of_range("Raw steering outside signed byte range");
    return std::clamp(raw/127.,-1.,1.);
}
BCPolicy BCPolicy::load(const std::filesystem::path& file) {
    std::ifstream in(file,std::ios::binary);
    if(!in)throw std::runtime_error("Cannot open native BC policy checkpoint");
    char magic[8]{};
    in.read(magic,8);
    if(!in || std::memcmp(magic,"TMBC001\0",8)!=0)
        throw std::runtime_error("Not a TM2020 BC checkpoint v1");
    BCPolicy p;
    auto value=[&in]()->double {
        double x{};
        if(!in.read(reinterpret_cast<char*>(&x),8)||!std::isfinite(x))
            throw std::runtime_error("Truncated/nonfinite BC checkpoint");
        return x;
    };
    for(auto& x:p.mean_)x=value();
    for(auto& x:p.stddev_) {
        x=value();
        if(x<=0)throw std::runtime_error("Invalid normalization scale");
    }
    for(auto& row:p.weights_)for(auto& weight:row)weight=value();
    if(in.peek()!=std::ifstream::traits_type::eof())
        throw std::runtime_error("Unexpected trailing BC checkpoint data");
    return p;
}
Controls BCPolicy::predict(const State& now,const State& desired_future) const {
    // This cannot be treated as a free-driving policy without a trajectory planner.
    const auto x=bc_features(now,desired_future);
    std::array<double,3> out{};
    for(int i=0;i<24;i++) {
        const double feature=(x[i]-mean_[i])/stddev_[i];
        for(int j=0;j<3;j++)out[j]+=feature*weights_[i][j];
    }
    return {std::clamp(out[0],-1.,1.),
            std::clamp(out[1],0.,1.),
            std::clamp(out[2],0.,1.)};
}

CollisionWorld::CollisionWorld(const std::filesystem::path& p){
    const auto path=p.string();
    handle_=tm_world_open(path.c_str());
    if(!handle_)throw std::runtime_error(std::string("Invalid partial mesh: ")+tm_last_error());
}
CollisionWorld::~CollisionWorld(){if(handle_)tm_world_close(handle_);}
CollisionWorld::CollisionWorld(CollisionWorld&& rhs) noexcept:handle_(std::exchange(rhs.handle_,nullptr)){}
CollisionWorld& CollisionWorld::operator=(CollisionWorld&& rhs) noexcept{
    if(this!=&rhs){
        if(handle_)tm_world_close(handle_);
        handle_=std::exchange(rhs.handle_,nullptr);
    }
    return *this;
}
std::size_t CollisionWorld::triangle_count()const noexcept{
    return handle_?static_cast<std::size_t>(tm_world_triangle_count(handle_)):0;
}
void CollisionWorld::raycast(const double* rays,std::size_t n,double* out)const {
    if(!handle_)throw std::runtime_error("Collision world closed");
    if(n>static_cast<std::size_t>(std::numeric_limits<long long>::max()))
        throw std::invalid_argument("Too many rays");
    const auto status=tm_world_cast_batch(handle_,rays,static_cast<long long>(n),out);
    if(status)throw std::runtime_error(std::string("Native raycast failure: ")+tm_last_error());
}
} // namespace tm2020
