#pragma once
#include "internal_tick.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

namespace tm2020::internal {
// Original scene decoder 0x12bce40, SHA-pinned build. These fields are inputs
// to the normal decoder and replay history, not vehicle output/visual fields.
struct PlayerInputRecord {
    std::uint32_t bits{};
    std::array<float,4> axes{}; // steering, throttle, brake, unused axis
    std::array<std::uint16_t,2> shorts{};
    std::uint32_t buttons{};
};
static_assert(sizeof(PlayerInputRecord)==28&&offsetof(PlayerInputRecord,axes)==4);
inline bool driving_record(const PlayerInputRecord& r)noexcept{
    return (r.bits&15)==2&&std::isfinite(r.axes[0])&&std::abs(r.axes[0])<=1.f&&
        std::isfinite(r.axes[1])&&r.axes[1]>=0&&r.axes[1]<=1&&
        std::isfinite(r.axes[2])&&r.axes[2]>=0&&r.axes[2]<=1;
}
inline std::array<float,3> input_axes(Controls c)noexcept{return {c.steer,c.gas,c.brake};}
inline Controls input_controls(const PlayerInputRecord& r)noexcept{return {r.axes[1],r.axes[2],r.axes[0]};}
inline bool same_input_controls(Controls a,Controls b)noexcept{
    return valid(a)&&valid(b)&&a.gas==b.gas&&a.brake==b.brake&&a.steer==b.steer;
}
inline bool input_record_owner(std::uintptr_t player,std::uintptr_t previous,std::uintptr_t next,
        std::uint32_t descriptor_type,std::uintptr_t vehicle)noexcept{
    return player>=0x10000&&previous==player+0x1a8&&next==player+0x188&&
        descriptor_type==0x0a020000&&vehicle>=0x10000;
}
}
