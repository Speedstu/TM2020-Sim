#include "tm2020/recovered_steering.hpp"
#include "tm2020/recovered_step.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <iostream>
#include <random>
using namespace tm2020::recovered;using namespace tm2020::testing;
template<class T,std::size_t N>void put(std::array<std::byte,N>& bytes,std::size_t offset,const T& value){check(offset+sizeof(value)<=N,"Fixture extent");std::memcpy(bytes.data()+offset,&value,sizeof(value));}
template<class T>void same(const T&a,const T&b,std::size_t n,const char* label){if(std::memcmp(&a,&b,sizeof(T))){std::cerr<<"MISMATCH "<<label<<" case="<<n<<'\n';throw std::runtime_error("Complete steering/surface procedure differs");}}
struct Curve {std::uint32_t flags{},pad{};const CurvePoint* points{};std::uint32_t count{},opaque{};};
int main(int argc,char**argv)try{
    check(argc==3,"Usage: steering_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,6> ranges{{{0x18d150,0x18d30e},{0x841b40,0x841bec},{0x83dbd0,0x83dbeb},{0x8465e0,0x84675e},{0x843150,0x84317b},{0x42bba0,0x42bdee}}};ArithmeticImage image(argv[1],ranges);
    using Inverse=float(*)(float);using Steering=void(*)(void*,const void*,void*);using Recovery=void(*)(void*,const void*);
    const auto asin=reinterpret_cast<Inverse>(image.base+0x18d150),acos=reinterpret_cast<Inverse>(image.base+0x18d230);
    const auto steering=reinterpret_cast<Steering>(image.base+0x841b40);const auto recovery=reinterpret_cast<Recovery>(image.base+0x8465e0);
    std::mt19937_64 rng(0x2026102601);std::uniform_real_distribution<float> unit(-1,1);
    const std::array<float,14> special{-100000,-2,-1,std::nextafter(-1.f,0.f),-.5f,-0.f,0.f,std::nextafter(0.f,1.f),.5f,std::nextafter(1.f,0.f),1,2,100000,std::nextafter(100000.f,0.f)};
    for(std::size_t n=0;n<20000;n++){
        const float x=n%3==0?special[(n/3)%special.size()]:unit(rng)*(n%2?1.f:100000.f);
        same(asin(x),fast_asin(x),n,"asin");same(acos(x),fast_acos(x),n,"acos");
        std::array<std::byte,0x1d00> vehicle{},expected_vehicle{};std::array<std::byte,0x2100> config{};std::array<std::byte,0x80> context{};
        put(vehicle,0x88,config.data());std::array<float,3> velocity{};for(auto&v:velocity)v=unit(rng)*10000.f;
        velocity[2]=n%17==0?std::array{-1e-5f,0.f,1e-5f}[(n/17)%3]:velocity[2];
        const float raw_steering=unit(rng);put(vehicle,0x1430,raw_steering);
        const auto status_a=std::uint32_t(rng()),status_b=n%2?0u:std::uint32_t(rng());put(vehicle,0x176c,status_a);put(vehicle,0x1370,status_b);
        SteeringAngleParameters tuning{unit(rng)*10,unit(rng)};if(n%13==0)tuning={std::array{0.f,1e-5f,1.f,2.f}[(n/13)%4],0};put(config,0x1808,tuning);
        std::array<float,3> output{-123.f,77.f,456.f};steering(vehicle.data(),velocity.data(),&output[1]);
        same(output[1],vehicle_steering_angle(velocity[2],raw_steering,tuning,status_a,status_b),n,"complete_steering");check(output[0]==-123&&output[2]==456,"Steering output guards changed");
        SurfaceScalarInput input{velocity,unit(rng),unit(rng),{},n%7==0?1u:0u};for(unsigned j=0;j<4;j++)input.wheel_contact_34[j]=n%9==0?0:std::uint32_t((n+j)%3);put(vehicle,0x98,input.scalar_98);put(vehicle,0x9c,input.scalar_9c);put(vehicle,0x138c,input.word_138c);for(unsigned j=0;j<4;j++)put(vehicle,0x1780+j*0xb8+0x34,input.wheel_contact_34[j]);
        float scalar=unit(rng)*2;put(vehicle,0x13a4,scalar);put(context,8,vehicle.data());put(context,0x28,velocity);put(context,0x40,config.data());const float interval=n%11==0?native_vehicle_interval:std::abs(unit(rng))*.999f+1e-6f;put(context,0x18,interval);
        SurfaceBlendValues material{};material.word_28=std::array<std::uint32_t,6>{0,1,20000,1000000,0x80000000u,0xffffffffu}[n%6];material.values_2c_34[0]=unit(rng)*2;
        std::array<CurvePoint,5> points{};for(unsigned j=0;j<5;j++)points[j]={float(j)*20000.f,unit(rng)*2};const auto count=std::uint32_t(n%6),flags=std::array<std::uint32_t,5>{0,1,2,0x10,0x30}[n%5];put(config,0x638,Curve{flags,0,points.data(),count,0});
        expected_vehicle=vehicle;const auto input_context=context;const auto input_config=config;recovery(context.data(),&material);update_surface_scalar(scalar,input,material,{std::span(points.data(),count),flags},interval);put(expected_vehicle,0x13a4,scalar);same(vehicle,expected_vehicle,n,"complete_surface_scalar");same(context,input_context,n,"context_unchanged");same(config,input_config,n,"config_unchanged");
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_steering_surface_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":4,\"bit_exact\":true,\"entry_rvas\":[\"0x18d150\",\"0x18d230\",\"0x841b40\",\"0x8465e0\"],\"inverse_trig_maximum_absolute_argument\":100000,\"whole_vehicle_bytes_checked\":true,\"curve_callee_executed\":true,\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"game_process_accessed\":false,\"complete_tire_forces\":false}\n";report.flush();check(bool(report),"Cannot save steering report");std::cout<<"PASS STEERING_SURFACE_ORACLE operations=4 cases_each=20000 bit_exact=true full_functions=true\n";
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
