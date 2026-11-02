// Regression oracle for Trackmania 2020 Fall 2026 - 01.
// Cross-check authored grid block positions against external read-only
// position candidates. Does not read game process, alter code or simulate physics.
#include "tm2020.hpp"
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
constexpr double GRID_HORIZ=32.;
struct Horizontal {double x,z;};
Horizontal center(const tm2020::Block& b){
    return {b.grid[0]*GRID_HORIZ+GRID_HORIZ/2.,
            b.grid[2]*GRID_HORIZ+GRID_HORIZ/2.};
}
double distance(Horizontal a,Horizontal b){
    return std::hypot(a.x-b.x,a.z-b.z);
}
}

int main(int argc,char**argv)try {
    if(argc!=2)throw std::invalid_argument("Usage: tm2020_map_anchor_test Fall2026_01.tmmap");
    auto map=tm2020::Map::load(argv[1]);
    if(map.uid!="ypPmohQofd72MyTsIsijKfrJH98"||map.blocks.size()<3000)
        throw std::runtime_error("Unexpected map UID or block count");
    std::size_t startCount=0;
    Horizontal start{},checkpoint{};
    double best=1e9;
    const Horizontal measuredBefore{1199.9995,1359.7267};
    const Horizontal measuredAfter{1148.4097,1188.314};
    std::string nearestName;
    for(const auto& block:map.blocks) {
        if(block.name=="RoadTechStart"){
            startCount++;
            start=center(block);
        }
        if(block.name.find("Road")==0 || block.name.find("Platform")==0){
            const auto c=center(block);
            const auto d=distance(c,measuredAfter);
            if(d<best){best=d;checkpoint=c;nearestName=block.name;}
        }
    }
    if(startCount!=1)throw std::runtime_error("Map start count not equal 1");
    const double startErr=distance(start,measuredBefore);
    if(startErr>0.5 || best>25. || nearestName!="RoadTechCheckpointTiltLeft")
        throw std::runtime_error("Recorded candidate coordinates do not corroborate real map");
    // The true Fall 2026 - 01 finish is three anchored item gates, NOT RoadTechFinish.
    const auto markers=map.course_markers();
    std::size_t starts=0,checkpoints=0,finishes=0,finishItems=0;
    double sumFinishX=0;
    for(const auto& m:markers) {
        switch(m.kind) {
            case tm2020::CourseMarkerKind::Start:
                starts++;
                if(std::hypot(m.position.x-1200.,m.position.z-1360.)>0.001
                   ||m.altitude_from_authoritative_item)
                    throw std::runtime_error("Invalid start marker or claimed block altitude");
                break;
            case tm2020::CourseMarkerKind::Checkpoint:
                checkpoints++;
                break;
            case tm2020::CourseMarkerKind::Finish:
                finishes++;
                if(!m.from_anchored_item || !m.altitude_from_authoritative_item ||
                   std::abs(m.position.y-30.)>0.001||
                   std::abs(m.position.z-1360.)>0.001)
                    throw std::runtime_error("Finish must come from native anchored GBX item");
                sumFinishX+=m.position.x;
                finishItems++;
                break;
        }
    }
    if(starts!=1||checkpoints!=3||finishes!=3||finishItems!=3 ||
       std::abs(sumFinishX/3.-816.)>0.001)
        throw std::runtime_error("Native course marker extraction mismatch (start/checkpoints/3-item finish)");
    std::cout<<"[MAP_MARKERS] starts="<<starts<<" checkpoints="<<checkpoints
             <<" finishItemGates="<<finishItems<<" finishCenterX="<<sumFinishX/3.
             <<" notARoutePlanner=true\n";
    std::cout<<"PASS GBX_CPP_MAP_ANCHOR UID="<<map.uid
             <<" blocks="<<map.blocks.size()
             <<" startCenterXZ=("<<start.x<<","<<start.z<<")"
             <<" candidateStartDeltaM="<<startErr
             <<" nearestAfterMovement="<<nearestName
             <<" afterDeltaToBlockCenterM="<<best
             <<" fullVehicleTelemetryValidated=false"
             <<" exactPhysicsReady=false\n";
    return 0;
}catch(const std::exception& e){std::cerr<<"FAIL map anchor: "<<e.what()<<"\n";return 1;}
