#include "tm2020/recovered_step.hpp"
#include <array>
#include <bit>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
int main(int argc,char**argv)try{
    if(argc!=3)throw std::runtime_error("Usage: vehicle_substep_probe input.bin output.bin");
    std::ifstream input(argv[1],std::ios::binary|std::ios::ate);
    const auto size=input.tellg();
    if(!input||size<=0||size%16!=0||size>1600000)throw std::runtime_error("Invalid bounded substep input");
    input.seekg(0);
    std::ofstream output(argv[2],std::ios::binary);
    if(!output)throw std::runtime_error("Cannot create substep output");
    for(std::streamoff at=0;at<size;at+=16){
        std::array<std::uint32_t,4> row{};
        input.read(reinterpret_cast<char*>(row.data()),16);
        if(!input)throw std::runtime_error("Truncated substep input");
        const auto result=select_vehicle_substeps(std::bit_cast<float>(row[0]),std::bit_cast<float>(row[1]),
            std::bit_cast<float>(row[2]),std::bit_cast<float>(row[3]));
        const std::array<std::uint32_t,5> words{result.substeps,
            std::bit_cast<std::uint32_t>(result.repeated_unscaled_interval),
            std::bit_cast<std::uint32_t>(result.repeated_scaled_interval),
            std::bit_cast<std::uint32_t>(result.total_scaled_interval),
            std::bit_cast<std::uint32_t>(vehicle_last_substep_interval(result))};
        output.write(reinterpret_cast<const char*>(words.data()),20);
        output.write(reinterpret_cast<const char*>(&result.timestamp_subtrahend_nanoseconds),8);
    }
    output.flush();if(!output)throw std::runtime_error("Substep output failed");
    std::cout<<"PASS PORTABLE VEHICLE SUBSTEP BATCH cases="<<size/16<<'\n';
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
