#pragma once
#include "tm2020/recovered_wheel_material.hpp"
namespace tm2020::recovered {
// Complete engine approximations 0x18d150 / 0x18d230. |x|<=100000.
// Mathematical inverse-trig domain is [-1,1]; beyond it, native sqrt-clamp
// and polynomial signed-zero behavior are preserved, not std::asin/acos.
float fast_asin(float x);
float fast_acos(float x);
struct SteeringAngleParameters {float offset_1808{},speed_slope_180c{};};
// Complete 0x841b40. Source velocity's third lane and raw steering +0x1430;
// status words +0x176c/+0x1370. Float inputs finite within +/-1e6.
float vehicle_steering_angle(float velocity_z,float steering_1430,
    const SteeringAngleParameters&,std::uint32_t state_176c,std::uint32_t state_1370);
struct SurfaceScalarInput {
    std::array<float,3> velocity{};
    float scalar_98{},scalar_9c{};
    std::array<std::uint32_t,4> wheel_contact_34{};
    std::uint32_t word_138c{};
};
// Complete 0x8465e0 with full curve callee. Keeps the +0x13a4 field's raw
// offset label: its physical interpretation has not been independently proven.
// Velocity components <=10000, other used floats <=1e6, interval [1e-6,1].
// Only scalar changes; no contact or +0x138c gate leaves it untouched.
void update_surface_scalar(float& scalar_13a4,const SurfaceScalarInput&,
    const SurfaceBlendValues&,VehicleCurveView speed_curve_638,float interval);
}
