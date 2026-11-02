#include "tm2020/experimental_sim.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>
using namespace tm2020::experimental;
void require(bool ok,const char* m){if(!ok)throw std::runtime_error(m);}
int main(int argc,char**argv)try{
    const std::size_t count=argc>1?std::stoull(argv[1]):65536;
    const int steps=argc>2?std::stoi(argv[2]):1000;
    require(count>0&&count<=2'000'000&&steps>=1&&steps<=20000,"Invalid benchmark sizes");
    require(!faithful_trackmania_physics,"Sandbox must never claim Trackmania fidelity");
    Sandbox world(count);
    std::vector<Pose> initial(count);
    std::vector<Action> action(count);
    for(std::size_t i=0;i<count;i++){
        initial[i]={0,10,0,0,static_cast<double>(i%20)};
        action[i]={float(int(i%3)-1)*0.2f,0.8f,0.0f};
    }
    world.reset(initial);
    auto saved=world.snapshot();
    require(saved.tick==0,"Fresh reset tick != 0");
    const auto start=std::chrono::steady_clock::now();
    for(int t=0;t<steps;t++)world.step(action);
    const auto elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    require(world.tick()==std::uint64_t(steps),"Wrong tick count");
    auto final=world.snapshot();
    double sum=0;
    for(const auto& s:world.states()){
        require(std::isfinite(s.x)&&std::isfinite(s.z)&&s.speed_ms>=0,"Nonfinite model");
        require(s.y==10,"Kinematic flat plane Y should be unchanged");
        sum+=s.x+s.z+s.speed_ms;
    }
    world.restore(saved);
    for(int t=0;t<steps;t++)world.step(action);
    require(world.tick()==final.tick,"Restored tick mismatch");
    for(std::size_t i=0;i<count;i++){
        const auto& a=final.states[i],b=world.states()[i];
        require(a.x==b.x&&a.y==b.y&&a.z==b.z&&a.yaw==b.yaw&&a.speed_ms==b.speed_ms,
                "Sandbox replay not bitwise deterministic");
    }
    bool caught=false;
    action[0].steer=std::numeric_limits<float>::quiet_NaN();
    const auto prior=world.snapshot();
    try{world.step(action);}catch(const std::invalid_argument&){caught=true;}
    require(caught&&world.tick()==prior.tick,"Invalid action did not fail atomically");
    std::cout<<std::fixed<<std::setprecision(2)
         <<"PASS EXPERIMENTAL_SANDBOX: instances="<<count
         <<" ticks="<<steps
         <<" transitions="<<count*std::uint64_t(steps)
         <<" millionTransitionsPerSecond="<<(count*double(steps)/elapsed/1e6)
         <<" deterministicRestore=TRUE"
         <<" trackedY=FLAT"
         <<" fullTrackmaniaPhysics=FALSE\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
