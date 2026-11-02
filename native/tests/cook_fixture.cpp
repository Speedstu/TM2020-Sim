#include "tm2020/recovered_mesh.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {std::array<std::array<float,3>,9> vertices;std::array<IndexedTriangle,9> triangles;std::uint32_t count;};
static_assert(sizeof(Case)==256);
int main(int argc,char** argv)try{
    if(argc!=3&&argc!=4)throw std::runtime_error("Usage: cook_fixture input.bin output.bin [bounds]");
    const bool bounds=argc==4&&std::string(argv[3])=="bounds";
    if(argc==4&&!bounds)throw std::runtime_error("Unknown cooking fixture mode");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid cooking case count");
    for(std::uint32_t n=0;n<count;n++){
        Case c{};if(!in.read(reinterpret_cast<char*>(&c),sizeof(c))||c.count>9)throw std::runtime_error("Invalid cooking fixture");
        if(bounds){
            const auto boxes=triangle_aabbs(c.vertices,std::span(c.triangles.data(),c.count));std::array<AabbPrimitive,9> result{};
            std::copy(boxes.begin(),boxes.end(),result.begin());out.write(reinterpret_cast<const char*>(result.data()),sizeof(result));
        }else{
            const auto cooked=cook_triangles(c.vertices,std::span(c.triangles.data(),c.count));std::array<CookedTriangle,9> result{};
            std::copy(cooked.begin(),cooked.end(),result.begin());out.write(reinterpret_cast<const char*>(result.data()),sizeof(result));
        }
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected cooking fixture bytes");
    out.flush();if(!out)throw std::runtime_error("Cannot save cooking fixture");std::cout<<"PASS COOK_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
