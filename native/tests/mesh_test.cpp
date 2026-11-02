#include "tm2020/recovered_mesh.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
void check(bool b,const char* why){if(!b)throw std::runtime_error(why);}
int main()try{
    const std::array<std::array<float,3>,4> vertices{{{-2,0,-2},{-2,0,2},{2,0,2},{2,0,-2}}};
    const std::array<IndexedTriangle,2> raw{{{{0,1,2},11,0},{{0,2,3},12,0}}};
    const auto cooked=cook_triangles(vertices,raw),empty=cook_triangles(vertices,{});
    check(empty.empty()&&cooked.size()==2&&cooked[0].normal==std::array{0.f,1.f,0.f},"Cooked face normal wrong");
    const auto boxes=triangle_aabbs(vertices,raw);const auto tree=build_aabb_tree(boxes);
    check(tree.size()==2&&tree[0].packed==1&&tree[1].packed==3,"Native leaf-group order wrong");
    CookedMeshView mesh{vertices,cooked,tree,{}};Sphere sphere{{0,.5f,0},1,7};
    const auto contacts=collide_sphere_mesh(sphere,mesh);
    check(contacts.size()==2,"Shared triangle edge contacts were deduplicated");
    for(std::size_t i=0;i<contacts.size();i++){
        const auto& c=contacts[i];check(c.triangle_index==i&&c.geometry.surface_id_a==7&&c.geometry.surface_id_b==11+i,"Contact order/surface IDs lost");
        check(c.geometry.normal[1]==1&&c.geometry.penetration_vector[1]==.5f&&c.geometry.surface_point_a[1]==-.5f&&c.surface_point_b[1]==0&&c.geometry.flags==3,"Face geometry wrong");
    }
    sphere.center={0,-.5f,0};check(collide_sphere_mesh(sphere,mesh).empty(),"Back-face contact admitted");
    sphere.center={0,1,0};check(collide_sphere_mesh(sphere,mesh).size()==2,"Native mesh tangency changed");
    sphere.center={-2.2f,.2f,0};sphere.radius=.5f;const auto edge=collide_sphere_mesh(sphere,mesh);check(!edge.empty()&&!(edge[0].geometry.flags&1),"Edge contact classified as face");
    sphere.center={2.2f,.2f,2.2f};const auto vertex=collide_sphere_mesh(sphere,mesh);check(!vertex.empty()&&!(vertex[0].geometry.flags&1),"Vertex contact missing");
    mesh.transform={{{0,-1,0,1,0,0,0,0,1}},{10,2,3}};sphere={{9.5f,2,3},1,7};
    const auto rotated=collide_sphere_mesh(sphere,mesh);check(rotated.size()==2&&rotated[0].geometry.normal[0]==-1&&rotated[0].surface_point_b[0]==10,"Mesh coordinate transforms wrong");
    const std::array<AabbNode,1> invalid{{{{},{},0}}};bool denied=false;
    try{query_aabb_tree(invalid,{},{1,1,1});}catch(const std::invalid_argument&){denied=true;}
    check(denied,"Zero subtree skip was not rejected");
    auto bad=raw;bad[1].vertices[2]=4;denied=false;
    try{cook_triangles(vertices,bad);}catch(const std::invalid_argument&){denied=true;}
    check(denied,"Invalid cooking index was not rejected");
    std::array<AabbPrimitive,32> identical{};for(std::size_t i=0;i<identical.size();i++)identical[i]={{{0,0,0}},{{1,1,1}},std::uint32_t(i)};
    const auto balanced=build_aabb_tree(identical,1);const auto leaves=query_aabb_tree(balanced,{},{1,1,1});
    check(balanced.size()==63&&leaves.size()==32,"Equal-center fallback failed to build a balanced tree");
    for(std::size_t i=0;i<leaves.size();i++)check((balanced[leaves[i]].packed>>1)==i,"Equal-center fallback changed native order");
    std::cout<<"PASS MESH_PIPELINE cooking=true tree=true face_edge_vertex=true transform=true native_order=true invalid_geometry_rejected=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
