#include "tm2020/recovered_activation.hpp"
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace tm2020::recovered;
static std::uint32_t read_word(std::istream& input){
    std::uint32_t value{};input.read(reinterpret_cast<char*>(&value),4);
    if(!input)throw std::runtime_error("Truncated active slot evidence");return value;
}
int main(int argc,char** argv)try{
    if(argc!=2)throw std::runtime_error("active_slot_oracle numeric_cases");
    std::ifstream input(argv[1],std::ios::binary);std::array<char,8> magic{};input.read(magic.data(),8);
    if(!input||magic!=std::array<char,8>{'T','M','A','C','T','0','0','1'})throw std::runtime_error("Unknown case format");
    auto cases=read_word(input);if(cases!=20000)throw std::runtime_error("Unexpected case count");
    unsigned inserted=0;
    for(unsigned i=0;i<cases;i++){
        WakeIndexState state{};state.rest_since=read_word(input);const auto rest=state.rest_since;const auto packed=read_word(input);
        state.active_index=std::uint16_t(packed);state.reserved=std::uint8_t(packed>>16);state.queued=std::uint8_t(packed>>24);
        const auto slot=read_word(input);auto count=read_word(input);std::array<std::uint32_t,16> active{};
        for(auto& v:active)v=read_word(input);
        const auto expected_packed=read_word(input),expected_count=read_word(input);
        std::array<std::uint32_t,16> expected{};for(auto& v:expected)v=read_word(input);
        inserted+=activate_body_slot(state,slot,active,count);
        const auto actual=std::uint32_t(state.active_index)|(std::uint32_t(state.reserved)<<16)|(std::uint32_t(state.queued)<<24);
        if(state.rest_since!=rest||actual!=expected_packed||count!=expected_count||active!=expected)throw std::runtime_error("Activation differs from original instruction slice");
    }
    if(input.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Trailing evidence bytes");
    std::cout<<"PASS ACTIVE_SLOT original_slice_cases="<<cases<<" inserted="<<inserted<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
