#include "tm2020/recovered_mesh.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct Buffer {AabbNode* data;std::uint32_t count{},capacity{};};
struct Context {std::uint32_t width{},padding{};AabbPrimitive* input{};Buffer* output{};};
int main(int argc,char** argv)try{
    check(argc==3,"Usage: tree_builder_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,2> ranges{{{0x19ee90,0x19fb9c},{0x1a0890,0x1a08c9}}};ArithmeticImage image(argv[1],ranges);
    using Build=void(*)(void*,std::uint32_t,std::uint32_t,std::uint32_t,std::uint32_t*);const auto original=reinterpret_cast<Build>(image.base+0x19fad0);
    std::mt19937_64 rng(0x2026102308);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;std::size_t nodes_total{};std::uint32_t max_depth{};
    for(std::size_t n=0;n<cases;n++){
        const auto count=std::uint32_t(n%65),width=std::uint32_t(n%4+1);std::vector<AabbPrimitive> primitive(count);
        for(std::size_t j=0;j<count;j++){
            auto& p=primitive[j];p.index=std::uint32_t(j);
            for(std::size_t k=0;k<3;k++){p.center[k]=u(rng)*20;p.half_extent[k]=std::abs(u(rng))*3;}
            if(n%11==0)p.center={0,-0.f,0};
            if(n%13==0)p.center={float(j),float(j),float(j)};
            if(n%17==0)p.half_extent={0,-0.f,0};
            if(n%19==0)p.center={float(j%2),0,0};
        }
        auto input=primitive;std::vector<AabbNode> expected(count*2+1);Buffer buffer{expected.data(),0,std::uint32_t(expected.size())};Context context{width,0,input.data(),&buffer};std::uint32_t depth{};
        original(&context,0,count,0,&depth);const auto actual=build_aabb_tree(primitive,width);
        if(actual.size()!=buffer.count){std::cerr<<"Tree count case="<<n<<" expected="<<buffer.count<<" actual="<<actual.size()<<'\n';throw std::runtime_error("AABB node count differs");}
        for(std::size_t j=0;j<actual.size();j++)if(std::memcmp(&expected[j],&actual[j],sizeof(AabbNode))!=0){
            const auto* a=reinterpret_cast<const unsigned char*>(&expected[j]);const auto* b=reinterpret_cast<const unsigned char*>(&actual[j]);
            std::size_t k{};while(k<sizeof(AabbNode)&&a[k]==b[k])++k;
            std::cerr<<"Tree mismatch case="<<n<<" node="<<j<<" byte="<<k<<" expected="<<unsigned(a[k])<<" actual="<<unsigned(b[k])<<'\n';throw std::runtime_error("AABB construction differs from original");
        }
        nodes_total+=buffer.count;max_depth=std::max(max_depth,depth);
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_tree_builder_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases\":20000,\"bit_exact\":true,\"original_instructions_native\":true,\"root\":\"0x19fad0\",\"primitive_counts\":\"0..64\",\"leaf_widths\":\"1..4\","
        <<"\"nodes_compared\":"<<nodes_total<<",\"maximum_native_depth\":"<<max_depth<<",\"sufficient_native_capacity\":true,\"native_allocation_qualified\":false,"
        <<"\"top_level_mesh_constructor_qualified\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save tree builder report");std::cout<<"PASS TREE_BUILDER_ORACLE cases=20000 nodes="<<nodes_total<<" bit_exact=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"TREE_BUILDER_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
