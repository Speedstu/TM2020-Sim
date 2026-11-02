#include "tm2020/recovered_raycast.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct NativeMesh {const void* vertices{};std::uint64_t pad{};const void* triangles{};};
struct NativeContact {const void* a{};const void* b{};std::array<float,3> penetration{},normal{},point{};
    std::array<std::byte,28> other{};std::uint16_t material_a{},material_b{};std::uint32_t flags{};};
struct Instance {const void* surface{};std::array<std::byte,36> other{};std::array<float,3> center{};};
struct Arena {NativeContact* data{};std::uint32_t count{},reserved{},capacity{1};};
struct Context {std::uint32_t hit{},reserved{};Arena* arena{};std::uint32_t any_hit{};};
struct Span {const void* data{};std::uint32_t count{},capacity{};};
struct MeshObject {std::array<std::byte,32> header{};Span vertices,raw,cooked,tree;};
struct MeshInstance {const void* surface{};MeshTransform transform;};
struct RayInput {std::array<float,3> origin,direction;};
struct RayRecord {float fraction{1.00001f};std::array<float,3> point{},normal{};std::uint16_t material{},pad{};
    const void* instance{};std::uint64_t triangle{};};
struct RayContext {std::uint32_t single{1},pad{};RayRecord* record{};std::uint32_t any_hit{};};
static_assert(sizeof(NativeContact)==88&&offsetof(Instance,center)==0x2c);
static_assert(sizeof(MeshObject)==96&&offsetof(MeshInstance,transform)==8&&offsetof(RayRecord,instance)==0x20);
void word(std::ostream& out,std::uint32_t value){out.write(reinterpret_cast<const char*>(&value),4);}
void value(std::ostream& out,float v){word(out,std::bit_cast<std::uint32_t>(v));}
template<class T>void floats(std::ostream& out,const T& row){for(float v:row)value(out,v);}
int main(int argc,char**argv)try{
    check(argc==4,"geometry_gap_oracle original.exe new_output_dir cases");
    const auto cases=std::stoul(argv[3]);check(cases>=100&&cases<=1000000,"Case bound");
    const std::filesystem::path folder(argv[2]);check(!std::filesystem::exists(folder),"Never overwrite geometry evidence");
    std::filesystem::create_directories(folder);
    const std::array<std::array<unsigned,2>,8> ranges{{{0x1af350,0x1af706},{0x18ba80,0x18bb55},
        {0x18ca50,0x18ca8f},{0x1a17f0,0x1a1a43},{0x197890,0x1978b2},
        {0x1b2420,0x1b2947},{0x1a0290,0x1a052d},{0x19a580,0x19a597}}};
    ArithmeticImage image(argv[1],ranges);
    using RayFn=int(*)(const NativeMesh*,const void*,const void*,unsigned,unsigned,float*,float*,float*);
    using SphereFn=void(*)(const void*,const void*,void*);
    using MeshFn=void(*)(const void*,const void*,const void*,const void*,void*);
    const auto ray=reinterpret_cast<RayFn>(image.base+0x1af350);
    const auto sphere=reinterpret_cast<SphereFn>(image.base+0x1a17f0);
    const auto full_mesh=reinterpret_cast<MeshFn>(image.base+0x1b2420);
    std::ofstream rays(folder/"ray-triangle.cases",std::ios::binary),spheres(folder/"sphere-sphere.cases",std::ios::binary);
    std::ofstream meshes(folder/"ray-mesh.cases",std::ios::binary);meshes.write("TMRMS002",8);word(meshes,cases);
    rays.write("TMRAY001",8);word(rays,cases);spheres.write("TMSPH001",8);word(spheres,cases);
    std::mt19937_64 rng(0x2026102901);std::uniform_real_distribution<float> u(-1,1);
    std::size_t ray_hits{},two_sided_hits{},sphere_hits{},sphere_fallbacks{},mesh_hits{},mesh_two_hits{},material_skips{};
    for(std::size_t i=0;i<cases;i++){
        std::array<std::array<float,3>,3> vertices;
        for(auto& p:vertices)for(auto& v:p)v=u(rng)*20;
        if(i%4==0)vertices={{{0,0,0},{0,0,4},{4,0,0}}};
        if(i%23==0)vertices[2]=vertices[1];
        const std::array<IndexedTriangle,1> indexed{{{{0,1,2},std::uint16_t(rng()),0}}};
        const auto tri=cook_triangles(vertices,indexed)[0];
        std::array<float,3> origin{},direction{};
        const auto cu=u(rng)*.8f+.3f,cv=u(rng)*.8f+.3f;
        const float distance=u(rng)*10;
        for(unsigned k=0;k<3;k++){
            const float point=vertices[0][k]+cu*(vertices[1][k]-vertices[0][k])+cv*(vertices[2][k]-vertices[0][k]);
            origin[k]=point+tri.normal[k]*distance;direction[k]=-tri.normal[k]*distance*(1.1f+std::abs(u(rng)));
        }
        if(i%17==0)direction={};
        if(i%19==0){origin={1,0,1};direction={0,-1,0};}
        if(i%29==0){origin={1,-1,1};direction={0,1,0};}
        RayTriangleHit expected{std::abs(u(rng))*1.5f,u(rng),u(rng)},actual=expected;
        if(i%19==0||i%29==0)expected.fraction=actual.fraction=1;
        const auto two=unsigned(i%2);NativeMesh mesh{vertices.data(),0,&tri};
        floats(rays,vertices[0]);floats(rays,vertices[1]);floats(rays,vertices[2]);
        floats(rays,tri.normal);value(rays,tri.plane_constant);for(auto index:tri.vertices)word(rays,index);
        word(rays,std::uint32_t(tri.surface_id));floats(rays,origin);floats(rays,direction);word(rays,two);
        value(rays,expected.fraction);value(rays,expected.u);value(rays,expected.v);
        const bool hit=ray(&mesh,origin.data(),direction.data(),0,two,&expected.fraction,&expected.u,&expected.v)!=0;
        const bool port=raycast_cooked_triangle(vertices,tri,origin,direction,two!=0,actual);
        if(hit!=port||std::memcmp(&expected,&actual,sizeof(expected))){std::cerr<<"RAY_MISMATCH case="<<i<<" original="<<hit<<" port="<<port<<'\n';throw std::runtime_error("Ray differs from original instructions");}
        word(rays,unsigned(hit));value(rays,expected.fraction);value(rays,expected.u);value(rays,expected.v);
        ray_hits+=hit;two_sided_hits+=hit&&two;

        // Full native mesh handler: rigid transform, tree traversal, skip material,
        // moving-surface displacement and closest-hit output ownership.
        const float angle=u(rng)*3.14f,cosine=std::cos(angle),sine=std::sin(angle);
        const float pitch=u(rng)*3.14f,roll=u(rng)*3.14f,cp=std::cos(pitch),sp=std::sin(pitch),cr=std::cos(roll),sr=std::sin(roll);
        const std::array<float,9> yaw{cosine,0,sine,0,1,0,-sine,0,cosine};
        const std::array<float,9> pitch_roll{cr,-sr,0,cp*sr,cp*cr,-sp,sp*sr,sp*cr,cp};
        MeshTransform pose;pose.translation={u(rng)*100,u(rng)*20,u(rng)*100};
        for(unsigned row=0;row<3;row++)for(unsigned col=0;col<3;col++)
            pose.rotation[row*3+col]=(yaw[row*3]*pitch_roll[col]+yaw[row*3+1]*pitch_roll[3+col])+yaw[row*3+2]*pitch_roll[6+col];
        auto rotate=[&](const std::array<float,3>& local){std::array<float,3> result{};
            for(unsigned k=0;k<3;k++)result[k]=(pose.rotation[k*3]*local[0]+pose.rotation[k*3+1]*local[1])+pose.rotation[k*3+2]*local[2];return result;};
        RayInput world_ray{rotate(origin),rotate(direction)};
        std::array<float,3> offset{u(rng)*.1f,u(rng)*.1f,u(rng)*.1f};
        if(i%3==0)offset={};
        for(unsigned k=0;k<3;k++){world_ray.origin[k]+=pose.translation[k];world_ray.direction[k]+=offset[k];}
        std::array<std::array<float,3>,9> mesh_vertices;std::array<IndexedTriangle,3> mesh_indexed;
        for(unsigned face=0;face<3;face++){
            const float separation=i%5==0?0.f:float(face)*.3f;
            for(unsigned vertex=0;vertex<3;vertex++)for(unsigned k=0;k<3;k++)
                mesh_vertices[face*3+vertex][k]=vertices[vertex][k]+tri.normal[k]*separation;
            mesh_indexed[face]={{face*3,face*3+1,face*3+2},std::uint16_t(face==0?tri.surface_id:rng()),0};
        }
        const auto mesh_cooked=cook_triangles(mesh_vertices,mesh_indexed);
        const auto tree=build_aabb_tree(triangle_aabbs(mesh_vertices,mesh_indexed));
        const MeshObject mesh_object{{},{mesh_vertices.data(),9,9},{mesh_indexed.data(),3,3},
            {mesh_cooked.data(),3,3},{tree.data(),std::uint32_t(tree.size()),std::uint32_t(tree.size())}};
        const MeshInstance mesh_instance{&mesh_object,pose};
        const std::array<std::uint8_t,2> filter{std::uint8_t(i%7==0?tri.surface_id:255),std::uint8_t(two)};
        RayRecord native_ray{};const auto untouched=native_ray;RayContext ray_context{1,0,&native_ray,0};
        full_mesh(filter.data(),&world_ray,&mesh_instance,offset.data(),&ray_context);
        if(!ray_context.any_hit)check(std::memcmp(&native_ray,&untouched,sizeof(native_ray))==0,"Full mesh miss modified output");
        else check(native_ray.instance==&mesh_instance&&native_ray.triangle<3,"Full mesh output ownership differs");
        for(const auto& p:mesh_vertices)floats(meshes,p);
        for(const auto& t:mesh_cooked){floats(meshes,t.normal);value(meshes,t.plane_constant);for(auto index:t.vertices)word(meshes,index);word(meshes,t.surface_id);}
        floats(meshes,pose.rotation);floats(meshes,pose.translation);floats(meshes,world_ray.origin);floats(meshes,world_ray.direction);
        floats(meshes,offset);word(meshes,filter[0]);word(meshes,two);word(meshes,ray_context.any_hit);
        value(meshes,native_ray.fraction);floats(meshes,native_ray.point);floats(meshes,native_ray.normal);
        word(meshes,native_ray.material);word(meshes,std::uint32_t(native_ray.triangle));
        mesh_hits+=ray_context.any_hit!=0;mesh_two_hits+=ray_context.any_hit&&two;material_skips+=i%7==0;

        Sphere a{},b{};for(float& x:a.center)x=u(rng)*4;for(float& x:b.center)x=u(rng)*4;
        a.radius=std::abs(u(rng))*4;b.radius=std::abs(u(rng))*4;a.surface_id=std::uint16_t(rng());b.surface_id=std::uint16_t(rng());
        if(i%7==0){a.center={};b.center={};}if(i%11==0){a.center={};b.center={0,1e-6f,0};}
        if(i%13==0){a.center={};a.radius=1;b.radius=1;b.center={2,0,0};}
        if(i%17==0){a.center={};b.center={0,1e-5f,0};}if(i%19==0){a.radius=0;b.radius=0;}
        std::array<std::byte,48> sa{},sb{};
        std::memcpy(sa.data()+0x28,&a.radius,4);std::memcpy(sb.data()+0x28,&b.radius,4);
        std::memcpy(sa.data()+0x20,&a.surface_id,2);std::memcpy(sb.data()+0x20,&b.surface_id,2);
        const Instance ia{sa.data(),{},a.center},ib{sb.data(),{},b.center};NativeContact original{};
        original.flags=std::uint32_t(rng());original.material_a=std::uint16_t(rng());original.material_b=std::uint16_t(rng());
        for(auto* row:{&original.penetration,&original.normal,&original.point})for(float& x:*row)x=u(rng);
        floats(spheres,a.center);value(spheres,a.radius);word(spheres,a.surface_id);
        floats(spheres,b.center);value(spheres,b.radius);word(spheres,b.surface_id);
        floats(spheres,original.penetration);floats(spheres,original.normal);floats(spheres,original.point);
        word(spheres,original.material_a);word(spheres,original.material_b);word(spheres,original.flags);
        Arena arena{&original};Context context{0,0,&arena,0};sphere(&ia,&ib,&context);
        word(spheres,context.hit);floats(spheres,original.penetration);floats(spheres,original.normal);floats(spheres,original.point);
        word(spheres,original.material_a);word(spheres,original.material_b);word(spheres,original.flags);
        sphere_hits+=context.hit!=0;
        if(context.hit&&a.center==b.center)sphere_fallbacks++;
    }
    rays.flush();spheres.flush();meshes.flush();check(bool(rays)&&bool(spheres)&&bool(meshes),"Cannot save geometry numeric cases");
    std::ofstream report(folder/"report.json");report<<"{\"schema\":\"tm2020_geometry_gap_original_oracle_v1\",\"exeSha256\":\""<<executable_sha256
        <<"\",\"rayCases\":"<<cases<<",\"rayHits\":"<<ray_hits<<",\"twoSidedHits\":"<<two_sided_hits
        <<",\"rayCppPortBitExact\":true,\"sphereCases\":"<<cases<<",\"sphereHits\":"<<sphere_hits
        <<",\"sphereCoincidentFallbacks\":"<<sphere_fallbacks<<",\"fullMeshCases\":"<<cases<<",\"fullMeshHits\":"<<mesh_hits<<",\"fullMeshTwoSidedHits\":"<<mesh_two_hits
        <<",\"materialSkipInputs\":"<<material_skips<<",\"originalInstructionsExecuted\":true,\"sourceGameProcessAccessed\":false,\"completeExactSimulatorQualified\":false}\n";
    check(bool(report),"Cannot save original oracle report");std::cout<<"PASS GEOMETRY_ORACLE ray="<<cases<<" hits="<<ray_hits<<" two_sided_hits="<<two_sided_hits<<" sphere="<<cases<<'\n';
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
