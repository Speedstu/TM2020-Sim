#include "tm2020/recovered_position.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {
    std::array<RigidState,3> states;
    std::array<VelocityCoefficients,3> coefficients;
    PositionParameters parameters;
    std::array<DynamicPositionConstraint,2> dynamic;
    std::array<StaticPositionConstraint,2> fixed;
    std::uint32_t count;
};
static_assert(sizeof(Case)==496);
int main(int argc,char** argv)try{
    if(argc!=3)throw std::runtime_error("Usage: position_fixture input.bin output.bin");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid fixture count");
    for(std::uint32_t n=0;n<count;n++){
        Case c{};if(!in.read(reinterpret_cast<char*>(&c),sizeof(c))||c.count>2)throw std::runtime_error("Invalid position fixture");
        auto dynamic=c.states,fixed=c.states;
        solve_dynamic_positions(dynamic,c.coefficients,std::span(c.dynamic.data(),c.count),c.parameters);
        solve_static_positions(fixed,c.coefficients,std::span(c.fixed.data(),c.count),c.parameters);
        out.write(reinterpret_cast<const char*>(dynamic.data()),sizeof(dynamic));out.write(reinterpret_cast<const char*>(fixed.data()),sizeof(fixed));
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected fixture data");
    out.flush();if(!out)throw std::runtime_error("Cannot save position fixture");std::cout<<"PASS POSITION_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
