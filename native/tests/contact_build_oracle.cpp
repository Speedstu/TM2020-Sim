#include "tm2020/recovered_jacobian.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T>struct Buffer{T* data;std::uint32_t count;std::uint32_t capacity;};
template<class T>void same(const T& a,const T& b,std::size_t n,const char* label){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);
    std::size_t off{};while(off<sizeof(T)&&x[off]==y[off])++off;
    std::cerr<<"MISMATCH "<<label<<" case="<<n<<" byte="<<off<<" expected="<<unsigned(x[off])<<" actual="<<unsigned(y[off])<<'\n';
    if(off+sizeof(float)<=sizeof(T)){float f{},g{};std::memcpy(&f,x+(off&~3),4);std::memcpy(&g,y+(off&~3),4);std::cerr<<f<<" / "<<g<<'\n';}
    throw std::runtime_error("Contact preparation differs from original");
}
template<class T>void put(std::array<std::byte,0x80>& group,std::size_t offset,T value){std::memcpy(group.data()+offset,&value,sizeof(value));}
template<class T>Buffer<T> get(const std::array<std::byte,0x80>& group,std::size_t offset){Buffer<T> out{};std::memcpy(&out,group.data()+offset,sizeof(out));return out;}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: contact_build_oracle original.exe report.json");
    // Allocation paths are never entered: valid caller-owned capacity covers
    // all native appends. No original instructions or calls are patched.
    const std::array<std::array<unsigned,2>,9> ranges{{{0x85ecd0,0x85fc49},{0x67c1e0,0x67c2f4},
        {0x117e90,0x117ecd},{0x1f6d70,0x1f6da9},{0x1f4910,0x1f494c},
        {0x8053e0,0x805419},{0x4d8c60,0x4d8c99},{0x25ef00,0x25ef3d},{0x1886d0,0x1888ef}}};
    ArithmeticImage image(argv[1],ranges);
    using Build=void(*)(void*,float,const ContactPoint*,const RigidState*,const VelocityCoefficients*,float);
    const auto dynamic=reinterpret_cast<Build>(image.base+0x85eea0),fixed=reinterpret_cast<Build>(image.base+0x85f5b0);
    std::mt19937_64 rng(0x2026102302);std::uniform_real_distribution<float> u(-1,1);
    const auto vec=[&](float scale=1.f){return std::array{u(rng)*scale,u(rng)*scale,u(rng)*scale};};
    constexpr std::size_t cases=20000;std::size_t with_friction{},restitution_negative{},target_positive{},target_zero{},negative_input_restitution{};
    for(std::size_t n=0;n<cases;n++){
        std::array<RigidState,3> states{};std::array<VelocityCoefficients,3> coeff{};
        for(std::size_t k=0;k<3;k++){
            auto& s=states[k];s.position=vec(10);s.linear_velocity=vec(5);s.angular_velocity=vec(2);
            auto axis=vec();const float norm=std::sqrt(axis[0]*axis[0]+axis[1]*axis[1]+axis[2]*axis[2]);
            const float angle=u(rng)*3;const float sine=std::sin(angle*.5f);
            s.quaternion={std::cos(angle*.5f),axis[0]/norm*sine,axis[1]/norm*sine,axis[2]/norm*sine};
            quaternion_to_matrix(s.rotation,s.quaternion);
            coeff[k]={.01f+std::abs(u(rng)),.01f+std::abs(u(rng)),.01f+std::abs(u(rng)),.1f+std::abs(u(rng))};
        }
        ContactPoint c{};c.body_a=n%3;c.body_b=n%17==0?c.body_a:(n+1)%3;c.world_point=vec(10);c.normal=vec();
        if(n%13==0)c.normal={0,1,-0.f};if(n%11==0)c.normal={1,0,0};if(n%7==0)c.normal={0,0,1};
        c.separation=u(rng)*.2f;c.friction=n%3==0?0:std::abs(u(rng));c.restitution=n%5==0?0:u(rng);negative_input_restitution+=c.restitution<0;
        const float dt=.001f+std::abs(u(rng))*.04f,threshold=n%19==0?0:std::abs(u(rng))*2;
        const std::uint32_t normal_index=n%3;
        std::array<DynamicPositionConstraint,4> dpos{};std::array<DynamicJacobianConstraint,6> dnormal{};std::array<DynamicFrictionConstraint,4> dfriction{};
        std::array<std::byte,0x80> dg{};
        put(dg,0x40,Buffer{dnormal.data(),normal_index,6u});put(dg,0x50,Buffer{dfriction.data(),0u,4u});put(dg,0x60,Buffer{dpos.data(),0u,4u});
        const auto original_states=states;const auto original_coeff=coeff;const auto original_contact=c;
        dynamic(dg.data(),dt,&c,states.data(),coeff.data(),threshold);
        const auto d=prepare_dynamic_contact(c,states,coeff,dt,threshold,normal_index);
        same(dpos[0],d.position,n,"dynamic position");same(dnormal[normal_index],d.normal,n,"dynamic normal");
        check(get<DynamicPositionConstraint>(dg,0x60).count==1&&get<DynamicJacobianConstraint>(dg,0x40).count==normal_index+1,"Native dynamic counts wrong");
        check(get<DynamicFrictionConstraint>(dg,0x50).count==d.friction_count,"Dynamic friction count differs");
        for(std::size_t k=0;k<d.friction_count;k++)same(dfriction[k],d.friction[k],n,"dynamic friction");
        std::array<StaticPositionConstraint,4> spos{};std::array<StaticJacobianConstraint,6> snormal{};std::array<StaticFrictionConstraint,4> sfriction{};
        std::array<std::byte,0x80> sg{};
        put(sg,0x40,Buffer{sfriction.data(),0u,4u});put(sg,0x50,Buffer{snormal.data(),normal_index,6u});put(sg,0x60,Buffer{spos.data(),0u,4u});
        fixed(sg.data(),dt,&c,states.data(),coeff.data(),threshold);
        const auto s=prepare_static_contact(c,states,coeff,dt,threshold,normal_index);
        same(spos[0],s.position,n,"static position");same(snormal[normal_index],s.normal,n,"static normal");
        check(get<StaticPositionConstraint>(sg,0x60).count==1&&get<StaticJacobianConstraint>(sg,0x50).count==normal_index+1,"Native static counts wrong");
        check(get<StaticFrictionConstraint>(sg,0x40).count==s.friction_count,"Static friction count differs");
        for(std::size_t k=0;k<s.friction_count;k++)same(sfriction[k],s.friction[k],n,"static friction");
        same(states,original_states,n,"input states unchanged");same(coeff,original_coeff,n,"input coefficients unchanged");same(c,original_contact,n,"input contact unchanged");
        if(s.friction_count)++with_friction;
        for(float target:{d.normal.jacobian.target,s.normal.target}){if(target<0)++restitution_negative;else if(target>0)++target_positive;else ++target_zero;}
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_contact_build_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_builder\":20000,\"builders\":2,\"bit_exact\":true,\"original_instructions_native\":true,\"original_code_modified\":false,"
        <<"\"sufficient_container_capacity\":true,\"allocation_path_qualified\":false,\"with_friction\":"<<with_friction
        <<",\"negative_restitution_inputs\":"<<negative_input_restitution<<",\"negative_restitution_targets\":"<<restitution_negative<<",\"positive_targets\":"<<target_positive<<",\"zero_targets\":"<<target_zero
        <<",\"game_process_accessed\":false,\"geometry_contact_generation_recovered\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save contact builder oracle");
    std::cout<<"PASS CONTACT_BUILD_ORACLE static_dynamic cases_each=20000 bit_exact=true geometry_contact_generation=false\n";
}catch(const std::exception& e){std::cerr<<"CONTACT_BUILD_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
