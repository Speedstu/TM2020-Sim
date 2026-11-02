#include "tm2020/recovered_activation.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
int main(int argc,char**argv)try{
    check(argc==3,"Usage: activation_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,3> ranges{{{0x7f4760,0x7f4774},{0x7f5130,0x7f513b},{0x800c00,0x800dc7}}};
    ArithmeticImage image(argv[1],ranges);
    using Fixed=bool(*)(const void*,const void*);
    using Prepare=void(*)(std::uint32_t,const void*,const void*,const void*,void*,const void*,void*,const void*);
    const auto fixed=reinterpret_cast<Fixed>(image.base+0x7f4760);
    const auto prepare=reinterpret_cast<Prepare>(image.base+0x800c00);
    std::mt19937_64 rng(0x2026102502);std::uniform_real_distribution<float> unit(-1,1);
    for(std::size_t n=0;n<20000;n++){
        constexpr unsigned capacity=8;
        std::array<std::array<std::byte,0x60>,capacity> models{};
        std::array<std::array<std::byte,0x18>,capacity> shapes{};
        std::array<std::array<std::byte,0x38>,capacity> items{};
        std::array<std::array<std::byte,8>,capacity> sleep{};
        std::array<const void*,capacity> model_ptrs{},shape_ptrs{};
        std::array<std::uint8_t,capacity> flags{};
        std::array<VelocityCoefficients,capacity> coefficients{};
        std::array<BodyActivationInput,capacity> inputs{};
        std::array<BodyActivationState,capacity> states{};
        std::array<std::uint32_t,32> ids{};for(auto&x:ids)x=std::uint32_t(rng());const auto* map=ids.data();
        for(unsigned j=0;j<capacity;j++){
            auto& p=inputs[j];p.model_mass=1.f+std::abs(unit(rng))*9999.f;p.item_mass_offset=unit(rng)*p.model_mass*.9f;
            p.model_word_50=n%3?0:std::uint32_t(rng())|1;
            p.source_flags=std::uint8_t(n+j*37);p.shape_present=(n+j)%3!=0;p.shape_tag_11=(n+j)%2?7:std::uint8_t(rng());p.sleep_word_4=(n+j)%5==0?0xffff:std::uint16_t(rng()%0xffff);
            std::memcpy(models[j].data()+0x18,&p.model_mass,4);std::memcpy(models[j].data()+0x50,&p.model_word_50,4);model_ptrs[j]=models[j].data();
            std::memcpy(shapes[j].data()+0x11,&p.shape_tag_11,1);shape_ptrs[j]=p.shape_present?shapes[j].data():nullptr;flags[j]=p.source_flags;
            std::memcpy(sleep[j].data()+4,&p.sleep_word_4,2);
            for(auto& x:items[j])x=std::byte(rng());
            auto& s=states[j];s.flags=std::uint32_t(rng());s.related_item_id=(n+j)%4==0?0xffffffff:std::uint32_t(rng()%ids.size());s.related_state_index=std::uint32_t(rng());
            for(unsigned k=0;k<3;k++)s.coefficients[k]=std::bit_cast<float>(std::uint32_t(rng()));
            s.coefficients[3]=unit(rng)*100;
            coefficients[j]=s.coefficients;std::memcpy(items[j].data()+4,&s.flags,4);std::memcpy(items[j].data()+8,&p.item_mass_offset,4);std::memcpy(items[j].data()+0x28,&s.related_item_id,4);std::memcpy(items[j].data()+0x2c,&s.related_state_index,4);
            check(fixed(&flags[j],models[j].data())==model_fixed_for_flags(p.model_word_50,p.source_flags),"Complete model-fixed helper differs");
        }
        const auto count=std::uint32_t(n%9);const auto initial_items=items;const auto initial_coefficients=coefficients;
        const auto models_before=models;const auto shapes_before=shapes;const auto flags_before=flags;const auto sleep_before=sleep;const auto ids_before=ids;
        prepare(count,&map,model_ptrs.data(),flags.data(),items.data(),sleep.data(),coefficients.data(),shape_ptrs.data());
        prepare_body_activation(std::span(states.data(),count),std::span(inputs.data(),count),ids);
        auto expected=initial_items;auto expected_coefficients=initial_coefficients;
        for(unsigned j=0;j<count;j++){std::memcpy(expected[j].data()+4,&states[j].flags,4);std::memcpy(expected[j].data()+0x2c,&states[j].related_state_index,4);expected_coefficients[j]=states[j].coefficients;}
        if(std::memcmp(items.data(),expected.data(),sizeof(items))||std::memcmp(coefficients.data(),expected_coefficients.data(),sizeof(coefficients))){std::cerr<<"ACTIVATION_MISMATCH case="<<n<<" count="<<count<<'\n';throw std::runtime_error("Complete activation batch differs");}
        check(models==models_before&&shapes==shapes_before&&flags==flags_before&&sleep==sleep_before&&ids==ids_before,"Original activation changed read-only inputs");
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_body_activation_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":2,\"bit_exact\":true,\"all_source_flag_bytes\":true,\"body_counts\":[0,1,2,3,4,5,6,7,8],\"complete_original_procedures\":true,\"all_56_item_bytes_and_16_coefficient_bytes_checked\":true,\"read_only_inputs_unchanged\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"game_process_accessed\":false,\"complete_sleep_scheduler\":false}\n";report.flush();check(bool(report),"Cannot save activation report");
    std::cout<<"PASS ACTIVATION_ORACLE operations=2 cases_each=20000 bit_exact=true complete_native_batch=true all_flags=true\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
