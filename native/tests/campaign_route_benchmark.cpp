// Native cross-demonstration route bench for EXACT same TM2020 game map.
// Reference is public TAS replay 4634; independently recorded TAS 4754/4902
// evaluate route deviation. No oracle future from heldout sample, no game
// injection, no physics state manipulation. Only offline saved GBX states.
#include "tm2020.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>
namespace fs=std::filesystem;
double dist(tm2020::Vec3 a,tm2020::Vec3 b){
    return std::hypot(a.x-b.x,std::hypot(a.y-b.y,a.z-b.z));
}
double mean(const std::vector<double>& v){
    if(v.empty())throw std::runtime_error("Empty metrics");
    return std::accumulate(v.begin(),v.end(),0.)/v.size();
}
double p95(std::vector<double> v){
    std::sort(v.begin(),v.end());
    return v[std::min(v.size()-1,v.size()*95/100)];
}
int main(int argc,char**argv)try {
    if(argc!=5)
        throw std::invalid_argument("Usage: tm2020_campaign_route_test <map.tmmap> <reference.tmreplay> <comparison.tmreplay> <out.csv>");
    const auto map=tm2020::Map::load(argv[1]);
    const auto reference=tm2020::Replay::load(argv[2]);
    const auto other=tm2020::Replay::load(argv[3]);
    if(map.uid!=reference.uid||map.uid!=other.uid)
        throw std::runtime_error("Map UID mismatch: never compare routes from different tracks");
    const auto markers=map.course_markers();
    std::vector<tm2020::Vec3> starts,finishes;
    for(const auto& m:markers) {
        if(m.kind==tm2020::CourseMarkerKind::Start)starts.push_back(m.position);
        if(m.kind==tm2020::CourseMarkerKind::Finish)finishes.push_back(m.position);
    }
    if(starts.size()!=1||finishes.empty())
        throw std::runtime_error("Track must have unique start and known finish gates");
    auto startsNear=[&](const tm2020::Replay& r){
        const auto& p=r.states.front().position;
        return std::hypot(p.x-starts.front().x,p.z-starts.front().z);
    };
    if(startsNear(reference)>1||startsNear(other)>1)
        throw std::runtime_error("Ghosts do not start near authentic map start");
    tm2020::RoutePlan planned(reference);
    if(planned.segment_count()!=1||planned.waypoint_count()<150)
        throw std::runtime_error("Unexpected teleports or route discontinuities in reference");
    std::vector<double> lateral,waypointDistance;
    std::size_t valid=0,forward=0;
    for(const auto& sample:other.states){
        if(sample.time_ms>other.finish_ms)break;
        const auto t=planned.target(sample.position,sample.yaw_rad,24.0);
        if(t.nearest_sample>=planned.waypoint_count()||
           t.target_sample>=planned.waypoint_count()||
           !std::isfinite(t.lateral_error_m))
            throw std::runtime_error("Invalid nearest-route projection");
        const auto f=planned.as_desired_future(sample,24.0);
        lateral.push_back(std::abs(t.lateral_error_m));
        waypointDistance.push_back(dist(sample.position,f.position));
        forward+=t.target_sample>=t.nearest_sample;
        valid++;
    }
    if(valid<350||valid>500 || forward!=valid)
        throw std::runtime_error("Unusable heldout route projection");
    auto distanceToFinish=[](const tm2020::Replay& r,const std::vector<tm2020::Vec3>& finish){
        const tm2020::State* ending=&r.states.front();
        for(const auto& s:r.states)if(s.time_ms<=r.finish_ms)ending=&s;
        double nearest=1e9;
        for(auto gate:finish)nearest=std::min(nearest,dist(ending->position,gate));
        return nearest;
    };
    const auto refFinish=distanceToFinish(reference,finishes);
    const auto otherFinish=distanceToFinish(other,finishes);
    if(refFinish>50||otherFinish>50)
        throw std::runtime_error("Replay did not finish near an actual map gate");
    fs::create_directories(fs::path(argv[4]).parent_path());
    std::ofstream csv(argv[4]);
    if(!csv)throw std::runtime_error("Cannot save native route benchmark");
    csv<<"map_uid,ref_finish_ms,test_finish_ms,frames,reference_nodes,"
          "mean_deviation_m,p95_deviation_m,mean_distance_future_waypoint_m,"
          "ref_distance_finish_gate_m,eval_distance_finish_gate_m,causal_future_from_ref_only\n";
    csv<<map.uid<<","<<reference.finish_ms<<","<<other.finish_ms<<","
       <<valid<<","<<planned.waypoint_count()<<","
       <<std::fixed<<std::setprecision(5)<<mean(lateral)<<","<<p95(lateral)<<","
       <<mean(waypointDistance)<<","<<refFinish<<","<<otherFinish<<",true\n";
    std::cout<<"PASS CXX_CAMPAIGN_ROUTE mapUID="<<map.uid
             <<" referenceMs="<<reference.finish_ms
             <<" heldoutMs="<<other.finish_ms
             <<" evalSamples="<<valid
             <<" meanRouteDeviationM="<<mean(lateral)
             <<" p95RouteDeviationM="<<p95(lateral)
             <<" meanWaypointDistanceM="<<mean(waypointDistance)
             <<" referenceFinishGateDistanceM="<<refFinish
             <<" heldoutFinishGateDistanceM="<<otherFinish
             <<" noHeldoutOracle=true realGamePhysicsSimulated=false"
             <<" result="<<argv[4]<<"\n";
    return 0;
}catch(const std::exception& e){
    std::cerr<<"FAIL CAMPAIGN_ROUTE "<<e.what()<<"\n";
    return 1;
}
