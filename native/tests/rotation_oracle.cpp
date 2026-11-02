#include "tm2020/recovered_position.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
int main(int argc,char** argv)try{
    check(argc==3,"Usage: rotation_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,5> ranges{{{0x85e4f0,0x85eab0},{0x192c70,0x192ce0},
        {0x195c010,0x195c2d9},{0x195d240,0x195d5cf},{0x1886d0,0x188800}}};ArithmeticImage image(argv[1],ranges);
    using Fn=void(*)(void*,const void*);const auto positive=reinterpret_cast<Fn>(image.base+0x85e4f0),negative=reinterpret_cast<Fn>(image.base+0x85e7d0);
    std::mt19937_64 rng(0x2026102303);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t count=20000;
    for(std::size_t n=0;n<count;n++){
        RigidState s{};for(float& x:s.quaternion)x=u(rng);
        for(float& x:s.rotation)x=u(rng);for(float& x:s.position)x=u(rng)*5;
        std::array<float,3> correction{u(rng)*.8f,u(rng)*.8f,u(rng)*.8f};
        if(n%5==0)for(float& x:correction)x=x*1e-6f;
        if(n%7==0)correction={-0.f,0,0};
        if(n%11==0)s.quaternion={};if(n%13==0)for(float& x:s.quaternion)x=x*1e6f;
        if(n%17==0)for(float& x:s.quaternion)x=x*1e-20f;
        for(unsigned sign=0;sign<2;sign++){
            auto expected=s,actual=s;(sign?negative:positive)(&expected,&correction);correct_rotation(actual,correction,sign!=0);
            if(std::memcmp(&expected,&actual,sizeof(s))!=0){
                const auto* a=reinterpret_cast<const unsigned char*>(&expected);const auto* b=reinterpret_cast<const unsigned char*>(&actual);
                std::size_t off{};while(off<sizeof(s)&&a[off]==b[off])++off;
                std::cerr<<"MISMATCH rotation case="<<n<<" sign="<<sign<<" byte="<<off<<" expected="<<unsigned(a[off])<<" actual="<<unsigned(b[off])<<'\n';
                throw std::runtime_error("Rotation correction differs from original");
            }
        }
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_rotation_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_sign\":20000,\"bit_exact\":true,\"correction_norm_limit\":1.57079625,\"math_dispatch\":\"original scalar SSE2 flag 0\","
        <<"\"all_trig_domains_recovered\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save rotation report");std::cout<<"PASS ROTATION_ORACLE signs=2 cases_each=20000 bit_exact=true bounded_angle=true\n";
}catch(const std::exception& e){std::cerr<<"ROTATION_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
