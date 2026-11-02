#include "tm2020/recovered_joint_position.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
template<class T>void read(std::istream& in,T& value){if(!in.read(reinterpret_cast<char*>(&value),sizeof(value)))throw std::runtime_error("Truncated position island fixture");}
template<class T>void array(std::istream& in,std::vector<T>& values){std::uint32_t count{};read(in,count);if(count>2)throw std::runtime_error("Position island fixture count exceeds domain");values.resize(count);for(auto& v:values)read(in,v);}
int main(int argc,char** argv)try{
    if(argc!=3)throw std::runtime_error("Usage: position_island_fixture input output");std::ifstream in(argv[1],std::ios::binary);std::ofstream out(argv[2],std::ios::binary);std::uint32_t cases{};read(in,cases);if(cases>100000)throw std::runtime_error("Too many position island fixtures");
    for(std::uint32_t n=0;n<cases;n++){
        std::array<RigidState,3> states{};std::array<VelocityCoefficients,3> coefficients{};PositionParameters parameters{};std::uint32_t iterations{},count{};
        read(in,states);read(in,coefficients);read(in,parameters);read(in,iterations);read(in,count);if(count>3)throw std::runtime_error("Too many position islands");
        std::vector<PositionIsland> islands(count);for(auto& i:islands){array(in,i.dynamic_orientation);array(in,i.static_orientation);array(in,i.dynamic_anchors);array(in,i.static_anchors);array(in,i.dynamic_projection);array(in,i.static_projection);array(in,i.dynamic_contacts);array(in,i.static_contacts);}
        solve_position_islands(states,coefficients,islands,iterations,parameters);out.write(reinterpret_cast<const char*>(states.data()),sizeof(states));
    }
    if(!out)throw std::runtime_error("Cannot write position island fixture");std::cout<<"PASS POSITION_ISLAND_FIXTURE cases="<<cases<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
