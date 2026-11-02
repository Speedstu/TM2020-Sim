#include "tm2020/recovered_vehicle.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T,std::size_t N>void put(std::array<std::byte,N>& block,std::size_t offset,const T& value){check(offset+sizeof(T)<=N,"Synthetic layout overflow");std::memcpy(block.data()+offset,&value,sizeof(T));}
template<class T>void same(const T& expected,const T& actual,std::size_t n,const char* field){
    if(std::memcmp(&expected,&actual,sizeof(T))==0)return;
    std::cerr<<"Vehicle mismatch case="<<n<<" field="<<field<<'\n';throw std::runtime_error("Vehicle kernel differs from original");
}
struct Curve {std::uint32_t flags{},padding{};const CurvePoint* data{};std::uint32_t count{},capacity{};};
int main(int argc,char** argv)try{
    check(argc==3,"Usage: vehicle_kernel_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,7> ranges{{{0x42bba0,0x42bdee},{0x844090,0x84412b},{0x845100,0x845108},{0x7bda90,0x7bdc54},{0x7bd310,0x7bd4af},{0x7be690,0x7be6a6},{0x7b9b70,0x7b9bd6}}};ArithmeticImage image(argv[1],ranges);
    using Evaluate=float(*)(const Curve*,float);const auto evaluate=reinterpret_cast<Evaluate>(image.base+0x42bcb0);
    using Apply=void(*)(void*,std::uint32_t,const void*,const void*);const auto apply=reinterpret_cast<Apply>(image.base+0x7bda90);
    using Spring=void(*)(void*,void*,const void*,const void*);const auto spring=reinterpret_cast<Spring>(image.base+0x844090);
    std::mt19937_64 rng(0x2026102311);std::uniform_real_distribution<float> u(-1,1);constexpr std::size_t count=20000;std::size_t applied{};
    for(std::size_t n=0;n<count;n++){
        std::vector<CurvePoint> points(n%19);float next_x=-3;
        for(auto& p:points){next_x+=.1f+std::abs(u(rng));p={next_x,u(rng)*100};}
        if(n%13==0)for(auto& p:points)p.y=-0.f;
        const auto flags=std::array<std::uint32_t,8>{0,1,2,0x10,0x30,0x12,0x11,0x32}[n%8];
        float x=u(rng)*10;
        if(!points.empty()&&n%3==0)x=points[(n/3)%points.size()].x;
        if(!points.empty()&&n%5==0)x=points.front().x+1e-5f;
        if(!points.empty()&&n%7==0)x=points.back().x-1e-5f;
        Curve curve{flags,0,points.data(),std::uint32_t(points.size()),std::uint32_t(points.size())};
        const float expected=evaluate(&curve,x),actual=evaluate_curve(points,x,flags);same(expected,actual,n,"curve");
        RigidState pose{};for(float& v:pose.rotation)v=u(rng);for(float& v:pose.position)v=u(rng)*10;
        std::array<float,3> center{},force{},point{};for(auto* v:{&center,&force,&point})for(float& z:*v)z=u(rng)*2;
        ForceAccumulator before{};for(auto* v:{&before.linear,&before.angular})for(float& z:*v)z=u(rng)*5;
        if(n%17==0){pose={};center={-0.f,0,-0.f};force={0,-0.f,0};point={-0.f,0,0};before={};}
        std::array<std::byte,0x110> manager{};std::array<std::byte,0x60> model{};std::array<std::byte,0x1c00> vehicle{};
        std::array<std::uint32_t,4> index{0,0,0,0};auto* model_pointer=model.data();ForceAccumulator native=before;
        put(manager,0x10,&model_pointer);put(manager,0x70,&pose);put(manager,0xa0,&native);put(manager,0xb0,index.data());put(model,0x40,center);
        auto ported=before;apply(manager.data(),3,&force,&point);apply_local_force_at_point(ported,pose,center,force,point);same(native,ported,n,"local force/torque");
        SuspensionParameters parameters{std::uint32_t(n%4),n%2==0,40+u(rng)*20,1+u(rng)*.5f,.2f+u(rng)*.1f};
        std::array<SuspensionWheelState,4> wheels{};
        for(std::size_t j=0;j<4;j++){
            wheels[j]={u(rng)*.4f,u(rng),n%7!=0||j%2==0};
            put(vehicle,0x1780+j*0xb8,wheels[j].length);put(vehicle,0x1784+j*0xb8,wheels[j].speed);put(vehicle,0x17b4+j*0xb8,std::uint32_t(wheels[j].contact));
        }
        const auto selected=(n/4)%4;std::array<std::byte,0x20> wheel_model{};put(wheel_model,0x10,point);auto* wheel_pointer=wheel_model.data();
        // Config native offsets +0x238..+0x244 need 0x248 bytes.
        std::array<std::byte,0x250> suspension_config{};put(suspension_config,0x238,parameters.mode);put(suspension_config,0x23c,parameters.stiffness);put(suspension_config,0x240,parameters.damping);put(suspension_config,0x244,parameters.rest_length);
        put(vehicle,0x88,suspension_config.data());put(vehicle,0x10,std::uint32_t(3));put(vehicle,0x171c,std::uint32_t(parameters.require_all_contacts));
        native=before;ported=before;spring(manager.data(),vehicle.data(),&wheel_pointer,vehicle.data()+0x1780+selected*0xb8);
        const bool called=apply_suspension_mode2(ported,pose,center,point,parameters,wheels,selected);same(native,ported,n,"complete mode2 spring force");if(called)++applied;
    }
    std::ofstream out(argv[2]);out<<"{\"schema\":\"tm2020_vehicle_kernel_oracle_v1\",\"sha256\":\""<<executable_sha256
        <<"\",\"cases_per_operation\":20000,\"operations\":3,\"bit_exact\":true,\"original_instructions_native\":true,\"suspension_force_calls\":"<<applied
        <<",\"wake_queue_disabled\":true,\"curve_modes\":[\"step\",\"linear\",\"smoothstep\",\"Hermite\",\"zero_final_tangent\"],\"game_process_accessed\":false,\"complete_physics\":false}\n";
    out.flush();check(bool(out),"Cannot save vehicle oracle");std::cout<<"PASS VEHICLE_KERNEL_ORACLE cases_each=20000 bit_exact=true suspension_calls="<<applied<<" complete_physics=false\n";
}catch(const std::exception& e){std::cerr<<"VEHICLE_KERNEL_ORACLE_ERROR "<<e.what()<<'\n';return 1;}
