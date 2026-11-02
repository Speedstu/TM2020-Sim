#include "tm2020/recovered_jacobian.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T>void same(const T& a,const T& b,std::size_t trial,const char* label){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);
    std::size_t off{};while(off<sizeof(T)&&x[off]==y[off])++off;
    std::cerr<<"MISMATCH "<<label<<" trial="<<trial<<" byte="<<off<<" expected="<<unsigned(x[off])<<" actual="<<unsigned(y[off])<<'\n';
    throw std::runtime_error("Jacobian differs from original instructions");
}
template<class T>struct Span{T* data;std::uint32_t count;std::uint32_t reserved{};};
int main(int argc,char** argv)try{
    check(argc==3,"Usage: jacobian_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,6> ranges{{{0x85ecd0,0x85ee9f},{0x85fc50,0x85fefc},
        {0x85ffd0,0x86019d},{0x8601a0,0x8603aa},{0x85ff00,0x85ffc7},{0x85eab0,0x85ecc1}}};
    ArithmeticImage image(argv[1],ranges);
    using Prepare=void(*)(DynamicJacobian*,void*,void*,const VelocityCoefficients*,const void*,void*,const VelocityCoefficients*,const void*,const void*,float);
    using Sweep=int(*)(void*,const void*);using Friction=int(*)(void*,const void*,const void*);
    const auto prep=reinterpret_cast<Prepare>(image.base+0x85ecd0);
    const auto dyn=reinterpret_cast<Sweep>(image.base+0x85fc50),stat=reinterpret_cast<Sweep>(image.base+0x85ffd0);
    const auto df=reinterpret_cast<Friction>(image.base+0x85ff00),sf=reinterpret_cast<Friction>(image.base+0x8601a0);
    std::mt19937_64 rng(0x2026102301);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;
    std::size_t positive{},negative{},zero{};
    for(std::size_t n=0;n<cases;n++){
        const auto v=[&](float scale=1.f){return std::array{u(rng)*scale,u(rng)*scale,u(rng)*scale};};
        const VelocityCoefficients ca{std::abs(u(rng))*.1f,std::abs(u(rng))*.1f,std::abs(u(rng))*.1f,.2f+std::abs(u(rng))};
        const VelocityCoefficients cb{std::abs(u(rng))*.1f,std::abs(u(rng))*.1f,std::abs(u(rng))*.1f,.2f+std::abs(u(rng))};
        auto ra=v(3),rb=v(3),direction=v();if(n%7==0)direction={0,-0.f,0};
        DynamicJacobian expected{};expected.accumulated_impulse=u(rng);auto actual=expected;const float target=u(rng)*4;
        prep(&expected,nullptr,nullptr,&ca,&ra,nullptr,&cb,&rb,&direction,target);
        prepare_dynamic_jacobian(actual,ca,cb,ra,rb,direction,target);same(expected,actual,n,"initializer");
        std::array<RigidState,3> initial{};
        for(auto& s:initial){s.linear_velocity=v(5);s.angular_velocity=v(3);if(n%11==0){s.linear_velocity={0,-0.f,0};s.angular_velocity={-0.f,0,0};}}
        std::array<DynamicJacobianConstraint,4> dc{};std::array<StaticJacobianConstraint,4> sc{};
        std::array<DynamicFrictionConstraint,4> dfr{};std::array<StaticFrictionConstraint,4> sfr{};
        for(std::size_t j=0;j<4;j++){
            auto& d=dc[j];d.body_a=j%3;d.body_b=n%19==0?d.body_a:(j+1)%3;d.direction=v();d.jacobian=actual;
            d.jacobian.target=u(rng)*3;d.jacobian.accumulated_impulse=std::abs(u(rng))*2;
            if(n%13==0){d.direction={0,-0.f,0};d.jacobian={};d.jacobian.accumulated_impulse=-0.f;}
            auto& s=sc[j];s.body=j%3;s.direction=d.direction;s.angular=d.jacobian.angular_a;s.weighted_angular=d.jacobian.weighted_angular_a;
            s.inverse_mass=ca[3];s.effective_coefficient=actual.effective_coefficient;s.target=d.jacobian.target;s.accumulated_impulse=d.jacobian.accumulated_impulse;
            dfr[j]={d,std::uint32_t((j+1)%4),std::abs(u(rng))};sfr[j]={s,dfr[j].normal_index,dfr[j].friction};
            if(n%5==0){dc[j].jacobian.accumulated_impulse=0;sc[j].accumulated_impulse=0;}
        }
        const std::uint32_t count=n%23==0?0:4;
        auto ds=initial,ps=initial;auto dp=dc;Span<DynamicJacobianConstraint> dspan{dc.data(),count};
        const bool de=dyn(ds.data(),&dspan)!=0;const bool da=solve_dynamic_unilateral(ps,std::span(dp.data(),count));
        same(ds,ps,n,"dynamic states");same(dc,dp,n,"dynamic impulses");same(de,da,n,"dynamic result");
        ds=initial;ps=initial;auto sp=sc;Span<StaticJacobianConstraint> sspan{sc.data(),count};
        const bool se=stat(ds.data(),&sspan)!=0;const bool sa=solve_static_unilateral(ps,std::span(sp.data(),count));
        same(ds,ps,n,"static states");same(sc,sp,n,"static impulses");same(se,sa,n,"static result");
        ds=initial;ps=initial;auto dfp=dfr;Span<DynamicFrictionConstraint> dfspan{dfr.data(),count};
        const bool dfe=df(ds.data(),&dfspan,&dspan)!=0;const bool dfa=solve_dynamic_friction(ps,std::span(dfp.data(),count),dc);
        same(ds,ps,n,"dynamic friction states");same(dfr,dfp,n,"dynamic friction impulses");same(dfe,dfa,n,"dynamic friction result");
        ds=initial;ps=initial;auto sfp=sfr;Span<StaticFrictionConstraint> sfspan{sfr.data(),count};
        const bool sfe=sf(ds.data(),&sfspan,&sspan)!=0;const bool sfa=solve_static_friction(ps,std::span(sfp.data(),count),sc);
        same(ds,ps,n,"static friction states");same(sfr,sfp,n,"static friction impulses");same(sfe,sfa,n,"static friction result");
        for(std::size_t j=0;j<count;j++){const auto x=sfr[j].constraint.accumulated_impulse;if(x>0)++positive;else if(x<0)++negative;else ++zero;}
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_jacobian_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_operation\":20000,\"complete_procedures\":6,\"public_operations\":5,\"bit_exact\":true,\"positive_friction\":"<<positive
        <<",\"negative_friction\":"<<negative<<",\"zero_friction\":"<<zero<<",\"original_instructions_native\":true,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    report.flush();check(bool(report),"Cannot save oracle report");
    std::cout<<"PASS JACOBIAN_ORACLE operations=5 cases_each=20000 bit_exact=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"JACOBIAN_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
