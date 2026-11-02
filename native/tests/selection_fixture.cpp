#include "tm2020/recovered_contacts.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
struct Case {
    std::array<float,3> velocity;float limit,interval;
    std::uint32_t mode,all_contacts,selected;
    float stiffness,damping,rest_length;
    std::array<float,4> lengths,speeds;std::array<std::uint32_t,4> contacts;
};
static_assert(sizeof(Case)==92);
int main(int argc,char** argv)try{
    if(argc!=3)throw std::invalid_argument("Usage: selection_fixture input.bin output.bin");
    std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t count{};
    if(!in.read(reinterpret_cast<char*>(&count),4)||count>100000)throw std::runtime_error("Invalid fixture count");
    for(std::uint32_t j=0;j<count;j++){
        Case c;if(!in.read(reinterpret_cast<char*>(&c),sizeof(c)))throw std::runtime_error("Truncated selection fixture");
        const float fraction=select_pose_fraction(c.velocity,c.limit,c.interval);float force=123.f;
        SuspensionParameters p{c.mode,c.all_contacts!=0,c.stiffness,c.damping,c.rest_length};std::array<SuspensionWheelState,4> wheels;
        for(std::size_t k=0;k<4;k++)wheels[k]={c.lengths[k],c.speeds[k],c.contacts[k]!=0};
        const std::uint32_t active=suspension_mode2(p,wheels,c.selected,force);
        out.write(reinterpret_cast<const char*>(&fraction),4);out.write(reinterpret_cast<const char*>(&active),4);out.write(reinterpret_cast<const char*>(&force),4);
    }
    if(in.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Unexpected fixture bytes");
    out.flush();if(!out)throw std::runtime_error("Cannot write selection fixture");
    std::cout<<"PASS SELECTION_FIXTURE cases="<<count<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
