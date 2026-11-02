#include "tm2020/visual_state.hpp"
#include <bit>
#include <cmath>
#include <cstring>
#include <algorithm>
namespace tm2020::live {
std::optional<ReflectedVisualState> decode_visual_state(std::span<const std::byte> b){
    static_assert(std::endian::native==std::endian::little);
    if(b.size()!=visual_state_bytes)return std::nullopt;
    auto u=[&](std::size_t at){std::uint32_t x;std::memcpy(&x,b.data()+at,4);return x;};
    auto f=[&](std::size_t at){return std::bit_cast<float>(u(at));};
    auto vec=[&](std::size_t at){return Vec3{f(at),f(at+4),f(at+8)};};
    ReflectedVisualState s;
    for(std::size_t i=0;i<4;i++)s.raw_header_words[i]=u(i*4);
    for(std::size_t i=0;i<9;i++)s.location_rotation_matrix[i]=f(0x2c+i*4);
    bool orthonormal=true;
    for(std::size_t row=0;row<3;row++)for(std::size_t other=0;other<3;other++){
        double dot=0;
        for(std::size_t k=0;k<3;k++)dot+=s.location_rotation_matrix[row*3+k]*s.location_rotation_matrix[other*3+k];
        orthonormal&=std::isfinite(dot)&&std::abs(dot-(row==other?1.:0.))<.02;
    }
    const auto& m=s.location_rotation_matrix;
    const double det=m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6]);
    s.rotation_matrix_is_orthonormal=orthonormal&&std::abs(det-1)<.02;
    s.position=vec(0x50);s.world_velocity=vec(0x5c);
    s.input_steer=f(0x10);s.input_gas=f(0x14);s.input_brake=f(0x18);
    s.input_is_braking=(u(0x20)&0xff)!=0;
    s.front_speed=f(0x74);
    auto flags=u(0x88);
    // Ground/engine/turbo/top masks independently checked in getter assembly.
    s.ground_contact=(flags&(1u<<20))!=0;s.engine_on=(flags&(1u<<23))!=0;
    s.turbo=(flags&(1u<<24))!=0;s.top_contact=(flags&(1u<<4))!=0;
    s.gear=std::bit_cast<std::int32_t>(u(0x1a4));
    s.race_start_time=std::bit_cast<std::int32_t>(u(0x1b4));
    std::memcpy(&s.discontinuity_count,b.data()+0xa,1);
    for(std::size_t i=0;i<4;i++){
        auto& w=s.wheels[i];const auto a=0xa8+i*0x2c;
        w.damper_length=f(a);w.rotation=f(a+4);w.rotation_speed=f(a+8);
        w.steer_angle=f(a+12);w.slip=f(a+20);w.icing=f(a+28);
        w.tire_wear=f(a+32);w.brake_coefficient=f(a+36);
    }
    for(double x:{s.position.x,s.position.y,s.position.z,s.world_velocity.x,
                  s.world_velocity.y,s.world_velocity.z,double(s.input_steer),
                  double(s.input_gas),double(s.input_brake),double(s.front_speed)})
        if(!std::isfinite(x)||std::abs(x)>100000)return std::nullopt;
    if(std::abs(s.input_steer)>1.01||s.input_gas<-.01||s.input_gas>1.01||
       s.input_brake<-.01||s.input_brake>1.01)return std::nullopt;
    if(s.gear<-1||s.gear>16||std::abs(s.front_speed)>1000||
       std::hypot(s.world_velocity.x,std::hypot(s.world_velocity.y,s.world_velocity.z))>1000)
        return std::nullopt;
    for(const auto& w:s.wheels)
        for(float x:{w.rotation,w.rotation_speed,w.steer_angle,w.damper_length,w.slip,w.icing,w.tire_wear,w.brake_coefficient})
            if(!std::isfinite(x)||std::abs(x)>1e7)return std::nullopt;
    return s;
}
std::optional<FreshVisualSample> select_fresh_visual(
    std::span<const std::optional<ReflectedVisualState>> copies,std::optional<Vec3> anchor,bool active){
    auto newer=[](std::uint32_t a,std::uint32_t b){return std::bit_cast<std::int32_t>(a-b)>0;};
    auto distance=[](Vec3 a,Vec3 b){return std::hypot(a.x-b.x,std::hypot(a.y-b.y,a.z-b.z));};
    auto valid=[](const auto& c){return c&&c->raw_header_words[0]==0x02000006;};
    const ReflectedVisualState* episode=nullptr;std::uint32_t count{};
    for(const auto& c:copies)if(valid(c)){
        count++;
        if(!episode||newer(static_cast<std::uint32_t>(c->race_start_time),static_cast<std::uint32_t>(episode->race_start_time)))episode=&*c;
    }
    if(!episode||count<3)return std::nullopt;
    const ReflectedVisualState* newest=nullptr;
    for(const auto& c:copies)if(valid(c)&&c->race_start_time==episode->race_start_time){
        if(anchor&&distance(c->position,*anchor)>2.)continue;
        if(!newest||newer(c->raw_header_words[3],newest->raw_header_words[3]))newest=&*c;
    }
    if(!newest)return std::nullopt;
    const auto newest_clock=newest->raw_header_words[3];
    // Bias toward a causal input response only within 100 ms of the newest
    // candidate. Otherwise braking/coasting would pin an old gas-on buffer.
    const bool active_seen=active&&std::any_of(copies.begin(),copies.end(),[&](const auto& c){
        return valid(c)&&c->race_start_time==episode->race_start_time&&c->input_gas>.5&&
            newest_clock-c->raw_header_words[3]<=100&&(!anchor||distance(c->position,*anchor)<=2.);
    });
    if(active_seen){
        const ReflectedVisualState* selected=nullptr;
        for(const auto& c:copies)if(valid(c)&&c->race_start_time==episode->race_start_time&&c->input_gas>.5&&
            newest_clock-c->raw_header_words[3]<=100&&(!anchor||distance(c->position,*anchor)<=2.))
            if(!selected||newer(c->raw_header_words[3],selected->raw_header_words[3]))selected=&*c;
        newest=selected;
    }
    FreshVisualSample result{*newest,newest->raw_header_words[3],0,count,false};
    for(const auto& c:copies)if(valid(c)&&c->race_start_time==newest->race_start_time){
        if(result.clock_candidate_ms-c->raw_header_words[3]<=200&&distance(c->position,newest->position)<2.)result.agreeing_copies++;
    }
    if(result.agreeing_copies<(anchor||active_seen?1u:2u))return std::nullopt;
    return result;
}
}
