#include "tm2020/recovered_wheel.hpp"
#include "owned_arithmetic_image.hpp"
#include <iostream>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T,std::size_t N>void put(std::array<std::byte,N>& block,std::size_t offset,const T& value){check(offset+sizeof(T)<=N,"Wheel spin fixture overflow");std::memcpy(block.data()+offset,&value,sizeof(T));}
int main(int argc,char** argv)try{
    check(argc==3,"Usage: wheel_spin_oracle original.exe report.json");const std::array<std::array<unsigned,2>,2> ranges{{{0x843190,0x84355b},{0x83db50,0x83db72}}};ArithmeticImage image(argv[1],ranges);
    using Run=void(*)(void*,std::uint32_t,float,float,std::uint32_t);const auto original=reinterpret_cast<Run>(image.base+0x843190);
    std::mt19937_64 rng(0x2026102321);std::uniform_real_distribution<float> u(-1,1);std::size_t airborne{},contacts{},specials{},future{},state1{},negative_zero{};
    for(std::size_t n=0;n<20000;n++){
        std::array<std::byte,0x1d00> vehicle{};std::array<std::byte,0x1f00> config{};std::array<std::byte,0x30> model{};for(auto& x:vehicle)x=std::byte(rng()&255);
        const std::uint32_t selected=n%4;WheelKinematicState state{};state.spin_rate_1c=u(rng)*300;state.contact_word_34=n%4==0?0:std::array<std::uint32_t,3>{1,0x80000000u,0xffffffffu}[n%3];state.material_40=std::array<std::uint8_t,5>{0,3,21,74,11}[n%5];
        if(n%23==0)state.spin_rate_1c=-0.f;
        const float dt=.001f+std::abs(u(rng))*.1f;const std::uint32_t tick=n%29==0?0xfffffff0u:std::uint32_t(n*10);
        WheelSpinInput input{u(rng)*100,std::abs(u(rng)),std::abs(u(rng)),std::abs(u(rng))*1.5f,std::abs(u(rng))*1.5f,.1f+std::abs(u(rng)),n%2==0,n%17==0,std::uint32_t(rng()%16),std::uint32_t(rng()%16),n%7==0?tick+100u:0xffffffffu,tick};
        if(n%11==0)input.scalar_9c=0;if(n%13==0)input.scalar_98=0;if(n%19==0){input.speed_parameter=-0.f;input.blend_1c3c=1;input.blend_1c40=1;}
        const WheelSpinParameters p{u(rng)*100,u(rng)*100,std::abs(u(rng))*.9f,u(rng)*100};
        put(vehicle,0x88,config.data());put(vehicle,0x388+selected*8,model.data());put(model,4,std::uint32_t(input.model_word_4));put(model,8,input.model_radius_8);
        put(vehicle,0x98,input.scalar_98);put(vehicle,0x9c,input.scalar_9c);put(vehicle,0x1c3c,input.blend_1c3c);put(vehicle,0x1c40,input.blend_1c40);put(vehicle,0x14b8,std::uint32_t(input.override_14b8));put(vehicle,0x176c,input.state_word_176c);put(vehicle,0x1370,input.state_word_1370);put(vehicle,0x13a0,input.future_tick_13a0);
        put(config,0xd90,p.drive_d90);put(config,0xd94,p.brake_d94);put(config,0xd98,p.blend_d98);put(config,0x1ef4,p.special_spin_1ef4);
        put(vehicle,0x1780+selected*0xb8+0x1c,state.spin_rate_1c);put(vehicle,0x1780+selected*0xb8+0x34,state.contact_word_34);put(vehicle,0x1780+selected*0xb8+0x40,state.material_40);auto ported=vehicle;
        original(vehicle.data(),selected,input.speed_parameter,dt,input.tick);update_wheel_spin(state,input,p,dt);put(ported,0x1780+selected*0xb8+0x1c,state.spin_rate_1c);
        if(vehicle!=ported){std::size_t at{};while(at<vehicle.size()&&vehicle[at]==ported[at])++at;std::cerr<<"MISMATCH WHEEL_SPIN case="<<n<<" byte="<<at<<" contact="<<state.contact_word_34<<" material="<<unsigned(state.material_40)<<" gas="<<input.scalar_98<<" brake="<<input.scalar_9c<<'\n';throw std::runtime_error("Wheel spin differs from complete original function");}
        airborne+=state.contact_word_34==0;contacts+=state.contact_word_34!=0;specials+=state.material_40==3||state.material_40==21||state.material_40==74;future+=input.future_tick_13a0!=0xffffffffu&&input.tick<input.future_tick_13a0;state1+=(input.state_word_176c&3)==1||(input.state_word_1370&3)==1;negative_zero+=std::signbit(state.spin_rate_1c)&&state.spin_rate_1c==0;
    }
    std::ofstream report(argv[2]);report<<"{\"schema\":\"tm2020_wheel_spin_oracle_v1\",\"sha256\":\""<<executable_sha256<<"\",\"cases_per_operation\":20000,\"operations\":1,\"bit_exact\":true,\"entry_rva\":\"0x843190\",\"original_instructions_native\":true,\"originalCodeModified\":false,\"functionsSkipped\":false,\"airborne_cases\":"<<airborne<<",\"contact_cases\":"<<contacts<<",\"special_material_injections\":"<<specials<<",\"future_tick_cases\":"<<future<<",\"state_one_cases\":"<<state1<<",\"negative_zero_outputs\":"<<negative_zero<<",\"game_process_accessed\":false,\"complete_physics\":false}\n";report.flush();check(bool(report),"Cannot write wheel spin report");
    std::cout<<"PASS WHEEL_SPIN_ORACLE operations=1 cases_each=20000 bit_exact=true complete_native_function=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
