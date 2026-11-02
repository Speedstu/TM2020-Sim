#include "convex_box_fixture.hpp"
#include "tm2020/recovered_world.hpp"
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
int main()try{
    const std::array<ConvexContact,3> contacts{{{{3,4,0},{1,0,0},{1,2,3},1,2},{{0,0,2},{0,1,0},{4,5,6},1,2},{{0,0,1},{1,0,0},{7,8,9},0x2301,0x4502}}};
    const auto patches=build_contact_patches(contacts,SurfaceMaterialTable{},{},{},0x30abc000);
    check(patches.size()==2&&patches[0].points.size()==2&&patches[1].points.size()==1,"Patch linked-run grouping lost low-byte material equivalence");
    check(patches[0].points[0].world_point==contacts[0].world_point&&patches[0].points[1].world_point==contacts[2].world_point&&patches[0].points[0].separation==5,"Patch point order or penetration length wrong");
    std::vector<ConvexContact> boundary(256,contacts[0]);const auto chunks=build_contact_patches(boundary,SurfaceMaterialTable{},{},{},0x30abc000);
    check(chunks.size()==2&&chunks[0].points.size()==255&&chunks[1].points.size()==1&&chunks[0].first_chunk&&!chunks[1].first_chunk,"Patch 255-contact chunk boundary changed");
    std::array<RigidState,1> states{};states[0].linear_velocity={0,-2,0};const std::array<VelocityCoefficients,1> coefficients{{{.1f,.1f,.1f,1}}};
    const auto no_bounce=prepare_static_contact({0,0,{0,-1,0},{0,1,0},.1f,.5f,-.5f},states,coefficients,.01f,1);
    check(no_bounce.normal.target==0,"Negative native restitution incorrectly activated bounce");
    tm2020::testing::BoxGeometry box({1,1,1});std::array<ConvexVector,4> floor{{{-100,0,-100},{-100,0,100},{100,0,100},{100,0,-100}}};
    const std::array<IndexedTriangle,2> triangles{{{{0,1,2},78,0},{{0,2,3},78,0}}};
    RigidMeshConfiguration config{};config.model.angular_speed_limit=100;config.velocity.coefficients={.1f,.1f,.1f,1};config.velocity.model_gravity_scale=1;config.velocity.item_gravity_multiplier=1;config.environment={{0,-10,0},false,.01f,.9f};config.velocity_iterations={5,1,5};config.position={0,.1f,.2f};config.position_iterations=4;config.restitution_speed_threshold=1;config.body_surface_id=78;
    RigidMeshWorld world(box.view(),{{0,0,0},{1,1,1},0},floor,triangles,{},config);floor={}; // World must own its source geometry.
    RigidState start{};start.position={0,4,0};world.reset(start);ForceAccumulator forces{};std::size_t hits{};
    for(unsigned i=0;i<400;i++)hits+=world.step(.01f,forces).contacts;
    check(hits>0&&world.state().position[1]>.95f&&world.state().position[1]<1.05f&&std::abs(world.state().linear_velocity[1])<.2f,"Autonomous recovered collision scene did not settle on floor");
    const auto saved=world.snapshot();for(unsigned i=0;i<100;i++)world.step(.01f,forces);const auto expected=world.snapshot();
    world.restore(saved);for(unsigned i=0;i<100;i++)world.step(.01f,forces);const auto actual=world.snapshot();
    check(std::memcmp(&expected.state,&actual.state,sizeof(RigidState))==0&&expected.tick==actual.tick,"Contact world snapshot replay differs");
    const auto before=world.snapshot();forces.linear[0]=std::numeric_limits<float>::infinity();const auto bad_force=forces;bool denied=false;
    try{world.step(.01f,forces);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(&before.state,&world.state(),sizeof(RigidState))==0&&world.tick()==before.tick&&std::memcmp(&forces,&bad_force,sizeof(forces))==0,"Failed world step changed state, tick or caller forces");
    auto invalid=before;invalid.state.quaternion={};denied=false;try{world.restore(invalid);}catch(const std::invalid_argument&){denied=true;}
    check(denied&&std::memcmp(&before.state,&world.state(),sizeof(RigidState))==0,"Invalid snapshot changed world state");
    RigidMeshWorld other(box.view(),{{0,0,0},{1,1,1},0},{}, {},{},config);denied=false;try{other.restore(before);}catch(const std::invalid_argument&){denied=true;}check(denied,"Snapshot accepted by a world with different geometry identity");
    auto centered=config;centered.model_center={1,0,0};centered.environment.gravity={};RigidMeshWorld spinning(box.view(),{{0,0,0},{1,1,1},0},{},{},{},centered);
    RigidState free{};free.angular_velocity={0,0,1};spinning.reset(free);forces={};spinning.step(.1f,forces);const auto& s=spinning.state();
    check(s.position[1]<-.09f&&std::abs((s.position[0]+s.rotation[0])-1)<1e-6f&&std::abs(s.position[1]+s.rotation[3])<1e-6f,"Nonzero model-center integration failed to preserve the free center while the origin rotates");
    auto fused=config;fused.position_math=PositionMathPath::fused_avx_fma;const std::array<ConvexVector,4> fused_floor{{{-100,0,-100},{-100,0,100},{100,0,100},{100,0,-100}}};
    RigidMeshWorld fused_world(box.view(),{{0,0,0},{1,1,1},0},fused_floor,triangles,{},fused);start.angular_velocity={.1f,.2f,.3f};fused_world.reset(start);forces={};hits=0;
    for(unsigned i=0;i<400;i++)hits+=fused_world.step(.01f,forces).contacts;
    check(hits>0&&fused_world.state().position[1]>.95f,"FMA world failed to resolve rotating contacts");
    std::cout<<"PASS PATCH_WORLD linked_runs=true chunk_limit=true negative_restitution=true owned_geometry=true autonomous_collision_settling=true bit_exact_snapshot_replay=true transactional=true full_vehicle=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
