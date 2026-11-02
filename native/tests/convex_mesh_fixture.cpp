#include "convex_box_fixture.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {MeshTransform a,mesh;ConvexVector half{};std::uint16_t id{},padding{};};
static_assert(sizeof(Case)==112);
int main(int argc,char** argv)try{
    if(argc!=3)throw std::runtime_error("Usage: convex_mesh_fixture input.bin output.bin");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid convex mesh count");
    const std::array<ConvexVector,7> vertices{{{-2,0,-2},{-2,0,2},{2,0,2},{2,0,-2},{-2,0,-2},{2,0,-2},{2,3,-2}}};
    const std::array<CookedTriangle,3> triangles{{{{0,1,0},0,{0,1,2},11,0},{{0,1,0},0,{0,2,3},12,0},{{0,0,1},2,{4,5,6},13,0}}};
    const std::array<AabbNode,5> tree{{{{0,1.5f,0},{2,1.5f,2},10},{{0,0,0},{2,0,2},6},{{0,0,0},{2,0,2},1},{{0,0,0},{2,0,2},3},{{0,1.5f,-2},{2,1.5f,0},5}}};
    for(std::uint32_t n=0;n<count;n++){
        Case c{};if(!in.read(reinterpret_cast<char*>(&c),sizeof(c)))throw std::runtime_error("Truncated convex mesh case");
        const tm2020::testing::BoxGeometry box(c.half);const ConvexInstance a{box.view(),c.a,c.id};
        const std::size_t nodes=n%37==0?0:5;CookedMeshView mesh{vertices,triangles,std::span(tree.data(),nodes),c.mesh};
        std::vector<CookedTriangle> repeated;std::vector<AabbNode> repeated_tree;
        if(c.padding==1){
            for(std::uint32_t j=0;j<129;j++){auto triangle=triangles[0];triangle.surface_id=std::uint16_t(j);repeated.push_back(triangle);repeated_tree.push_back({{0,0,0},{2,0,2},(j<<1)|1u});}
            mesh.triangles=repeated;mesh.tree=repeated_tree;
        }
        const auto result=collide_convex_mesh(a,mesh,{{},c.half,0});const auto boolean=collide_convex_mesh(a,mesh,{{},c.half,0},false);
        if(result.overlap!=boolean.overlap||!boolean.contacts.empty())throw std::runtime_error("Convex mesh boolean gate differs");
        const std::array<std::uint32_t,2> header{std::uint32_t(result.overlap),std::uint32_t(result.contacts.size())};
        out.write(reinterpret_cast<const char*>(header.data()),sizeof(header));out.write(reinterpret_cast<const char*>(result.contacts.data()),static_cast<std::streamsize>(result.contacts.size()*sizeof(ConvexContact)));
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected convex mesh input bytes");
    out.flush();if(!out)throw std::runtime_error("Cannot write convex mesh output");std::cout<<"PASS CONVEX_MESH_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
