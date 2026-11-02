#include "tm2020/recovered_contacts.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T>void same(const T& a,const T& b,std::size_t trial,const char* label){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);
    std::size_t offset{};while(offset<sizeof(T)&&x[offset]==y[offset])++offset;
    std::cerr<<"MISMATCH trial="<<trial<<" label="<<label<<" offset="<<offset<<" expected="<<unsigned(x[offset])<<" actual="<<unsigned(y[offset])<<'\n';
    throw std::runtime_error("Contact kernel differs from original");
}
template<class T>struct Span {T* data;std::uint32_t count;std::uint32_t reserved{};};
int main(int argc,char** argv)try{
    check(argc==3,"Usage: contact_oracle original.exe output.json");
    const std::array<std::array<unsigned,2>,2> ranges{{{0x7f5860,0x7f5caa},{0x7f5cb0,0x7f5f33}}};ArithmeticImage image(argv[1],ranges);
    using DynamicFn=float(*)(const void*,void*,const void*);using StaticFn=float(*)(void*,const void*,const void*);
    const auto dynamic=reinterpret_cast<DynamicFn>(image.base+0x7f5860);const auto fixed=reinterpret_cast<StaticFn>(image.base+0x7f5cb0);
    std::mt19937_64 rng(0x20261022);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;
    for(std::size_t n=0;n<cases;n++){
        std::array<RigidState,3> initial;
        std::array<VelocityCoefficients,3> coefficients;
        for(std::size_t j=0;j<3;j++){
            for(auto& x:initial[j].position)x=u(rng)*3;
            for(auto& x:initial[j].linear_velocity)x=u(rng)*10;
            for(auto& x:initial[j].angular_velocity)x=u(rng)*3;
            for(auto& x:coefficients[j])x=std::abs(u(rng))*.1f;
            if(n%13==0)initial[j].linear_velocity={0,-0.f,0};
        }
        std::array<DynamicNormalConstraint,4> nd;std::array<StaticNormalConstraint,4> ns;
        for(std::size_t j=0;j<4;j++){
            auto& d=nd[j];auto& s=ns[j];d.body_a=j%3;d.body_b=(j+1)%3;s.body=j%3;
            if(n%19==0)d.body_b=d.body_a;
            for(std::size_t k=0;k<3;k++){d.world_point[k]=u(rng)*4;d.normal[k]=u(rng);}
            if(n%17==0)d.normal={0,-0.f,0};
            d.bias=u(rng)*5;d.effective_coefficient=std::abs(u(rng))*.1f;d.accumulated_impulse=std::abs(u(rng))*10;
            s.world_point=d.world_point;s.normal=d.normal;s.bias=d.bias;s.effective_coefficient=d.effective_coefficient;s.accumulated_impulse=d.accumulated_impulse;
        }
        auto pd=nd;auto ps=ns;auto native_states=initial,ported_states=initial;
        const std::uint32_t count=n%23==0?0:4;
        Span<DynamicNormalConstraint> sd{nd.data(),count};Span<StaticNormalConstraint> ss{ns.data(),count};
        const float expected=dynamic(coefficients.data(),native_states.data(),&sd);
        const float actual=solve_dynamic_normals(ported_states,coefficients,std::span(pd.data(),count));
        same(native_states,ported_states,n,"dynamic states");same(nd,pd,n,"dynamic accumulated impulses");same(expected,actual,n,"dynamic maximum delta");
        native_states=initial;ported_states=initial;
        const float expected_static=fixed(native_states.data(),coefficients.data(),&ss);
        const float actual_static=solve_static_normals(ported_states,coefficients,std::span(ps.data(),count));
        same(native_states,ported_states,n,"static states");same(ns,ps,n,"static accumulated impulses");same(expected_static,actual_static,n,"static maximum delta");
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_contact_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_solver\":20000,\"solvers\":2,\"constraints_per_batch\":4,\"bit_exact\":true,\"original_instructions_native\":true,"
        <<"\"game_process_accessed\":false,\"contact_generation_recovered\":false,\"complete_physics\":false}\n";
    report.flush();check(bool(report),"Cannot write contact oracle report");
    std::cout<<"PASS CONTACT_ORACLE dynamic_and_static cases_each=20000 bit_exact=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"CONTACT_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
