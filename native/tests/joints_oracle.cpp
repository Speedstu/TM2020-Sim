#include "tm2020/recovered_joints.hpp"
#include "owned_arithmetic_image.hpp"
#include <cmath>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T>struct Span{T* data;std::uint32_t count;std::uint32_t reserved{};};
template<class T>void same(const T& a,const T& b,std::size_t trial,const char* label){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);std::size_t offset{};while(offset<sizeof(T)&&x[offset]==y[offset])++offset;
    std::cerr<<"MISMATCH trial="<<trial<<" label="<<label<<" byte="<<offset<<" expected="<<unsigned(x[offset])<<" actual="<<unsigned(y[offset])<<'\n';throw std::runtime_error("Joint kernel differs from original");
}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: joints_oracle original.exe output.json");
    const std::array<std::array<unsigned,2>,3> ranges{{{0x7f5090,0x7f5858},{0x7f5f40,0x7f6041},{0x7f67a0,0x7f6a46}}};ArithmeticImage image(argv[1],ranges);
    using Sweep=float(*)(void*,const void*,const void*);using Coupling=void(*)(void*,const void*,const void*);
    const auto point=reinterpret_cast<Sweep>(image.base+0x7f56d0),angular=reinterpret_cast<Sweep>(image.base+0x7f5f40);const auto coupling=reinterpret_cast<Coupling>(image.base+0x7f67a0);
    std::mt19937_64 rng(0x2026102317);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;std::size_t unilateral{},signed_impulses{},fixed{},same_body{},positive{},negative{},coupling_skips{},coupling_updates{};
    const auto vector=[&](float scale=1.f){return std::array{u(rng)*scale,u(rng)*scale,u(rng)*scale};};
    for(std::size_t n=0;n<cases;n++){
        std::array<RigidState,3> initial{};std::array<VelocityCoefficients,3> coefficients{};
        for(std::size_t j=0;j<3;j++){initial[j].position=vector(3);initial[j].linear_velocity=vector(5);initial[j].angular_velocity=vector(2);for(auto& x:coefficients[j])x=.05f+std::abs(u(rng))*.1f;if(n%11==0)initial[j].angular_velocity={0,-0.f,0};}
        std::array<PointConstraint,4> pc{};std::array<AngularConstraint,4> ac{};std::array<AngularCouplingConstraint,4> cc{};
        for(std::size_t j=0;j<4;j++){
            auto& p=pc[j];p.body_a=j%3;p.body_b=n%7==0?fixed_constraint_body:(j+1)%3;if(n%17==0)p.body_b=p.body_a;
            p.world_point_a=vector(3);p.world_point_b=vector(3);p.direction=vector();p.bias=u(rng);p.softness=n%3==0?0:u(rng);p.effective_coefficient=std::abs(u(rng))*.1f;p.accumulated_impulse=u(rng);
            if(n%19==0){p.direction={0,-0.f,0};p.bias=-0.f;p.accumulated_impulse=-0.f;}
            auto& a=ac[j];a={p.body_a,p.body_b,p.direction,p.bias,p.softness,p.effective_coefficient,p.accumulated_impulse};if(n%13==0)a.body_a=fixed_constraint_body;
            auto& c=cc[j];c.body_a=p.body_a;c.body_b=n%17==0?c.body_a:(j+1)%3;c.axis_a=vector();c.axis_b=vector();c.coefficient_weights_a=vector();c.coefficient_weights_b=vector();for(auto* weights:{&c.coefficient_weights_a,&c.coefficient_weights_b})for(auto& x:*weights)x=.1f+std::abs(x);c.ratio=std::abs(u(rng))*3;
            if(n%11==0){c.axis_a={1,0,0};c.axis_b={1,0,0};c.coefficient_weights_a={};c.coefficient_weights_b={};}
            unilateral+=p.softness==0;signed_impulses+=p.softness!=0;fixed+=p.body_b==fixed_constraint_body;same_body+=p.body_b==p.body_a;
        }
        const std::uint32_t count=n%23==0?0:4;Span<PointConstraint> ps{pc.data(),count};Span<AngularConstraint> as{ac.data(),count};Span<AngularCouplingConstraint> cs{cc.data(),count};
        auto native_states=initial,ported_states=initial;auto pp=pc;const float pe=point(native_states.data(),coefficients.data(),&ps),pa=solve_point_constraints(ported_states,coefficients,std::span(pp.data(),count));
        same(native_states,ported_states,n,"point states");same(pc,pp,n,"point impulses");same(pe,pa,n,"point maximum delta");
        native_states=initial;ported_states=initial;auto ap=ac;const float ae=angular(native_states.data(),coefficients.data(),&as),aa=solve_angular_constraints(ported_states,coefficients,std::span(ap.data(),count));
        same(native_states,ported_states,n,"angular states");same(ac,ap,n,"angular impulses");same(ae,aa,n,"angular maximum delta");
        native_states=initial;ported_states=initial;coupling(native_states.data(),coefficients.data(),&cs);solve_angular_couplings(ported_states,coefficients,std::span(cc.data(),count));same(native_states,ported_states,n,"angular coupling states");
        if(std::memcmp(native_states.data(),initial.data(),sizeof(initial))==0)++coupling_skips;else ++coupling_updates;
        for(std::size_t j=0;j<count;j++){positive+=pp[j].accumulated_impulse>0;negative+=pp[j].accumulated_impulse<0;}
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_joint_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":3,\"bit_exact\":true,\"original_instructions_native\":true,\"unilateral_injections\":"<<unilateral<<",\"signed_impulse_injections\":"<<signed_impulses<<",\"fixed_body_injections\":"<<fixed<<",\"same_body_injections\":"<<same_body<<",\"positive_impulses\":"<<positive<<",\"negative_impulses\":"<<negative<<",\"coupling_update_cases\":"<<coupling_updates<<",\"coupling_no_update_cases\":"<<coupling_skips<<",\"game_process_accessed\":false,\"joint_construction_from_assets_qualified\":false,\"complete_physics\":false}\n";
    report.flush();check(bool(report),"Cannot write joint oracle report");std::cout<<"PASS JOINT_ORACLE operations=3 cases_each=20000 bit_exact=true original_full_sweeps=true full_physics=false\n";
}catch(const std::exception& e){std::cerr<<"JOINT_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
