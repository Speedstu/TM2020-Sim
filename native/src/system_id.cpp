// Trackmania 2020 empirical system identification from native observed replays.
// No invented friction constants: only differential measurements. Output to CSV.
// Samples are at 50 ms; these are OBSERVED acceleration/yaw changes, not
// native 100 Hz engine parameters. Excludes obvious teleport discontinuities.
#include "tm2020.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <numeric>
#include <string>
#include <tuple>
#include <vector>

namespace fs=std::filesystem;
namespace {
constexpr double pi=3.1415926535897932384626;
struct Key {
    std::string surface,control;
    int speed_bin{};
    bool operator<(const Key& b) const{
        return std::tie(surface,control,speed_bin)<std::tie(b.surface,b.control,b.speed_bin);
    }
};
struct Group {
    std::vector<double> accel, yaw_rate,steer,speed;
    std::size_t excluded{0};
};
double dist(const tm2020::Vec3& a,const tm2020::Vec3& b){
    auto dx=a.x-b.x,dy=a.y-b.y,dz=a.z-b.z;
    return std::sqrt(dx*dx+dy*dy+dz*dz);
}
std::string classify_surface(const tm2020::State& state){
    if(!state.ground_contact)return "airborne";
    std::array<int,256> count{};
    for(auto v:state.contact_materials)count[v]++;
    int top=0;for(int i=1;i<256;i++)if(count[i]>count[top])top=i;
    // Need >=3 wheels; mixed surfaces are a distinct category.
    if(count[top]<3)return "mixed";
    switch(top){
        case 1:case 2:return "road";
        case 3:return "dirt";
        case 4:return "grass";
        case 5:return "ice";
        case 6:return "metal";
        case 7:return "plastic";
        case 8:return "rubber";
        case 9:return "sand";
        case 10:return "wood";
        case 11:return "water";
        default:return "unknown";
    }
}
std::string classify_control(const tm2020::State& s){
    const bool straighish=std::abs(s.controls.steer)<0.12;
    if(s.controls.brake>=0.7&&s.controls.gas<0.5)
        return straighish?"straight_brake":"turn_brake";
    if(s.controls.gas>=0.7&&s.controls.brake<0.25)
        return straighish?"straight_gas":"turn_gas";
    if(s.controls.gas<0.2&&s.controls.brake<0.2)
        return straighish?"straight_coast":"turn_coast";
    return "mixed_controls";
}
double median(std::vector<double>& vals){
    if(vals.empty())return 0;
    auto mid=vals.begin()+vals.size()/2;
    std::nth_element(vals.begin(),mid,vals.end());
    double m=*mid;
    if(vals.size()%2==0){
        auto before=std::max_element(vals.begin(),mid);
        m=(m+*before)/2;
    }
    return m;
}
struct Stat {double med{}, p10{},p90{},mean{};};
Stat stats(std::vector<double> values){
    if(values.empty())return {};
    const auto mean=std::accumulate(values.begin(),values.end(),0.)/values.size();
    std::sort(values.begin(),values.end());
    auto quant=[&](double q) {
        const auto index=q*(values.size()-1);
        auto lo=(std::size_t)index;
        const auto hi=std::min(lo+1,values.size()-1);
        return values[lo]*(1-(index-lo))+values[hi]*(index-lo);
    };
    return {quant(0.5),quant(0.1),quant(0.9),mean};
}
}
int main(int argc,char**argv)try{
    if(argc!=3){std::cerr<<"Usage: tm2020_system_id <native-dataset-dir> <out.csv>\n";return 2;}
    const fs::path folder=argv[1],target=argv[2];
    std::map<Key,Group> groups;
    std::size_t maps=0,accepted=0,skipped=0,all=0;
    for(auto& file:fs::directory_iterator(folder)){
        if(file.path().extension()!=".tmreplay")continue;
        auto replay=tm2020::Replay::load(file.path());
        auto& states=replay.states;
        ++maps;
        for(std::size_t i=1;i<states.size();i++){
            const auto& a=states[i-1];
            const auto& b=states[i];
            if(b.time_ms>replay.finish_ms)break;
            ++all;
            const double dt=(b.time_ms-a.time_ms)*.001;
            if(dt<0.049||dt>0.051){++skipped;continue;}
            const double d=dist(a.position,b.position);
            const double speed_max=std::max(a.speed_kmh,b.speed_kmh)/3.6;
            // Mark teleport, invalid inter-frame acceleration and extreme
            // rotations explicitly as exclusions; not invented observations.
            const double accel=(b.speed_kmh-a.speed_kmh)/dt;
            const double yaw_rate=std::remainder(b.yaw_rad-a.yaw_rad,2*pi)/dt;
            if(!std::isfinite(d)||d>speed_max*dt+8 ||
               std::abs(accel)>350. || std::abs(yaw_rate)>20.){
                ++skipped;continue;
            }
            const auto surface=classify_surface(a);
            const auto control=classify_control(a);
            const int bin=static_cast<int>(a.speed_kmh/50.)*50;
            Key key{surface,control,std::clamp(bin,0,1000)};
            auto& g=groups[key];
            g.accel.push_back(accel);
            g.yaw_rate.push_back(yaw_rate*180./pi);
            g.steer.push_back(a.controls.steer);
            g.speed.push_back(a.speed_kmh);
            ++accepted;
        }
    }
    fs::create_directories(target.parent_path());
    std::ofstream csv(target);
    if(!csv)throw std::runtime_error("Could not create CSV on H:");
    csv<<"surface,control,speed_bin_kmh,samples,median_speed_kmh,"
          "acceleration_median_kmh_per_second,acceleration_p10,acceleration_p90,"
          "yaw_median_deg_per_second,yaw_p10,yaw_p90,median_steer\n";
    csv<<std::fixed<<std::setprecision(6);
    for(const auto& [key,g]:groups){
        auto acc=stats(g.accel),yaw=stats(g.yaw_rate),steer=stats(g.steer),speed=stats(g.speed);
        csv<<key.surface<<','<<key.control<<','<<key.speed_bin<<','
           <<g.accel.size()<<','<<speed.med<<','
           <<acc.med<<','<<acc.p10<<','<<acc.p90<<','
           <<yaw.med<<','<<yaw.p10<<','<<yaw.p90<<','<<steer.med<<'\n';
    }
    if(maps<5||accepted<1000)
        throw std::runtime_error("Insufficient diverse real replay data");
    std::cout<<"PASS SYSTEM_ID maps="<<maps<<" examined="<<all
             <<" accepted="<<accepted<<" excluded="<<skipped
             <<" bins="<<groups.size()<<" CSV="<<target.string()<<"\n";
    std::cout<<"CAUTION: 50ms replay statistics, NOT Trackmania 100Hz physics constants.\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"ERROR "<<e.what()<<"\n";return 1;}
