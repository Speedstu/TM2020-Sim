// Benchmark geometry-free replay RoutePlan 3D KD-tree on a long recorded route.
// Does not measure neural driving performance or physics accuracy.
#include "tm2020.hpp"
#include <chrono>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <vector>
int main(int argc,char**argv)try{
    if(argc!=2)throw std::invalid_argument("Usage: tm2020_route_bench <replay.tmreplay>");
    const auto r=tm2020::Replay::load(argv[1]);
    const tm2020::RoutePlan route(r);
    constexpr std::size_t queries=100'000;
    volatile std::size_t sink=0;
    auto start=std::chrono::steady_clock::now();
    for(std::size_t i=0;i<queries;i++){
        const auto& s=r.states[(i*83)%route.waypoint_count()];
        const tm2020::Vec3 query{s.position.x+double(i%15)-7.0,
                                 s.position.y+double(i%5)-2.0,
                                 s.position.z+double(i%11)-5.0};
        auto result=route.target(query,s.yaw_rad+(double(i%7)-3)*0.12,25);
        sink=sink^result.nearest_sample;
    }
    const double dt=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
    if(dt<=0||route.waypoint_count()<100)
        throw std::runtime_error("Invalid benchmark");
    std::cout<<std::fixed<<std::setprecision(2)
        <<"PASS ROUTE_KDTREE_BENCH: waypoints="<<route.waypoint_count()
        <<" segments="<<route.segment_count()
        <<" lookups="<<queries
        <<" kdSearchesPerSecond="<<queries/dt
        <<" checksum="<<sink
        <<" nativeGamePhysics=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
