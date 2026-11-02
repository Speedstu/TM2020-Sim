#include "tm2020/recovered_step.hpp"
#include <bit>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
int main(int argc,char**argv)try{
    if(argc!=3)throw std::runtime_error("Usage: vehicle_motion_probe input.bin output.bin");
    std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
    const auto size=input.tellg();
    if(!input||size<=0||size%56!=0||size>5600000)throw std::runtime_error("Invalid bounded motion input");
    input.seekg(0);std::ofstream output(argv[2],std::ios::binary);
    if(!output)throw std::runtime_error("Cannot create motion output");
    for(std::streamoff at=0;at<size;at+=56){
        std::array<float,14> row{};input.read(reinterpret_cast<char*>(row.data()),56);
        if(!input)throw std::runtime_error("Truncated motion input");
        VehicleSubstepMotion v;
        std::memcpy(v.linear_velocity.data(),row.data(),12);
        std::memcpy(v.angular_velocity.data(),row.data()+3,12);
        std::memcpy(v.vector_1348.data(),row.data()+6,12);
        std::memcpy(v.vector_1354.data(),row.data()+9,12);
        const auto result=std::bit_cast<std::uint32_t>(scaled_vehicle_substep_motion(v,row[12],row[13]));
        output.write(reinterpret_cast<const char*>(&result),4);
    }
    output.flush();if(!output)throw std::runtime_error("Motion output failed");
    std::cout<<"PASS PORTABLE VEHICLE MOTION BATCH cases="<<size/56<<'\n';
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
