#include "tm2020/recovered_control_guard.hpp"
#include "owned_arithmetic_image.hpp"
#include <bit>
#include <cmath>
#include <iostream>
#include <limits>
#include <random>
using namespace tm2020::recovered;
using namespace tm2020::testing;
template<class T,std::size_t N>
void put(std::array<std::byte,N>& bytes,std::size_t offset,const T& value) {
    check(offset+sizeof(value)<=N,"Fixture extent");
    std::memcpy(bytes.data()+offset,&value,sizeof(value));
}
void same(float a,float b,std::size_t n,const char* label) {
    if (std::bit_cast<std::uint32_t>(a)!=std::bit_cast<std::uint32_t>(b)) {
        std::cerr<<label<<" case="<<n<<" original="<<a<<" port="<<b<<'\n';
        throw std::runtime_error("Control guard differential mismatch");
    }
}
int main(int argc,char** argv) try {
    check(argc==3,"Usage: control_guard_oracle original.exe report.json");
    const std::array<std::array<unsigned,2>,7> ranges{{
        {0x83db80,0x83dba2},{0x83dbf0,0x83dc0b},{0x83dc30,0x83dc60},
        {0x83dd60,0x83dd85},{0x83dd90,0x83de20},{0x83de60,0x83df0c},
        {0x1955c0,0x1956e0}}};
    ArithmeticImage image(argv[1],ranges);
    using Scalar=float(*)(const void*);
    using Update=void(*)(void*);
    const auto select=reinterpret_cast<Scalar>(image.base+0x83dd60);
    const auto gate=reinterpret_cast<Scalar>(image.base+0x83dd90);
    const auto update=reinterpret_cast<Update>(image.base+0x83de60);
    std::mt19937_64 rng(0x202610230029);
    std::uniform_real_distribution<float> unit(-1.f,1.f);
    const std::array<float,10> edge{-10000.f,-1.f,-0.f,0.f,
        std::nextafter(0.f,1.f),std::nextafter(0.f,-1.f),1.f,10000.f,
        std::nextafter(1.f,0.f),std::nextafter(1.f,2.f)};
    const std::array<std::int16_t,7> short_edge{-32768,-32767,-1,0,1,32766,32767};
    for(std::size_t n=0;n<20000;++n) {
        std::array<std::byte,0x1e00> vehicle{};
        std::array<std::byte,0x80> context{};
        for(auto& x:vehicle)x=std::byte(rng()&255);
        for(auto& x:context)x=std::byte(rng()&255);
        NestedControlRecord r;
        for(auto& x:r.quaternion_60)x=unit(rng)*(n%2 ? 1.f : 10000.f);
        for(auto& x:r.vector_7c)x=unit(rng)*10000.f;
        if(n%5==0)r.quaternion_60={1,0,0,0};
        r.fallback_f4=n%3 ? edge[n%edge.size()] : unit(rng)*10000.f;
        r.priority_4e8=n%2 ? 0 : short_edge[(n/2)%short_edge.size()];
        r.flags_f0=std::uint32_t(n&7) | (std::uint32_t(rng())&~7u);
        r.flags_4ec=std::uint32_t((n>>3)&7) | (std::uint32_t(rng())&~7u);
        if(n%7==0)r.vector_7c[2]=r.priority_4e8 ? float(r.priority_4e8) : r.fallback_f4;
        // The record vector domain is +/-10000; signed-short targets may be wider.
        if(std::abs(r.vector_7c[2])>10000.f)r.vector_7c[2]=10000.f;
        GuardedControlScalars state{edge[(n/3)%edge.size()],edge[(n/7)%edge.size()]};
        const auto limit=short_edge[(n/11)%short_edge.size()];
        r.limit_4ea=limit;
        r.flags_4ec=(r.flags_4ec&~0x400u) | (n%2 ? 0x400u : 0);
        const float bound=float(std::abs(int(limit)));
        float scalar=unit(rng)*10000.f;
        if(bound<=10000.f && n%4==0)scalar=n%8 ? bound : -bound;
        put(vehicle,0x1280+0x60,r.quaternion_60);
        put(vehicle,0x1280+0x7c,r.vector_7c);
        put(vehicle,0x1280+0xf0,r.flags_f0);
        put(vehicle,0x1280+0xf4,r.fallback_f4);
        put(vehicle,0x1280+0x4e8,r.priority_4e8);
        put(vehicle,0x1280+0x4ec,r.flags_4ec);
        put(vehicle,0x98,state.scalar_98);put(vehicle,0x9c,state.scalar_9c);
        put(vehicle,0x1280+0x4ea,r.limit_4ea);
        put(context,8,vehicle.data());put(context,0x30,scalar);
        same(select(vehicle.data()+0x1280),select_nested_control_value(r),n,"select");
        same(gate(vehicle.data()+0x1280),nested_drive_gate(r),n,"gate");
        auto expected=vehicle;const auto initial_context=context;
        update(context.data());
        update_control_guard(state,r,scalar);
        put(expected,0x98,state.scalar_98);put(expected,0x9c,state.scalar_9c);
        if(vehicle!=expected) {
            std::cerr<<"complete_update case="<<n<<'\n';
            throw std::runtime_error("Complete vehicle bytes differ");
        }
        check(context==initial_context,"Context changed");
    }
    NestedControlRecord invalid;
    invalid.vector_7c[0]=std::numeric_limits<float>::quiet_NaN();
    GuardedControlScalars state{.5f,-0.f};const auto before=state;
    bool rejected=false;
    try {update_control_guard(state,invalid,0);}catch(const std::invalid_argument&){rejected=true;}
    check(rejected && std::memcmp(&state,&before,sizeof(state))==0,"Invalid input mutated state");
    std::ofstream report(argv[2]);
    report<<"{\"schema\":\"tm2020_control_guard_oracle_v1\",\"sha256\":\""<<executable_sha256
      <<"\",\"cases_per_operation\":20000,\"operations\":3,\"bit_exact\":true,"
      <<"\"entry_rvas\":[\"0x83dd60\",\"0x83dd90\",\"0x83de60\"],"
      <<"\"whole_vehicle_bytes_checked\":true,\"quaternion_callee_executed\":true,"
      <<"\"signed_short_extrema\":true,\"all_low_flag_combinations\":true,"
      <<"\"finite_float_limit\":10000,\"invalid_input_atomic\":true,"
      <<"\"originalCodeModified\":false,\"game_process_accessed\":false,"
      <<"\"raw_player_action_mapping_verified\":false,\"full_simulator\":false}\n";
    report.flush();check(bool(report),"Cannot write control guard report");
    std::cout<<"PASS CONTROL_GUARD_ORACLE operations=3 cases_each=20000 bit_exact=true whole_vehicle_bytes=true\n";
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
