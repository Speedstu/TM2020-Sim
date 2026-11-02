#include "tm2020/recovered_collision.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct NativeContact {
    const void* a{};const void* b{};
    std::array<float,3> penetration{},normal{},point{};
    std::array<std::byte,28> other{};
    std::uint16_t material_a{},material_b{};std::uint32_t flags{};
};
static_assert(sizeof(NativeContact)==88&&offsetof(NativeContact,material_a)==0x50);
struct Instance{const void* surface{};std::array<std::byte,36> other{};std::array<float,3> center{};};
static_assert(offsetof(Instance,center)==0x2c);
struct Arena{NativeContact* data;std::uint32_t count{},reserved{},capacity{1};};
struct Context{std::uint32_t hit{},reserved{};Arena* arena{};std::uint32_t any_hit{};};
template<class T>void same(const T& a,const T& b,std::size_t n,const char* label){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);
    std::size_t at{};while(at<sizeof(T)&&x[at]==y[at])++at;
    std::cerr<<"MISMATCH sphere "<<label<<" case="<<n<<" byte="<<at<<" expected="<<unsigned(x[at])<<" actual="<<unsigned(y[at])<<'\n';
    throw std::runtime_error("Sphere geometry differs from original");
}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: sphere_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,2> ranges{{{0x1a17f0,0x1a1a43},{0x197890,0x1978b2}}};ArithmeticImage image(argv[1],ranges);
    using Fn=void(*)(const void*,const void*,void*);const auto original=reinterpret_cast<Fn>(image.base+0x1a17f0);
    std::mt19937_64 rng(0x2026102305);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;
    std::size_t overlaps{},fallback{},separated{},tangent{};
    for(std::size_t n=0;n<cases;n++){
        Sphere a{},b{};for(float& x:a.center)x=u(rng)*4;for(float& x:b.center)x=u(rng)*4;
        a.radius=std::abs(u(rng))*4;b.radius=std::abs(u(rng))*4;a.surface_id=std::uint16_t(rng());b.surface_id=std::uint16_t(rng());
        if(n%7==0){a.center={};b.center={};}
        if(n%11==0){a.center={};b.center={0,1e-6f,0};}
        if(n%13==0){a.center={};a.radius=1;b.radius=1;b.center={2,0,0};++tangent;}
        if(n%17==0){a.center={};b.center={0,1e-5f,0};}
        if(n%19==0){a.radius=0;b.radius=0;}
        std::array<std::byte,48> sa{},sb{};std::memcpy(sa.data()+0x28,&a.radius,4);std::memcpy(sb.data()+0x28,&b.radius,4);
        std::memcpy(sa.data()+0x20,&a.surface_id,2);std::memcpy(sb.data()+0x20,&b.surface_id,2);
        const Instance ia{sa.data(),{},a.center},ib{sb.data(),{},b.center};
        NativeContact native{};native.flags=std::uint32_t(rng());SphereContact ported{};ported.flags=native.flags;
        for(float& x:ported.normal)x=u(rng);for(float& x:ported.penetration_vector)x=u(rng);for(float& x:ported.surface_point_a)x=u(rng);
        native.normal=ported.normal;native.penetration=ported.penetration_vector;native.point=ported.surface_point_a;
        native.material_a=ported.surface_id_a=std::uint16_t(rng());native.material_b=ported.surface_id_b=std::uint16_t(rng());
        Arena arena{&native};Context context{0,0,&arena,0};original(&ia,&ib,&context);
        const bool actual=collide_spheres(a,b,ported),expected=context.hit!=0;same(expected,actual,n,"overlap");
        check(arena.count==unsigned(expected),"Original sphere contact count wrong");
        same(native.normal,ported.normal,n,"normal");same(native.penetration,ported.penetration_vector,n,"penetration");same(native.point,ported.surface_point_a,n,"surface point");
        same(native.material_a,ported.surface_id_a,n,"material A");same(native.material_b,ported.surface_id_b,n,"material B");same(native.flags,ported.flags,n,"flags");
        if(expected){++overlaps;const float dx=b.center[0]-a.center[0],dy=b.center[1]-a.center[1],dz=b.center[2]-a.center[2];if(std::sqrt((dy*dy+dx*dx)+dz*dz)<=1e-5f)++fallback;
            check(native.a==&ia&&native.b==&ib,"Original contact ownership wrong");}
        else ++separated;
        Context query{};original(&ia,&ib,&query);check((query.hit!=0)==actual&&query.any_hit==unsigned(actual),"Native boolean-only query changed overlap semantics");
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_sphere_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases\":20000,\"bit_exact\":true,\"original_instructions_native\":true,\"overlaps\":"<<overlaps<<",\"coincident_fallbacks\":"<<fallback
        <<",\"separated\":"<<separated<<",\"tangency_inputs\":"<<tangent<<",\"game_process_accessed\":false,\"stadium_chassis_geometry_recovered\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save sphere oracle");std::cout<<"PASS SPHERE_ORACLE cases=20000 bit_exact=true original_boolean_query=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"SPHERE_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
