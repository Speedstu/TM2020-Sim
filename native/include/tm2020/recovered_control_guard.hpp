#pragma once
#include <array>
#include <cstdint>

namespace tm2020::recovered {
// Offsets are relative to the record at vehicle +0x1280. They are not a
// keyboard/gamepad API; record provenance and physical units remain unproven.
struct NestedControlRecord {
    std::array<float,4> quaternion_60{1,0,0,0}; // scalar first
    std::array<float,3> vector_7c{};
    std::uint32_t flags_f0{};
    float fallback_f4{};
    std::int16_t priority_4e8{};
    std::int16_t limit_4ea{}; // same bytes as vehicle +0x176a
    std::uint32_t flags_4ec{};
};
struct GuardedControlScalars {float scalar_98{},scalar_9c{};};
// Complete 0x83dd60, 0x83dd90 (+0x1955c0), and 0x83de60 respectively.
// Finite floats within +/-10000. Invalid inputs throw before state changes.
float select_nested_control_value(const NestedControlRecord&);
float nested_drive_gate(const NestedControlRecord&);
void update_control_guard(GuardedControlScalars&,const NestedControlRecord&,
    float context_scalar_30);
}
