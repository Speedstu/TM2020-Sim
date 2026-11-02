#include "tm2020/recovered_polygon.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct Buffer {ConvexVector* data{};std::uint32_t count{},padding{},capacity{},reserved{};};
struct Span {const void* data{};std::uint32_t count{},padding{};};
struct Face {std::array<std::byte,16> opaque{};std::uint32_t normal_index{},orientation{1};Span indices{};};
struct Descriptor {Span vertices,normals,edges,faces,edge_topology;};
struct Arena {void* begin{};void* end{};void* cursor{};void* committed{};std::uint32_t report{};};
int main(int argc,char** argv)try{
    check(argc==3,"Usage: polygon_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,4> ranges{{{0x1cc390,0x1cd044},{0x19ed30,0x19ed94},{0x11d8d0,0x11da60},{0x1521930,0x1521945}}};ArithmeticImage image(argv[1],ranges);
    using Classify=std::uint32_t(*)(const void*,const void*);using Split=void(*)(const void*,const void*,void*,void*);
    const auto classify=reinterpret_cast<Classify>(image.base+0x1cc390);const auto split=reinterpret_cast<Split>(image.base+0x1cc3e0);
    using FaceContacts=void(*)(void*,const Descriptor*,std::uint32_t,const Descriptor*,std::uint32_t,const float*,Buffer*);
    const auto contacts=reinterpret_cast<FaceContacts>(image.base+0x1cca10);
    std::mt19937_64 rng(0x2026102310);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t cases=20000;
    std::array<std::size_t,3> classifications{};std::size_t positive_count{},negative_count{},face_count{};
    for(std::size_t n=0;n<cases;n++){
        ContactPlane plane{};for(float& x:plane.normal)x=u(rng);const float length=std::sqrt((plane.normal[1]*plane.normal[1]+plane.normal[0]*plane.normal[0])+plane.normal[2]*plane.normal[2]);
        for(float& x:plane.normal)x=x/length;plane.constant=u(rng);
        std::vector<ConvexVector> polygon(n%18);for(auto& p:polygon)for(float& x:p)x=u(rng)*2;
        if(n%3==0){plane={{1,0,0},0};for(std::size_t j=0;j<polygon.size();j++)polygon[j][0]=std::array{0.f,1e-4f,-1e-4f,2e-4f,-2e-4f,-0.f}[j%6];}
        if(n%13==0)for(auto& p:polygon)p={u(rng),u(rng),u(rng)};
        const ConvexVector point=n%5==0?ConvexVector{0,0,0}:ConvexVector{u(rng),u(rng),u(rng)};
        const auto e=classify(&point,&plane),a=static_cast<std::uint32_t>(classify_point(point,plane));check(e==a,"Point plane classification differs");++classifications.at(a);
        std::array<ConvexVector,64> positive{},negative{};Buffer input{polygon.data(),std::uint32_t(polygon.size()),0,64,0},pos{positive.data(),0,0,64,0},neg{negative.data(),0,0,64,0};
        split(&input,&plane,&pos,&neg);const auto actual=split_polygon(polygon,plane);
        if(pos.count!=actual.positive.size()||neg.count!=actual.negative.size()){std::cerr<<"Polygon count case="<<n<<" positive="<<pos.count<<'/'<<actual.positive.size()<<" negative="<<neg.count<<'/'<<actual.negative.size()<<'\n';throw std::runtime_error("Polygon counts differ");}
        for(unsigned which=0;which<2;which++){
            const auto& output=which?actual.negative:actual.positive;const auto& expected=which?negative:positive;
            for(std::size_t j=0;j<output.size();j++)if(std::memcmp(&output[j],&expected[j],sizeof(ConvexVector))!=0){
                std::cerr<<"Polygon point mismatch case="<<n<<" side="<<which<<" point="<<j<<'\n';for(std::size_t k=0;k<3;k++)std::cerr<<expected[j][k]<<'/'<<output[j][k]<<' ';std::cerr<<'\n';throw std::runtime_error("Polygon vertices differ from original");
            }
        }
        positive_count+=pos.count;negative_count+=neg.count;
        std::vector<ConvexVector> incident(3+n%7),reference(3+(n*3)%7);
        const float offset=u(rng),sx=1.f+u(rng)*.5f,sy=1.f+u(rng)*.5f;
        for(std::size_t j=0;j<incident.size();j++){const float angle=float(j)*6.283185307179586f/float(incident.size());incident[j]={sx*std::cos(angle),sy*std::sin(angle),offset};}
        for(std::size_t j=0;j<reference.size();j++){const float angle=float(j)*6.283185307179586f/float(reference.size());reference[j]={std::cos(angle),std::sin(angle),0};}
        std::array<float,12> transform{1,0,0,0,1,0,0,0,1,u(rng)*.5f,u(rng)*.5f,u(rng)*.5f};
        if(n%4!=0){
            float w=u(rng),x=u(rng),y=u(rng),z=u(rng);const float inverse=1.f/std::sqrt(w*w+x*x+y*y+z*z);w*=inverse;x*=inverse;y*=inverse;z*=inverse;
            transform={1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y),2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x),2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y),transform[9],transform[10],transform[11]};
        }
        if(n%11==0){transform={1,0,0,0,1,0,0,0,1,0,0,offset};}
        const ConvexVector reference_normal=n%5==0?ConvexVector{0,0,-1}:ConvexVector{0,0,1};
        std::array<std::uint32_t,9> indices{0,1,2,3,4,5,6,7,8};
        Face fa{},fb{};fa.indices={indices.data(),std::uint32_t(incident.size())};fb.indices={indices.data(),std::uint32_t(reference.size())};fb.orientation=n%5==0?0:1;
        const Descriptor da{{incident.data(),std::uint32_t(incident.size())},{&reference_normal,1},{},{&fa,1},{}},db{{reference.data(),std::uint32_t(reference.size())},{&reference_normal,1},{},{&fb,1},{}};
        alignas(16) std::array<std::byte,8192> arena_storage{};Arena arena{arena_storage.data(),arena_storage.data()+arena_storage.size(),arena_storage.data(),arena_storage.data()+arena_storage.size(),0};auto* arena_pointer=&arena;
        Buffer face_output{};contacts(&arena_pointer,&da,0,&db,0,transform.data(),&face_output);
        const auto actual_face=face_contacts(incident,reference,reference_normal,transform,fb.orientation!=0);
        if(actual_face.size()!=face_output.count){std::cerr<<"Face count mismatch case="<<n<<" native="<<face_output.count<<" port="<<actual_face.size()<<'\n';throw std::runtime_error("Face contact counts differ");}
        for(std::size_t j=0;j<actual_face.size();j++)if(std::memcmp(&actual_face[j],&face_output.data[j],sizeof(ConvexVector))!=0){std::cerr<<"Face point mismatch case="<<n<<" point="<<j<<'\n';for(std::size_t k=0;k<3;k++)std::cerr<<face_output.data[j][k]<<'/'<<actual_face[j][k]<<' ';std::cerr<<'\n';throw std::runtime_error("Face contact coordinates differ");}
        face_count+=face_output.count;
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_polygon_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_operation\":20000,\"operations\":3,\"bit_exact\":true,\"original_instructions_native\":true,\"classifications\":["<<classifications[0]<<','<<classifications[1]<<','<<classifications[2]
        <<"],\"positive_vertices\":"<<positive_count<<",\"negative_vertices\":"<<negative_count<<",\"face_contact_vertices\":"<<face_count<<",\"near_parallel_undefined_branch_qualified\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save polygon oracle");std::cout<<"PASS POLYGON_ORACLE cases_each=20000 bit_exact=true deterministic_domain=true complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"POLYGON_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
