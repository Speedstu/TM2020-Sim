#include "tm2020/recovered_mesh.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct ContactRecord {
    const void* a{};const void* b{};
    std::array<float,3> penetration{},normal{},point_a{},triangle_normal{},point_b{};
    std::uint32_t opaque{};std::uint16_t id_a{},id_b{};std::uint32_t flags{};
};
static_assert(sizeof(ContactRecord)==88&&offsetof(ContactRecord,point_b)==0x40);
struct Instance {const void* shape{};std::array<float,9> rotation{1,0,0,0,1,0,0,0,1};std::array<float,3> center{};};
static_assert(sizeof(Instance)==56&&offsetof(Instance,center)==0x2c);
struct Arena {ContactRecord* data;std::uint32_t count{},reserved{},capacity{};};
struct Context {std::uint32_t hit{},reserved{};Arena* arena{};std::uint32_t early_exit{};};
struct Iterator {
    const AabbNode* nodes;std::uint32_t count{},index{0xffffffffu};const AabbNode* current{};
    std::uint64_t padding{};std::array<float,4> center{},half{};
};
static_assert(offsetof(Iterator,center)==0x20);
template<class T>void same(const T& a,const T& b,std::size_t n,const char* field){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);
    std::size_t i{};while(i<sizeof(T)&&x[i]==y[i])++i;
    std::cerr<<"MISMATCH mesh case="<<n<<" field="<<field<<" byte="<<i<<" expected="<<unsigned(x[i])<<" actual="<<unsigned(y[i])<<'\n';
    if(sizeof(T)>=4){float f{},g{};std::memcpy(&f,x+(i&~3),4);std::memcpy(&g,y+(i&~3),4);std::cerr<<f<<" / "<<g<<'\n';}
    throw std::runtime_error("Mesh kernel differs from original instructions");
}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: mesh_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,4> ranges{{{0x1af710,0x1b02d1},{0x1a01b0,0x1a028e},
        {0x197890,0x1978b2},{0x1521930,0x1521945}}};ArithmeticImage image(argv[1],ranges);
    using Collide=void(*)(const void*,const void*,void*);using Query=int(*)(void*);
    const auto original=reinterpret_cast<Collide>(image.base+0x1af710);const auto query=reinterpret_cast<Query>(image.base+0x1a01b0);
    std::mt19937_64 rng(0x2026102306);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;
    std::size_t faces{},edges_vertices{},overlaps{},empty{},leaves{};
    for(std::size_t n=0;n<cases;n++){
        std::array<std::array<float,3>,7> vertices{{{-2,0,-2},{-2,0,2},{2,0,2},{2,0,-2},{-2,0,-2},{2,0,-2},{2,3,-2}}};
        if(n%31==0)vertices[1]=vertices[0];
        const std::array<CookedTriangle,3> triangles{{{{0,1,0},0,{0,1,2},11,0},{{0,1,0},0,{0,2,3},12,0},{{0,0,1},0,{4,5,6},13,0}}};
        const std::array<AabbNode,5> tree{{{{0,1.5f,0},{2,1.5f,2},10},{{0,0,0},{2,0,2},6},
            {{0,0,0},{2,0,2},1},{{0,0,0},{2,0,2},3},{{0,1.5f,-2},{2,1.5f,0},5}}};
        const std::size_t node_count=n%37==0?0:5;
        MeshTransform transform{};Sphere sphere{};sphere.center={u(rng)*3,u(rng)*2,u(rng)*3};sphere.radius=.05f+std::abs(u(rng));sphere.surface_id=std::uint16_t(rng());
        // Boundary cases stay in identity space; random rotated/translated
        // meshes exercise both coordinate transforms in the original routine.
        if(n%3==0){
            const float angle=u(rng)*3.14f;const float sine=std::sin(angle*.5f),cosine=std::cos(angle*.5f);
            const std::array axis{u(rng),u(rng),u(rng)};const float length=std::sqrt((axis[0]*axis[0]+axis[1]*axis[1])+axis[2]*axis[2]);
            quaternion_to_matrix(transform.rotation,{cosine,axis[0]/length*sine,axis[1]/length*sine,axis[2]/length*sine});transform.translation={u(rng),u(rng),u(rng)};
        }
        if(n%11==0){transform={};sphere.center={0,.5f,0};sphere.radius=1;}
        if(n%13==0){transform={};sphere.center={-2.2f,.2f,0};sphere.radius=.5f;}
        if(n%17==0){transform={};sphere.center={2.2f,.2f,2.2f};sphere.radius=.5f;}
        if(n%19==0){transform={};sphere.center={0,0,0};sphere.radius=0;}
        if(n%23==0){transform={};sphere.center={0,-.1f,0};sphere.radius=.5f;}
        const std::array<float,3> query_center{u(rng)*4,u(rng)*4,u(rng)*4},query_half{std::abs(u(rng))*3,std::abs(u(rng))*3,std::abs(u(rng))*3};
        Iterator iterator{tree.data(),std::uint32_t(node_count)};iterator.center={0,query_center[2],query_center[1],query_center[0]};iterator.half={0,query_half[2],query_half[1],query_half[0]};
        std::vector<std::uint32_t> expected_leaves;while(query(&iterator))expected_leaves.push_back(iterator.index);
        const auto actual_leaves=query_aabb_tree(std::span(tree.data(),node_count),query_center,query_half);
        check(expected_leaves==actual_leaves,"AABB leaf sequence differs");leaves+=expected_leaves.size();
        std::array<std::byte,48> sphere_shape{};std::array<std::byte,0x60> mesh_shape{};
        std::memcpy(sphere_shape.data()+0x28,&sphere.radius,4);std::memcpy(sphere_shape.data()+0x20,&sphere.surface_id,2);
        const auto* vp=vertices.data();const auto* tp=triangles.data();const auto* np=tree.data();const auto nc=std::uint32_t(node_count);
        std::memcpy(mesh_shape.data()+0x20,&vp,8);std::memcpy(mesh_shape.data()+0x40,&tp,8);std::memcpy(mesh_shape.data()+0x50,&np,8);std::memcpy(mesh_shape.data()+0x58,&nc,4);
        const Instance a{sphere_shape.data(),{1,0,0,0,1,0,0,0,1},sphere.center},b{mesh_shape.data(),transform.rotation,transform.translation};
        std::array<ContactRecord,3> native{};const auto flags=std::uint32_t(rng());for(auto& c:native){c.flags=flags;c.opaque=0x12345678;}
        Arena arena{native.data(),0,0,3};Context context{0,0,&arena,0};original(&a,&b,&context);
        CookedMeshView view{vertices,triangles,std::span(tree.data(),node_count),transform};const auto ported=collide_sphere_mesh(sphere,view,flags);
        if(arena.count!=ported.size()){std::cerr<<"Count mismatch case="<<n<<" original="<<arena.count<<" ported="<<ported.size()<<'\n';throw std::runtime_error("Mesh contact count differs");}
        check((context.hit!=0)==!ported.empty(),"Mesh hit flag differs");
        for(std::size_t j=0;j<ported.size();j++){
            const auto& e=native[j];const auto& p=ported[j];same(e.penetration,p.geometry.penetration_vector,n,"penetration");same(e.normal,p.geometry.normal,n,"normal");
            same(e.point_a,p.geometry.surface_point_a,n,"sphere point");same(e.point_b,p.surface_point_b,n,"triangle point");same(e.triangle_normal,p.triangle_normal,n,"triangle normal");
            same(e.id_a,p.geometry.surface_id_a,n,"surface A");same(e.id_b,p.geometry.surface_id_b,n,"surface B");same(e.flags,p.geometry.flags,n,"flags");
            check(e.a==&a&&e.b==&b&&e.opaque==0x12345678,"Mesh ownership/reserved bytes changed");
            if(e.flags&1)++faces;else ++edges_vertices;
        }
        if(ported.empty())++empty;else ++overlaps;
        Context boolean{};original(&a,&b,&boolean);check((boolean.hit!=0)==!ported.empty()&&boolean.early_exit==unsigned(!ported.empty()),"Original mesh boolean query differs");
        if(!ported.empty()){
            std::array<ContactRecord,3> untouched{};Arena gated{untouched.data(),0,0,3};Context early{0,0,&gated,1};original(&a,&b,&early);
            check(early.hit==1&&gated.count==0,"Original emission gate ignored");
        }
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_mesh_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_operation\":20000,\"operations\":2,\"bit_exact\":true,\"original_instructions_native\":true,\"original_code_modified\":false,"
        <<"\"face_contacts\":"<<faces<<",\"edge_vertex_contacts\":"<<edges_vertices<<",\"overlap_queries\":"<<overlaps<<",\"empty_queries\":"<<empty
        <<",\"aabb_leaves_returned\":"<<leaves<<",\"native_boolean_and_emission_gates_checked\":true,\"cooked_data_supplied_by_caller\":true,"
        <<"\"stadium_mesh_assets_recovered\":false,\"convex_mesh_ported\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save mesh oracle");std::cout<<"PASS MESH_ORACLE cases_each=20000 bit_exact=true face_contacts="<<faces<<" edge_vertex_contacts="<<edges_vertices<<" complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"MESH_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
