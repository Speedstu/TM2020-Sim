#pragma once
#include "tm2020/recovered_contacts.hpp"
namespace tm2020::recovered {
// Complete 0x7bdd20 local-force rotation and linear accumulation. Does not
// create torque. Native wake-queue bookkeeping is outside this arithmetic API.
void apply_local_force(ForceAccumulator& accumulator,const RigidState& pose,const std::array<float,3>& local_force);
struct AuxiliaryVehicleForceParameters {
    float coefficient_1efc{},coefficient_1f00{},coefficient_1f04{},coefficient_1f08{};
};
struct AuxiliaryVehicleForceState {
    std::array<float,3> local_velocity{};
    float scalar_98{},scalar_9c{};
    std::uint32_t state_word_176c{},state_word_1370{};
};
struct AuxiliaryWheelForcePoint {std::array<float,3> local_point{};std::uint32_t flags_70{};};
// Full 0x84da80 arithmetic, including raw status gates, speed/input thresholds,
// center drag and front/rear local force-at-point calls. Field names retain
// verified native offsets: their complete gameplay meaning is not inferred.
// <=4 wheels; coefficient_1f00 >=0; awake native manager with wake queue disabled.
// This helper alone is not the complete tire/slip model or effective tuning.
void apply_auxiliary_vehicle_forces(ForceAccumulator& accumulator,const RigidState& pose,
    const std::array<float,3>& model_center,const AuxiliaryVehicleForceState& state,
    const AuxiliaryVehicleForceParameters& parameters,std::span<const AuxiliaryWheelForcePoint> wheels,float magnitude);
struct CurvePoint {float x{},y{};};
// Complete 0x42bcb0 + 0x42bba0: clamp, step, linear, smoothstep and Hermite.
// Flags 1=step, 2=smoothstep, 0x10=Hermite, 0x20=zero final Hermite tangent.
// SDK requires strictly increasing finite abscissae; empty curve returns +0.
float evaluate_curve(std::span<const CurvePoint> points,float x,std::uint32_t flags=0);
// 0x7bda90 + 0x7bd310 arithmetic: transform local force and application point,
// accumulate world force/torque about model-local center of mass. Sleep queues,
// manager index translation and wake bookkeeping are caller responsibilities.
void apply_local_force_at_point(ForceAccumulator& accumulator,const RigidState& pose,
    const std::array<float,3>& model_center_of_mass,const std::array<float,3>& local_force,
    const std::array<float,3>& local_point);
// Full 0x844090 selected branch through force/torque accumulation, qualified
// with the native manager's wake queue disabled. Does not supply race settings
// or the wheel collision/contact update, nor implement suspension modes 0/1.
bool apply_suspension_mode2(ForceAccumulator& accumulator,const RigidState& pose,
    const std::array<float,3>& model_center_of_mass,const std::array<float,3>& local_point,
    const SuspensionParameters& parameters,const std::array<SuspensionWheelState,4>& wheels,
    std::size_t selected_wheel);
}
