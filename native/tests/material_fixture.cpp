#include "tm2020/recovered_material.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {float a{},b{};std::uint32_t class_a{},class_b{},runtime_class{},variant_a{},variant_b{},material_a{},material_b{},category_a{},category_b{};SurfaceResponseParameters parameters;};
static_assert(sizeof(Case)==64);
int main(int argc,char** argv)try{
    if(argc!=4)throw std::runtime_error("Usage: material_fixture input.bin output.bin defaults.bin");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid material case count");
    const SurfaceMaterialTable table;
    for(std::uint32_t n=0;n<count;n++){
        Case c{};if(!in.read(reinterpret_cast<char*>(&c),sizeof(c)))throw std::runtime_error("Truncated material fixture");
        const auto response=surface_response(table,std::uint16_t(c.material_a),std::uint16_t(c.material_b),{c.class_a,c.variant_a,std::uint8_t(c.category_a)},{c.class_b,c.variant_b,std::uint8_t(c.category_b)},c.runtime_class,c.parameters);
        const std::array<float,3> result{combine_restitution(c.a,c.b),response.friction,response.restitution};
        out.write(reinterpret_cast<const char*>(result.data()),sizeof(result));
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected material fixture bytes");
    out.flush();if(!out)throw std::runtime_error("Cannot write material fixture");
    std::ofstream defaults(argv[3],std::ios::binary);defaults.write(reinterpret_cast<const char*>(table.values.data()),sizeof(table.values));defaults.flush();if(!defaults)throw std::runtime_error("Cannot write material defaults");
    std::cout<<"PASS MATERIAL_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
