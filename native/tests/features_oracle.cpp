#include "tm2020/recovered_features.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
struct Span {const void* data{};std::uint32_t count{},padding{};};
struct NativeFace {std::array<std::byte,16> opaque{};std::uint32_t normal{},orientation{1};Span vertices;};
struct Descriptor {Span vertices,normals,directions,faces,edges;};
static_assert(sizeof(NativeFace)==40&&sizeof(Descriptor)==80);
template<class T>void same(const T& a,const T& b,std::size_t n,const char* field){
    if(std::memcmp(&a,&b,sizeof(T))==0)return;
    std::cerr<<"Feature mismatch case="<<n<<" field="<<field<<'\n';throw std::runtime_error("Convex feature differs from original");
}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: features_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,2> ranges{{{0x1cb980,0x1cc390},{0x1c9080,0x1c97bc}}};ArithmeticImage image(argv[1],ranges);
    using Select=std::uint32_t(*)(const Descriptor*,std::uint32_t,const ConvexVector*);
    using Incident=std::uint32_t(*)(const Descriptor*,const ConvexVector*);
    using Frame=void(*)(const Descriptor*,std::uint32_t,ConvexVector*,ConvexVector*,float*);
    using Pair=float(*)(const float*,const float*,float,const float*,const float*,float,float*,float*);
    const auto native_edge=reinterpret_cast<Select>(image.base+0x1cb980),native_face=reinterpret_cast<Select>(image.base+0x1cbcb0);
    const auto native_incident=reinterpret_cast<Incident>(image.base+0x1cbef0);const auto native_frame=reinterpret_cast<Frame>(image.base+0x1cc200);const auto native_pair=reinterpret_cast<Pair>(image.base+0x1c9080);
    std::mt19937_64 rng(0x2026102313);std::uniform_real_distribution<float> u(-1,1);std::size_t missing_edges{},missing_faces{},zero_frames{},parallel{};
    for(std::size_t n=0;n<20000;n++){
        std::array<ConvexVector,17> vertices{};std::array<ConvexVector,4> normals{},directions{};ConvexVector axis{};
        for(auto& v:vertices)for(float& x:v)x=u(rng)*5;
        for(auto* a:{&normals,&directions})for(auto& v:*a)for(float& x:v)x=u(rng);
        for(float& x:axis)x=u(rng);
        if(n%11==0)for(auto& v:vertices)v={0,-0.f,0};
        if(n%13==0){axis={0,-0.f,0};for(auto& v:normals)v={1,0,0};}
        std::vector<ConvexEdge> edges(1+n%17);for(auto& e:edges)e={std::uint32_t(rng()%17),std::uint32_t(rng()%17),std::uint32_t(rng()%4)};
        std::vector<ConvexFace> faces(n%18);std::vector<NativeFace> native_faces(faces.size());
        for(std::size_t j=0;j<faces.size();j++){faces[j]={std::uint32_t(rng()%4),rng()%2==0,{}};native_faces[j].normal=faces[j].normal_index;native_faces[j].orientation=faces[j].keep_normal?1:0;}
        const Descriptor descriptor{{vertices.data(),17},{normals.data(),4},{directions.data(),4},{native_faces.data(),std::uint32_t(faces.size())},{edges.data(),std::uint32_t(edges.size())}};
        const ConvexTopologyView shape{{vertices,normals,directions},faces,edges};const auto group=std::uint32_t(n%5);
        const auto e=native_edge(&descriptor,group,&axis),a=select_edge(shape,group,axis);same(e,a,n,"edge selection");if(a==no_convex_feature)++missing_edges;
        const auto f=native_face(&descriptor,group%4,&axis),g=select_face_from_normal(shape,group%4,axis);same(f,g,n,"face normal selection");if(g==no_convex_feature)++missing_faces;
        same(native_incident(&descriptor,&axis),select_incident_face(shape,axis),n,"incident face selection");
        EdgeFrame expected{};const auto index=std::uint32_t(n%edges.size());native_frame(&descriptor,index,&expected.center,&expected.direction,&expected.half_length);const auto actual=edge_frame(shape,index);same(expected,actual,n,"edge frame");if(actual.half_length==0)++zero_frames;
        EdgeFrame first{},second{};for(auto* v:{&first.center,&second.center,&first.direction,&second.direction})for(float& x:*v)x=u(rng)*5;
        for(auto* v:{&first.direction,&second.direction}){const float length=std::sqrt(((*v)[0]*(*v)[0]+(*v)[1]*(*v)[1])+(*v)[2]*(*v)[2]);for(float& x:*v)x=x/length;}
        if(n%5==0){second.direction=first.direction;++parallel;}
        if(n%7==0){for(std::size_t k=0;k<3;k++)second.direction[k]=-first.direction[k];++parallel;}
        if(n%11==0){first.direction={1,0,0};second.direction={1,1e-3f,0};}
        if(n%13==0){first.direction={1,0,0};second.direction={1,1e-2f,0};}
        if(n%17==0)first.center=second.center;
        first.half_length=.01f+std::abs(u(rng))*4;second.half_length=n%19==0?0.f:std::abs(u(rng))*4;
        EdgePairResult expected_pair{};expected_pair.squared_distance=native_pair(first.center.data(),first.direction.data(),first.half_length,second.center.data(),second.direction.data(),second.half_length,&expected_pair.parameter_a,&expected_pair.parameter_b);
        const auto pair=closest_edges(first,second);same(expected_pair,pair,n,"edge pair closest parameters/distance");
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_convex_features_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_operation\":20000,\"operations\":5,\"bit_exact\":true,\"original_instructions_native\":true,\"missing_edge_features\":"<<missing_edges<<",\"missing_face_features\":"<<missing_faces
        <<",\"degenerate_edge_frames\":"<<zero_frames<<",\"parallel_injections\":"<<parallel<<",\"both_zero_half_lengths_qualified\":false,\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save convex features oracle");std::cout<<"PASS CONVEX_FEATURES_ORACLE operations=5 cases_each=20000 bit_exact=true full_manifolds=false\n";
}catch(const std::exception& e){std::cerr<<"CONVEX_FEATURES_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
