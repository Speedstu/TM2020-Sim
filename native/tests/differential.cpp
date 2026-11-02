// Experimental development-sandbox vs REAL replay state differential test.
// Scores 100Hz tick integration over successive 50ms replay observations.
// This is a NEGATIVE CONTROL: it demonstrates the toy flat dynamics are
// nowhere near a verified Trackmania physics reproduction.
#include "tm2020.hpp"
#include "tm2020/experimental_sim.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs=std::filesystem;
namespace {
constexpr double pi=3.14159265358979323846;
struct Record {
    tm2020::experimental::Pose initial{};
    tm2020::State target{};
    tm2020::State prior{};
    std::array<tm2020::experimental::Action,5> input{};
    int id{};
};
double euclidean(tm2020::Vec3 a,tm2020::Vec3 b){
    return std::hypot(a.x-b.x,std::hypot(a.y-b.y,a.z-b.z));
}
double mae(const std::vector<double>& v){
    if(v.empty())return 0;
    return std::accumulate(v.begin(),v.end(),0.)/double(v.size());
}
double p95(std::vector<double> v){
    if(v.empty())return 0;
    const auto ix=std::min(v.size()-1,static_cast<std::size_t>(v.size()*.95));
    std::nth_element(v.begin(),v.begin()+ix,v.end());
    return v[ix];
}
std::vector<int> ids(const fs::path& dir){
    std::vector<int> results;
    std::ifstream f(dir/"test.txt");
    if(!f)throw std::runtime_error("Missing held-out map index");
    for(std::string s;std::getline(f,s);){
        if(s.empty())continue;
        const int id=std::stoi(s);
        if(id<=0||id>10000000)throw std::runtime_error("Invalid map ID");
        results.push_back(id);
    }
    return results;
}
}

int main(int argc,char**argv)try{
    if(argc!=3){std::cerr<<"Usage: tm2020_differential <native-dataset-dir> <results.csv>\n";return 2;}
    fs::path dir=argv[1],output=argv[2];
    std::vector<Record> records;
    std::size_t skipped=0;
    auto tests=ids(dir);
    for(auto id:tests){
        const auto r=tm2020::Replay::load(dir/(std::to_string(id)+".tmreplay"));
        if(r.states.size()<2)throw std::runtime_error("Insufficient replay samples");
        for(std::size_t i=0;i+1<r.states.size();i++){
            const auto& a=r.states[i],&b=r.states[i+1];
            if(b.time_ms>r.finish_ms)break;
            if(b.time_ms-a.time_ms!=50){++skipped;continue;}
            const double moved=euclidean(a.position,b.position);
            const double physicallyPlausibleDistance=
                std::max(a.speed_kmh,b.speed_kmh)/3.6*.05+8.0;
            if(!std::isfinite(moved)||moved>physicallyPlausibleDistance){
                ++skipped;continue;
            }
            Record rec;
            rec.id=id;
            rec.initial={a.position.x,a.position.y,a.position.z,a.yaw_rad,a.speed_kmh/3.6};
            rec.prior=a;rec.target=b;
            for(int tick=0;tick<5;tick++){
                const auto command=r.input_at(a.time_ms+(tick+1)*10);
                const float steer=static_cast<float>(tm2020::analog_steer_from_raw(command.steer_raw));
                rec.input[tick]={steer,command.gas?1.f:0.f,command.brake?1.f:0.f};
            }
            records.push_back(std::move(rec));
        }
    }
    if(records.size()<1000)throw std::runtime_error("Too few eligible transitions");
    std::vector<tm2020::experimental::Pose> starts;
    starts.reserve(records.size());
    for(const auto& p:records)starts.push_back(p.initial);
    tm2020::experimental::Sandbox sandbox(starts.size());
    sandbox.reset(starts);
    std::vector<tm2020::experimental::Action> actions(starts.size());
    for(int tick=0;tick<5;tick++){
        for(std::size_t i=0;i<records.size();i++)actions[i]=records[i].input[tick];
        sandbox.step(actions);
    }
    std::vector<double> position_error,speed_error,yaw_error,naive_position_error;
    struct Summary{std::vector<double> positions,speeds,yaws;};
    std::map<int,Summary> per_map;
    position_error.reserve(records.size());
    for(std::size_t i=0;i<records.size();i++){
        const auto& p=sandbox.states()[i];
        const auto& r=records[i];
        const tm2020::Vec3 predicted{p.x,p.y,p.z};
        const double posErr=euclidean(predicted,r.target.position);
        const double speedErr=std::abs(p.speed_ms*3.6-r.target.speed_kmh);
        const double yawErr=std::abs(std::remainder(p.yaw-r.target.yaw_rad,2*pi))*180/pi;
        const auto& s=r.prior;
        const tm2020::Vec3 inertial{
            s.position.x+s.velocity.x*.05,
            s.position.y+s.velocity.y*.05,
            s.position.z+s.velocity.z*.05
        };
        position_error.push_back(posErr);
        speed_error.push_back(speedErr);
        yaw_error.push_back(yawErr);
        naive_position_error.push_back(euclidean(inertial,r.target.position));
        auto& d=per_map[r.id];
        d.positions.push_back(posErr);
        d.speeds.push_back(speedErr);
        d.yaws.push_back(yawErr);
    }
    fs::create_directories(output.parent_path());
    std::ofstream out(output);
    if(!out)throw std::runtime_error("Cannot save validation CSV");
    out<<"tmx_id,transitions,position_MAE_m,position_p95_m,speed_MAE_kmh,yaw_MAE_deg\n";
    out<<std::setprecision(7);
    for(auto& [id,s]:per_map){
        out<<id<<','<<s.positions.size()<<','<<mae(s.positions)<<','<<p95(s.positions)
            <<','<<mae(s.speeds)<<','<<mae(s.yaws)<<"\n";
    }
    constexpr double maximumPositionMAE=0.05;
    constexpr double maximumSpeedMAE=0.2;
    constexpr double maximumYawMAE=0.2;
    const bool passes=mae(position_error)<=maximumPositionMAE &&
        mae(speed_error)<=maximumSpeedMAE&&mae(yaw_error)<=maximumYawMAE;
    std::cout<<std::fixed<<std::setprecision(5)
        <<"DIFF_100HZ_SANDBOX maps="<<per_map.size()
        <<" transitions="<<records.size()<<" skipped="<<skipped
        <<" posMAE_m="<<mae(position_error)
        <<" posP95_m="<<p95(position_error)
        <<" naiveInertialPosMAE_m="<<mae(naive_position_error)
        <<" speedMAE_kmh="<<mae(speed_error)
        <<" yawMAE_deg="<<mae(yaw_error)
        <<" nativeTrackmaniaPhysicsValidated="<<(passes?"true":"false")
        <<" output="<<output.string()<<"\n";
    if(passes) {
        // A flat no-collision placeholder cannot be declared high-fidelity
        // even if it accidentally performs well on a small test set.
        std::cout<<"WARNING accidental good one-step fit does NOT validate native collisions and 100Hz physics.\n";
    }
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
