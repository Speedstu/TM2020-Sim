#include "tm2020/recovered_frames.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
int main(int argc,char** argv)try{
    check(argc==3,"Usage: frame_oracle original.exe report.json");const std::array<std::array<unsigned,2>,1> ranges{{{0x7f8db0,0x7f92cd}}};ArithmeticImage image(argv[1],ranges);
    using Run=void(*)(std::uint32_t,void*,const void*,int);const auto original=reinterpret_cast<Run>(image.base+0x7f8db0);std::mt19937_64 rng(0x2026102324);std::uniform_real_distribution<float> u(-1,1);
    for(std::size_t n=0;n<20000;n++){
        std::array<RigidState,12> initial{};std::array<std::array<float,3>,12> centers{};std::array<std::array<std::byte,0x50>,12> models{};std::array<const void*,12> pointers{};
        for(std::size_t j=0;j<12;j++){
            auto& s=initial[j];for(float& x:s.rotation)x=u(rng);for(auto* v:{&s.position,&s.linear_velocity,&s.angular_velocity})for(float& x:*v)x=u(rng)*5;for(float& x:s.quaternion)x=u(rng);for(float& x:centers[j])x=u(rng)*2;
            if(n%17==0){s={};s.position={-0.f,0,-0.f};centers[j]={0,-0.f,0};}
            std::memcpy(models[j].data()+0x40,centers[j].data(),12);pointers[j]=models[j].data();
        }
        const std::uint32_t count=n%13;
        for(bool subtract:{false,true}){
            auto native=initial,ported=initial;original(count,native.data(),pointers.data(),subtract?1:0);shift_model_center_frame(std::span(ported.data(),count),std::span(centers.data(),count),subtract);
            if(std::memcmp(native.data(),ported.data(),sizeof(native))){std::size_t at{};const auto* a=reinterpret_cast<const unsigned char*>(native.data());const auto* b=reinterpret_cast<const unsigned char*>(ported.data());while(at<sizeof(native)&&a[at]==b[at])++at;std::cerr<<"FRAME MISMATCH case="<<n<<" subtract="<<subtract<<" byte="<<at<<'\n';throw std::runtime_error("Center frame shift differs from complete original procedure");}
        }
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_model_frame_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":1,\"bit_exact\":true,\"entry_rva\":\"0x7f8db0\",\"both_sign_modes_tested_each_case\":true,\"body_counts\":[0,1,2,3,4,5,6,7,8,9,10,11,12],\"unrolled_and_tail_paths_qualified\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";report.flush();check(bool(report),"Cannot write center frame report");
    std::cout<<"PASS MODEL_FRAME_ORACLE operations=1 cases=20000 both_signs=true unroll_and_tail=true bit_exact=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
