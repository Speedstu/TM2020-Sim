#pragma once
#include "tm2020/recovered_wheel.hpp"
namespace tm2020::recovered {
struct VehicleResistanceState {
 float scalar_98{},scalar_9c{},multiplier_1c44{},curve_input_13a4{},manager_a5c{},scalar_1760{};
 std::uint32_t state_word_176c{},state_word_1370{},word_138c{},word_1408{},timer_1410{},word_1600{};
 std::array<std::uint32_t,4> wheel_contacts{};
};
struct VehicleResistanceParameters {
 std::int32_t variant_1790{};
 float constant_17a8{},linear_17ac{};
 std::uint32_t duration_1bdc{};
 VehicleCurveView curve_9f8,curve_17b8,curve_2060;
};
// Complete 0x7bdf40, native row-specific evaluation order and angular-only add.
void apply_local_torque(ForceAccumulator&,const RigidState&,const std::array<float,3>&);
// Complete 0x846010 with original force callees, wake queue disabled.
// Includes scalar/status gates, signed variant comparison, uint timer update,
// normalized constant/linear resistance, timed braking and airborne angular
// damping. It does not generate tire contact or drive traction.
// Finite inputs/outputs <=1e6, quaternion components<=16, explicit race tuning.
// Both force accumulator and mutable state are transactional on rejection.
void apply_vehicle_resistance(ForceAccumulator&,VehicleResistanceState&,const RigidState&,
 const std::array<float,3>& local_velocity,const VehicleResistanceParameters&,std::uint32_t tick,float blend);
}
