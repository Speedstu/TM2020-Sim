#include "tm2020.hpp"
#include "tm2020/surface_materials.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
int main(int argc,char** argv)try{
    if(argc!=5)throw std::invalid_argument("Usage: tm2020_collision_replay_audit cache.tmcol cache.surfaces reference.tmreplay report.json");
    tm2020::CollisionWorld world(argv[1]);const auto replay=tm2020::Replay::load(argv[3]);
    if(replay.uid!="ypPmohQofd72MyTsIsijKfrJH98")throw std::invalid_argument("This start-floor audit requires the verified Fall 2026 - 01 reference");
    std::ifstream source(argv[2],std::ios::binary|std::ios::ate);if(!source)throw std::runtime_error("Cannot open surface sidecar");const auto bytes=source.tellg();source.seekg(0);std::array<char,8> magic{};source.read(magic.data(),8);std::uint32_t count{};source.read(reinterpret_cast<char*>(&count),4);
    if(!source||std::memcmp(magic.data(),"TMSURF1\0",8)||count!=world.triangle_count()||bytes!=std::streamoff(12ull+count*2ull))throw std::runtime_error("Surface sidecar extent differs from geometry");
    std::vector<std::uint16_t> surfaces(count);source.read(reinterpret_cast<char*>(surfaces.data()),count*2ull);if(!source)throw std::runtime_error("Truncated surface sidecar");
    std::vector<const tm2020::State*> states;std::vector<double> rays;
    for(const auto& state:replay.states)if(state.time_ms>=0&&state.time_ms<=replay.finish_ms){states.push_back(&state);const auto& p=state.position;rays.insert(rays.end(),{p.x,p.y+.05,p.z,0.,-1.,0.,5.});}
    if(states.empty())throw std::runtime_error("Replay has no in-race states");std::vector<double> hits(states.size()*9);world.raycast(rays.data(),states.size(),hits.data());
    std::size_t grounded{},ground_hits{},ground_materials{},comparable_materials{},ray_hits{};std::vector<double> clearances;
    for(std::size_t i=0;i<states.size();i++){const auto* hit=hits.data()+i*9;const auto& state=*states[i];ray_hits+=hit[0]!=0;if(!state.ground_contact)continue;grounded++;if(hit[0]==0)continue;ground_hits++;const auto index=std::size_t(hit[8]);if(index>=surfaces.size())throw std::runtime_error("Ray returned invalid triangle index");const auto id=tm2020::recovered::dataset_material_code(std::uint8_t(surfaces[index]));if(id!=255){comparable_materials++;ground_materials+=std::find(state.contact_materials.begin(),state.contact_materials.end(),id)!=state.contact_materials.end();}clearances.push_back(state.position.y-hit[3]);}
    std::sort(clearances.begin(),clearances.end());const auto percentile=[&](double q){return clearances.empty()?0.:clearances[std::size_t(q*double(clearances.size()-1))];};
    const std::array<double,7> start_ray{1200,34.1,1360,0,-1,0,5};std::array<double,9> start{};world.raycast(start_ray.data(),1,start.data());const auto start_surface=start[0]!=0?surfaces[std::size_t(start[8])]:0xffffu;
    if(start[0]==0||std::abs(start[3]-34.)>1e-4||start_surface!=16)throw std::runtime_error("Captured cache fails independently observed start floor/material");
    std::ofstream report(argv[4]);report<<std::setprecision(12)<<"{\"schema\":\"tm2020_captured_collision_replay_audit_v1\",\"triangles\":"<<count<<",\"replayFinishMs\":"<<replay.finish_ms<<",\"inRaceStates\":"<<states.size()<<",\"rayHits\":"<<ray_hits<<",\"groundContactStates\":"<<grounded<<",\"groundContactRayHits\":"<<ground_hits<<",\"groundContactMaterialMatches\":"<<ground_materials<<",\"groundRayHitFraction\":"<<(grounded?double(ground_hits)/grounded:0)<<",\"materialComparisonUsesIndependentPhysicalNameTable\":true,\"comparableGroundMaterialRays\":"<<comparable_materials<<",\"groundMaterialMatchFraction\":"<<(comparable_materials?double(ground_materials)/comparable_materials:0)<<",\"bodyOriginGroundClearanceP05\":"<<percentile(.05)<<",\"bodyOriginGroundClearanceP50\":"<<percentile(.5)<<",\"bodyOriginGroundClearanceP95\":"<<percentile(.95)<<",\"startFloorY\":"<<start[3]<<",\"startSurfaceId\":"<<start_surface<<",\"startMatchesFourLiveWheelMaterials\":true,\"gameRequiredAtRuntime\":false,\"pythonRequiredAtRuntime\":false,\"allWorldPlacementsVerified\":false,\"completeMapCollisionVerified\":false,\"nativeRaycastInstructionOracleClaim\":false}\n";report.flush();if(!report)throw std::runtime_error("Cannot write collision replay audit");
    std::cout<<"PASS CAPTURED_COLLISION_REPLAY triangles="<<count<<" states="<<states.size()<<" grounded="<<grounded<<" grounded_ray_hits="<<ground_hits<<" matching_materials="<<ground_materials<<" start_y="<<start[3]<<" start_material="<<start_surface<<" game_required=false complete_map_qualified=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
