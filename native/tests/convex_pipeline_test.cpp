#include "convex_box_fixture.hpp"
#include "tm2020/recovered_solver.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
int main()try{
    tm2020::testing::BoxGeometry box({1,1,1});ConvexInstance a{box.view(),{},7},b{box.view(),{},11};b.transform.translation={1.5f,0,0};
    const auto pair=collide_convex(a,b);check(pair.overlap&&pair.contacts.size()==4,"Cube face manifold missing");
    for(const auto& p:pair.contacts){
        check(p.normal[0]==-1&&p.penetration_vector[0]==-.5f&&p.world_point[0]==.5f,"Cube contact depth, orientation or incident face changed");
        check(std::abs(p.world_point[1])==1&&std::abs(p.world_point[2])==1&&p.surface_id_a==7&&p.surface_id_b==11,"Cube face corner or material pair changed");
    }
    check(collide_convex(a,b,false).overlap&&collide_convex(a,b,false).contacts.empty(),"Boolean convex query emits contacts");
    b.transform.translation[0]=2;check(collide_convex(a,b).overlap,"Closed convex tangency changed");b.transform.translation[0]=2.01f;check(!collide_convex(a,b).overlap,"Separated cubes overlap");
    const EdgeFrame e{{0,0,0},{1,0,0},1},f{{3,2,0},{-1,0,0},1};const auto closest=closest_edges(e,f);
    check(closest.squared_distance==5&&closest.parameter_a==1&&closest.parameter_b==1,"Parallel segment endpoint minimization wrong");
    const std::array<ConvexVector,4> vertices{{{-4,0,-4},{-4,0,4},{4,0,4},{4,0,-4}}};
    const std::array<IndexedTriangle,2> indexed{{{{0,1,2},3,0},{{0,2,3},5,0}}};const auto triangles=cook_triangles(vertices,indexed);const auto tree=build_aabb_tree(triangle_aabbs(vertices,indexed));
    a.transform.translation={0,.5f,0};const CookedMeshView mesh{vertices,triangles,tree,{}};
    const auto floor=collide_convex_mesh(a,mesh,{{0,0,0},{1,1,1},0});check(floor.overlap&&!floor.contacts.empty(),"Convex floor contacts missing");
    for(const auto& p:floor.contacts)check(p.normal[1]==1&&p.penetration_vector[1]>.49f&&p.penetration_vector[1]<.501f&&p.surface_id_a==7&&(p.surface_id_b==3||p.surface_id_b==5),"Convex mesh orientation, depth or material wrong");
    a.transform.translation[1]=3;check(!collide_convex_mesh(a,mesh,{{0,0,0},{1,1,1},0}).overlap,"Broadphase kept remote floor contact");
    bool rejected=false;try{closest_edges({{},{1,0,0},0},{{},{1,0,0},0});}catch(const std::invalid_argument&){rejected=true;}check(rejected,"Undefined zero/zero parallel segment accepted");
    auto bad=a;bad.transform.rotation[0]=2;rejected=false;try{collide_convex(bad,b);}catch(const std::invalid_argument&){rejected=true;}check(rejected,"Nonrigid convex rotation accepted");
    std::array<RigidState,1> initial{};initial[0].linear_velocity={2,-2,0};const std::array<VelocityCoefficients,1> coefficients{{{0,0,0,1}}};
    const auto prepared=prepare_static_contact({0,0,{0,0,0},{0,1,0},0,.5f,0},initial,coefficients,.01f,1);
    ContactIsland island;island.static_normals.push_back(prepared.normal);island.static_friction.assign(prepared.friction.begin(),prepared.friction.begin()+prepared.friction_count);
    std::array islands{island};auto states=initial;solve_contact_islands(states,coefficients,islands,{2,0,1});
    check(states[0].linear_velocity[0]==2&&states[0].linear_velocity[1]==0&&islands[0].static_normals[0].accumulated_impulse==2,"First iteration did not run friction before the normal impulse");
    islands[0]=island;states=initial;solve_contact_islands(states,coefficients,islands,{2,0,2});check(states[0].linear_velocity[0]==1&&states[0].linear_velocity[1]==0,"Second iteration did not consume previous normal impulse");
    islands[0]=island;states=initial;solve_contact_islands(states,coefficients,islands,{0,0,2});check(states[0].linear_velocity[0]==2&&states[0].linear_velocity[1]==0,"Friction threshold stopped unilateral normals");
    const auto saved=states;islands[0].static_final_normals.push_back({2,{},{},0,1,0});const auto invalid=islands;
    rejected=false;try{solve_contact_islands(states,coefficients,islands,{2,0,2});}catch(const std::invalid_argument&){rejected=true;}
    check(rejected&&std::memcmp(states.data(),saved.data(),sizeof(states))==0&&islands[0].static_normals[0].accumulated_impulse==invalid[0].static_normals[0].accumulated_impulse,"Late scheduler error partly committed state or impulses");
    std::cout<<"PASS CONVEX_CONTACT_PIPELINE manifold=true convex_mesh=true segment_boundaries=true native_friction_order=true transactional_scheduler=true full_vehicle=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
