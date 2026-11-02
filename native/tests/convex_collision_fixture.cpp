#include "convex_box_fixture.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {MeshTransform a,b;ConvexVector half_a{},half_b{};std::uint16_t id_a{},id_b{};};
static_assert(sizeof(Case)==124);
int main(int argc,char** argv)try{
    if(argc!=3)throw std::runtime_error("Usage: convex_collision_fixture input.bin output.bin");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid convex case count");
    for(std::uint32_t n=0;n<count;n++){
        Case c{};if(!in.read(reinterpret_cast<char*>(&c),sizeof(c)))throw std::runtime_error("Truncated convex case");
        const tm2020::testing::BoxGeometry box_a(c.half_a),box_b(c.half_b);const ConvexInstance a{box_a.view(),c.a,c.id_a},b{box_b.view(),c.b,c.id_b};
        const auto result=collide_convex(a,b),boolean=collide_convex(a,b,false);
        if(result.overlap!=boolean.overlap||!boolean.contacts.empty())throw std::runtime_error("Convex boolean emission gate differs");
        const std::array<std::uint32_t,2> header{std::uint32_t(result.overlap),std::uint32_t(result.contacts.size())};
        out.write(reinterpret_cast<const char*>(header.data()),sizeof(header));out.write(reinterpret_cast<const char*>(result.contacts.data()),static_cast<std::streamsize>(result.contacts.size()*sizeof(ConvexContact)));
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected convex fixture bytes");
    out.flush();if(!out)throw std::runtime_error("Cannot write convex output");std::cout<<"PASS CONVEX_COLLISION_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
