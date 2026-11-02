// Trackmania 2020 empirical 50ms integration/timestamp system-ID diagnostic.
// Fit a *single scalar effective dt* on training maps, evaluate on unseen maps.
// Do not mistake this for a learned or exact Trackmania physics integrator.
#include "tm2020.hpp"
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs=std::filesystem;
namespace {
struct Pair {tm2020::State a,b;};
std::vector<int> indices(const fs::path& dir,const char* name){
    std::vector<int> ret;
    std::ifstream f(dir/name);
    if(!f)throw std::runtime_error("Missing train/test dataset index");
    for(std::string s;std::getline(f,s);)if(!s.empty())ret.push_back(std::stoi(s));
    return ret;
}
double len(tm2020::Vec3 x){
    return std::sqrt(x.x*x.x+x.y*x.y+x.z*x.z);
}
tm2020::Vec3 sub(tm2020::Vec3 a,tm2020::Vec3 b) {
    return {a.x-b.x,a.y-b.y,a.z-b.z};
}
tm2020::Vec3 add(tm2020::Vec3 a,tm2020::Vec3 b) {
    return {a.x+b.x,a.y+b.y,a.z+b.z};
}
tm2020::Vec3 mul(tm2020::Vec3 a,double f){
    return {a.x*f,a.y*f,a.z*f};
}
double dot(tm2020::Vec3 a,tm2020::Vec3 b){
    return a.x*b.x+a.y*b.y+a.z*b.z;
}
std::vector<Pair> load(const fs::path& dir,const std::vector<int>& mapIds){
    std::vector<Pair> pairs;
    for(int id:mapIds){
        auto r=tm2020::Replay::load(dir/(std::to_string(id)+".tmreplay"));
        for(std::size_t i=1;i<r.states.size();i++){
            const auto& a=r.states[i-1],&b=r.states[i];
            if(b.time_ms>r.finish_ms)break;
            if(b.time_ms-a.time_ms!=50)continue;
            if(len(sub(b.position,a.position))>std::max(a.speed_kmh,b.speed_kmh)/3.6*0.05+8)
                continue;
            pairs.push_back({a,b});
        }
    }
    return pairs;
}
double error(const std::vector<Pair>& r,double dt,int mode){
    double sum=0;
    for(const auto& p:r){
        const auto velocity=mode==2
            ?mul(add(p.a.velocity,p.b.velocity),0.5) // oracle future velocity
            :p.a.velocity;
        const auto predicted=add(p.a.position,mul(velocity,dt));
        sum+=len(sub(predicted,p.b.position));
    }
    return sum/r.size();
}
}
int main(int argc,char**argv)try{
    if(argc!=2){std::cerr<<"Usage: tm2020_integrator_probe <native-dataset-dir>\n";return 2;}
    fs::path dir=argv[1];
    auto train=load(dir,indices(dir,"train.txt"));
    auto test=load(dir,indices(dir,"test.txt"));
    if(train.size()<1000||test.size()<500)throw std::runtime_error("Insufficient train/test observations");
    double numerator=0,denominator=0;
    for(auto& p:train){
        const auto disp=sub(p.b.position,p.a.position);
        numerator+=dot(p.a.velocity,disp);
        denominator+=dot(p.a.velocity,p.a.velocity);
    }
    if(denominator<=0)throw std::runtime_error("Invalid velocity observations");
    const double dt=numerator/denominator;
    auto trainErr=error(train,dt,1);
    auto testErr=error(test,dt,1);
    auto reference=error(test,0.05,1);
    auto oracle=error(test,0.05,2);
    if(!std::isfinite(dt)||!std::isfinite(testErr)||dt<0.01||dt>0.1)
        throw std::runtime_error("Unreasonable inferred timebase");
    std::cout<<std::fixed<<std::setprecision(7)
        <<"PASS TIMING_PROBE train_rows="<<train.size()
        <<" heldout_rows="<<test.size()
        <<" fittedEffectiveSeconds="<<dt
        <<" groundTruthNominalSeconds=0.0500000"
        <<" fittedTrainPositionMAE_m="<<trainErr
        <<" fittedTestPositionMAE_m="<<testErr
        <<" fixed50msTestPositionMAE_m="<<reference
        <<" oracleMidpointVelocityTestMAE_m="<<oracle
        <<" fullNativePhysicsAvailable=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
