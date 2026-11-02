// Binary test transport for independently emulated original instructions.
#include "tm2020/recovered_rigid.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {
    RigidState state;ForceAccumulator forces;std::array<float,4> coefficients;
    std::uint32_t flags;float model_gravity,item_offset,item_multiplier;
    std::uint32_t sleeping;std::array<float,3> gravity;std::uint32_t attenuate;
    float threshold,multiplier,interval;
};
static_assert(sizeof(Case)==176);
int main(int argc,char** argv)try{
    if(argc!=3)throw std::invalid_argument("Usage: force_fixture input.bin output.bin");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid fixture count");
    for(std::uint32_t i=0;i<count;i++){
        Case c;if(!in.read(reinterpret_cast<char*>(&c),sizeof(c)))throw std::runtime_error("Truncated fixture");
        VelocityStepParameters p{c.coefficients,c.flags,c.model_gravity,c.item_offset,c.item_multiplier,c.sleeping!=0};
        GravityEnvironment env{c.gravity,c.attenuate!=0,c.threshold,c.multiplier};
        integrate_forces(c.state,c.forces,p,env,c.interval);
        out.write(reinterpret_cast<const char*>(&c.state),sizeof(c.state));out.write(reinterpret_cast<const char*>(&c.forces),sizeof(c.forces));
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected fixture data");
    out.flush();if(!out)throw std::runtime_error("Cannot write fixture output");
    std::cout<<"PASS FORCE_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
