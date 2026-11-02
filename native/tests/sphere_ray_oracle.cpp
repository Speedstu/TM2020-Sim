#include "tm2020/recovered_raycast.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
using V=std::array<float,3>;
struct Object {std::array<std::byte,32> header{};std::uint16_t material{},pad{};float reserved{},radius{};};
struct Instance {const Object* object{};std::array<std::byte,36> rotation{};V center{};};
struct Ray {V origin,direction;};
struct Record {float fraction{};V point{},normal{};std::uint16_t material{},pad{};const void* instance{};std::uint64_t triangle{};};
struct Context {std::uint32_t single{1},pad{};Record* record{};std::uint32_t any{};};
static_assert(offsetof(Object,radius)==0x28&&offsetof(Instance,center)==0x2c&&sizeof(Record)==48);
void word(std::ostream& o,std::uint32_t v){o.write(reinterpret_cast<const char*>(&v),4);}
void scalar(std::ostream& o,float v){word(o,std::bit_cast<std::uint32_t>(v));}
void vec(std::ostream& o,const V& v){for(auto x:v)scalar(o,x);}
void hit(std::ostream& o,const RaySphereHit& h){scalar(o,h.fraction);vec(o,h.point);vec(o,h.normal);word(o,h.material);}
bool same(float a,float b){return std::bit_cast<std::uint32_t>(a)==std::bit_cast<std::uint32_t>(b);}
int main(int argc,char** argv)try{
    check(argc==3,"sphere_ray_oracle original.exe new_output_folder");
    const std::filesystem::path folder(argv[2]);check(!std::filesystem::exists(folder),"Never overwrite evidence");std::filesystem::create_directories(folder);
    const std::array<std::array<unsigned,2>,3> ranges{{{0x1a5580,0x1a58d8},{0x18f410,0x18f55d},{0x19a5a0,0x19a5d6}}};
    ArithmeticImage image(argv[1],ranges);using Fn=void(*)(const void*,const Ray*,const Instance*,const V*,Context*);
    const auto original=reinterpret_cast<Fn>(image.base+0x1a5580);
    std::ofstream data(folder/"ray-sphere.cases",std::ios::binary);data.write("TMRSP001",8);word(data,20000);
    std::mt19937_64 rng(0x2026102904);std::uniform_real_distribution<float> u(-1,1);
    unsigned hits=0,inside=0,moving=0;
    for(unsigned i=0;i<20000;i++){
        auto random=[&](float scale){return V{u(rng)*scale,u(rng)*scale,u(rng)*scale};};
        Object object{};object.material=std::uint16_t(rng());object.radius=std::abs(u(rng))*5.f;
        Instance instance{&object,{},random(10)};Ray ray{random(20),random(30)};V displacement=random(3);
        if(i%3==0)for(unsigned k=0;k<3;k++)ray.direction[k]=(instance.center[k]-ray.origin[k])*1.5f;
        if(i%7==0)ray.origin=instance.center;
        if(i%11==0)ray.direction={};
        if(i%13==0)displacement=ray.direction;
        if(i%17==0){instance.center={};object.radius=1;ray={{-2,1,0},{4,0,0}};displacement={};}
        if(i%19==0){instance.center={};object.radius=1;ray={{1,0,0},{1,0,0}};displacement={};}
        if(i%23==0)object.radius=0;
        if(i%29==0){instance.center={};object.radius=1;ray={{1.000001f,0,0},{-.000001f,0,0}};displacement={};}
        const auto skip=std::uint8_t(i%5==0?object.material:255);
        RaySphereHit expected{std::array<float,4>{0.f,.5f,1.f,1.00001f}[i%4],random(5),random(5),std::uint16_t(rng())};auto actual=expected;
        Record record{expected.fraction,expected.point,expected.normal,expected.material,0,nullptr,0xdeadbeef};Context context{1,0,&record,0};
        vec(data,instance.center);scalar(data,object.radius);word(data,object.material);vec(data,ray.origin);vec(data,ray.direction);vec(data,displacement);word(data,skip);hit(data,expected);
        original(&skip,&ray,&instance,&displacement,&context);
        const bool native=context.any!=0,ported=raycast_sphere(instance.center,object.radius,object.material,ray.origin,ray.direction,displacement,skip,actual);
        expected={record.fraction,record.point,record.normal,record.material};
        bool exact=native==ported&&same(expected.fraction,actual.fraction)&&expected.material==actual.material;
        for(unsigned k=0;k<3;k++)exact=exact&&same(expected.point[k],actual.point[k])&&same(expected.normal[k],actual.normal[k]);
        if(!exact){std::cerr<<"MISMATCH sphere ray case="<<i<<" native="<<native<<" port="<<ported<<" fraction="<<record.fraction<<'/'<<actual.fraction<<'\n';throw std::runtime_error("Original sphere ray differs");}
        if(native){check(record.instance==&instance&&record.triangle==0,"Native sphere hit metadata");hits++;if(expected.fraction==0)inside++;if(displacement!=V{})moving++;}
        word(data,native);hit(data,expected);
    }
    data.flush();check(bool(data),"Cannot save numeric sphere ray cases");
    std::ofstream report(folder/"report.json");report<<"{\"schema\":\"tm2020_original_sphere_ray_v1\",\"exeSha256\":\""<<executable_sha256
        <<"\",\"cases\":20000,\"hits\":"<<hits<<",\"insideOrSurfaceHits\":"<<inside<<",\"movingSphereHits\":"<<moving
        <<",\"definedOutputBitsExact\":true,\"originalInstructionsExecuted\":true,\"nativeHitMetadataChecked\":true,\"gameProcessAccessed\":false,\"completeExactSimulatorQualified\":false}\n";
    check(bool(report),"Cannot write sphere ray report");std::cout<<"PASS SPHERE_RAY cases=20000 hits="<<hits<<" inside="<<inside<<" moving="<<moving<<'\n';
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
