#pragma once
#include "tm2020/recovered_rigid.hpp"
#include <bit>
namespace tm2020::recovered {
// Explicit construction in 0x12e9ea0: 10 integer milliseconds and the float
// below. It differs by one binary32 ULP from the C++ literal .01f.
inline constexpr std::uint32_t native_vehicle_interval_ms=10;
inline constexpr float native_vehicle_interval=std::bit_cast<float>(0x3c23d70bu);
// Complete leaf 0x7f3ec0: the engine's binary32 approximation, not std::exp2.
// Finite exponent domain [-200,100]; native lower clamp is -126.
float approximate_power_of_two(float exponent);
struct StepParameters {
    float interval{},inverse_interval{},decay_multiplier{},gravity_magnitude{};
    float depenetration_impulse_factor{},allowed_penetration{},max_depenetration_velocity{};
    std::uint32_t use_constraints2{};
    float min_velocity_for_restitution{};
    // Copied integer words: their enclosing-context meanings are not qualified.
    std::uint32_t opaque_24{},opaque_28{};
};
static_assert(sizeof(StepParameters)==44);
static_assert(offsetof(StepParameters,use_constraints2)==0x1c);
// Complete constructor 0x8020a0, including its approximation helper. Finite
// gravity/configuration floats within +/-1e6 and interval [1e-6,1]. No game,
// TLS, allocation containers, clock inference or scheduling in this operation.
StepParameters prepare_step_parameters(float interval,const std::array<float,3>& gravity,
    const SolverParameters& solver,std::uint32_t opaque_24,std::uint32_t opaque_28);
struct VehicleSubstepSelection {
    std::uint32_t substeps{};
    float repeated_unscaled_interval{},repeated_scaled_interval{},total_scaled_interval{};
    // Original multiplies by -1e9, then subtracts this signed value from time.
    std::int64_t timestamp_subtrahend_nanoseconds{};
};
struct VehicleSubstepMotion {
    std::array<float,3> linear_velocity{},angular_velocity{},vector_1348{},vector_1354{};
};
// Prefix slice 0x15019f7..0x1501b52: four ordered binary32 lengths, their
// ordered sum, then multiplication by (time_scale * interval). Model lookup
// at 0x1501b52 remains outside the arithmetic port. Vector components +/-10000.
float scaled_vehicle_substep_motion(const VehicleSubstepMotion&,float time_scale,float interval);
// Arithmetic slice 0x1501b57..0x1501bd7, with single-step exit 0x1501ce4.
// scaled_motion is the already computed four-magnitude sum times scaled dt.
// This does not compute those magnitudes, find model/vehicle pointers, execute
// contacts, or qualify the surrounding complete scene scheduler.
// Domain: motion [0,1e9], limit [1e-6,1e6], ratio <=1e6,
// time scale [1e-4,100], interval [1e-6,1].
VehicleSubstepSelection select_vehicle_substeps(float scaled_motion,float motion_limit,
    float time_scale,float interval);
VehicleSubstepSelection select_vehicle_substeps(const VehicleSubstepMotion&,float motion_limit,
    float time_scale,float interval);
// Original repeated subtraction, preserving the final residual's rounding.
float vehicle_last_substep_interval(const VehicleSubstepSelection&);
}
