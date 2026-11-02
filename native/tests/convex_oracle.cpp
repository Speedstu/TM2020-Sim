#include "tm2020/recovered_convex.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct Span {const ConvexVector* data{};std::uint32_t count{},padding{};};
struct Descriptor {Span vertices,normals,edges;};
struct NativeResult {float depth{};ConvexVector normal{};std::uint32_t feature{};};
template<class T>void same(const T& a,const T& b,std::size_t n,const char* field){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    const auto* x=reinterpret_cast<const unsigned char*>(&a);const auto* y=reinterpret_cast<const unsigned char*>(&b);std::size_t at{};while(at<sizeof(T)&&x[at]==y[at])++at;
    std::cerr<<"MISMATCH SAT case="<<n<<" field="<<field<<" byte="<<at<<" expected="<<unsigned(x[at])<<" actual="<<unsigned(y[at])<<'\n';throw std::runtime_error("Convex kernel differs from original");
}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: convex_oracle original.exe report.json");const std::array<std::array<unsigned,2>,1> ranges{{{0x1cab20,0x1cb1bc}}};ArithmeticImage image(argv[1],ranges);
    using Project=void(*)(const Span*,const ConvexVector*,float*,float*);using Sat=int(*)(const Descriptor*,const Descriptor*,float,NativeResult*);
    const auto project=reinterpret_cast<Project>(image.base+0x1cab20);const auto sat=reinterpret_cast<Sat>(image.base+0x1cae40);
    std::mt19937_64 rng(0x2026102309);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t count=20000;std::size_t overlaps{},separations{};std::array<std::size_t,3> witnesses{};
    for(std::size_t n=0;n<count;n++){
        std::vector<ConvexVector> va(1+n%17),vb(1+(n*3)%17);std::array<ConvexVector,6> na{},nb{},ea{},eb{};
        for(auto* v:{&va,&vb})for(auto& p:*v)for(float& x:p)x=u(rng)*4;
        for(auto* normals:{&na,&nb,&ea,&eb})for(auto& p:*normals){
            for(float& x:p)x=u(rng);const float length=std::sqrt((p[1]*p[1]+p[0]*p[0])+p[2]*p[2]);for(float& x:p)x=x/length;
        }
        if(n%11==0)for(auto* v:{&va,&vb})for(auto& p:*v)p={0,-0.f,0};
        if(n%13==0){ea[0]={1,0,0};eb[0]={1,1e-6f,0};}
        if(n%17==0){ea[0]={1,0,0};eb[0]={1,1e-4f,0};}
        const std::uint32_t fa=n%7==0?0:std::uint32_t(n%6+1),fb=n%9==0?0:std::uint32_t((n+2)%6+1),edge_count=n%5==0?0:6;
        const Span sa{va.data(),std::uint32_t(va.size())},sb{vb.data(),std::uint32_t(vb.size())};
        const Descriptor a{sa,{na.data(),fa},{ea.data(),edge_count}},b{sb,{nb.data(),fb},{eb.data(),edge_count}};
        const auto axis=na[0];ProjectionInterval expected{};project(&sa,&axis,&expected.minimum,&expected.maximum);const auto actual=project_vertices(va,axis);same(expected,actual,n,"projection");
        NativeResult native{};const float margin=n%3==0?0:std::abs(u(rng))*.2f;const bool expected_overlap=sat(&a,&b,margin,&native)!=0;
        const ConvexAxesView av{va,std::span(na.data(),fa),std::span(ea.data(),edge_count)},bv{vb,std::span(nb.data(),fb),std::span(eb.data(),edge_count)};
        const auto ported=separating_axes(av,bv,margin);same(expected_overlap,ported.overlap,n,"overlap");same(native.depth,ported.depth,n,"depth");same(native.normal,ported.normal,n,"normal");
        const bool witness=native.depth!=std::numeric_limits<float>::max();same(witness,ported.has_witness,n,"witness exists");
        if(witness){
            const auto kind=std::uint8_t(native.feature),ia=std::uint8_t(native.feature>>8),ib=std::uint8_t(native.feature>>16);
            same(kind,ported.kind,n,"feature kind");same(ia,ported.index_a,n,"feature index A");if(kind==2)same(ib,ported.index_b,n,"feature index B");++witnesses.at(kind);
        }
        if(ported.overlap)++overlaps;else ++separations;
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_convex_sat_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_operation\":20000,\"operations\":2,\"bit_exact_defined_outputs\":true,\"original_instructions_native\":true,\"overlap_cases\":"<<overlaps<<",\"separated_cases\":"<<separations
        <<",\"witnesses\":["<<witnesses[0]<<','<<witnesses[1]<<','<<witnesses[2]<<"],\"unused_native_feature_bytes_compared\":false,\"convex_contact_manifold_ported\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save convex oracle");std::cout<<"PASS CONVEX_SAT_ORACLE cases_each=20000 defined_outputs_bit_exact=true overlaps="<<overlaps<<" separated="<<separations<<" complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"CONVEX_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
