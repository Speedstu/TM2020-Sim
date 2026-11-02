#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
namespace tm2020::internal {
// Read-only statistics over the exact commands sent to normal physics.
// Run-duration histograms have one bin per 10ms tick (up to 40.96s).
struct InputStatistics {
    static constexpr unsigned duration_bins=4096;
    static constexpr unsigned steer_hold_offset=264;
    static constexpr unsigned gas_press_offset=steer_hold_offset+duration_bins;
    static constexpr unsigned gas_release_offset=gas_press_offset+duration_bins;
    static constexpr unsigned brake_press_offset=gas_release_offset+duration_bins;
    static constexpr unsigned brake_release_offset=brake_press_offset+duration_bins;
    static constexpr unsigned size=brake_release_offset+duration_bins;
    std::array<std::uint32_t,size> counts{};
    int steer{},gas{},brake{},last_delta{};
    std::uint32_t last_change{},steer_hold{},gas_press{},gas_release{},brake_press{},brake_release{};
    static unsigned bucket(std::uint32_t ticks) noexcept {
        return ticks?std::min(ticks,duration_bins)-1:0;
    }
    void flush(unsigned offset,std::uint32_t ticks) noexcept {if(ticks)++counts[offset+bucket(ticks)];}
    void observe(float g,float b,float s) noexcept {
        const int next=static_cast<int>(std::round(s*127.f));
        const auto tick=counts[0];
        if(tick){
            const int d=next-steer,step=std::abs(d);
            ++counts[9+static_cast<unsigned>(step)];
            if(d){
                ++counts[1];counts[2]+=step;
                if(last_delta&&tick-last_change<=10&&d*last_delta<0){
                    ++counts[3];if(step<=2&&std::abs(last_delta)<=2)++counts[4];
                }
                last_delta=d;last_change=tick;
            }
            counts[5]+=int(g)!=gas;counts[6]+=int(b)!=brake;
            if(next!=steer){flush(steer_hold_offset,steer_hold);steer_hold=0;}
            if((g==1.f)!=(gas!=0)){
                if(gas)flush(gas_press_offset,gas_press);else flush(gas_release_offset,gas_release);
                gas_press=gas_release=0;
            }
            if((b==1.f)!=(brake!=0)){
                if(brake)flush(brake_press_offset,brake_press);else flush(brake_release_offset,brake_release);
                brake_press=brake_release=0;
            }
        }
        ++counts[0];counts[7]+=g==1.f;counts[8]+=b==1.f;
        ++steer_hold;
        if(g==1.f){++gas_press;gas_release=0;}else{++gas_release;gas_press=0;}
        if(b==1.f){++brake_press;brake_release=0;}else{++brake_release;brake_press=0;}
        steer=next;gas=int(g);brake=int(b);
    }
    std::array<std::uint32_t,size> snapshot()const noexcept {
        auto out=counts;auto add=[&](unsigned offset,std::uint32_t ticks){if(ticks)++out[offset+bucket(ticks)];};
        add(steer_hold_offset,steer_hold);add(gas_press_offset,gas_press);add(gas_release_offset,gas_release);
        add(brake_press_offset,brake_press);add(brake_release_offset,brake_release);return out;
    }
};
}
