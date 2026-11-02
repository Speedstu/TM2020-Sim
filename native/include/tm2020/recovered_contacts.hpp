#pragma once
#include "tm2020/recovered_rigid.hpp"
namespace tm2020::recovered {
// Prepared velocity constraints. Building these from collision geometry is a
// separate engine stage; caller supplies its exact bias/effective coefficient.
using VelocityCoefficients=std::array<float,4>;
struct DynamicNormalConstraint {
    std::uint32_t body_a{},body_b{};
    std::array<float,3> world_point{},normal{};
    float bias{},effective_coefficient{},accumulated_impulse{};
};
struct StaticNormalConstraint {
    std::uint32_t body{};
    std::array<float,3> world_point{},normal{};
    float bias{},effective_coefficient{},accumulated_impulse{};
};
static_assert(sizeof(DynamicNormalConstraint)==0x2c);
static_assert(sizeof(StaticNormalConstraint)==0x28);
// One sequential native solver sweep (not the outer iteration scheduler).
// Returns the largest absolute change in accumulated impulse. All inputs are
// validated before commit; invalid or overflowing batches leave state intact.
float solve_dynamic_normals(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<DynamicNormalConstraint> constraints);
float solve_static_normals(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<StaticNormalConstraint> constraints);
// The original pose scheduler's *selection math*. Contacts are recomputed
// between fractions in the engine; this selector alone does not implement CCD.
float select_pose_fraction(const std::array<float,3>& velocity,float displacement_limit,float interval);
inline constexpr float pose_remainder_cutoff=9.999999747378752e-6f;
struct SuspensionWheelState {float length{},speed{};bool contact{};};
struct SuspensionParameters {
    std::uint32_t mode{};bool require_all_contacts{};
    float stiffness{},damping{},rest_length{};
};
// Conditional spring/damper branch at 0x844090. Returns false when the native
// branch makes no force call. Other suspension modes are NOT inferred here.
bool suspension_mode2(const SuspensionParameters& parameters,const std::array<SuspensionWheelState,4>& wheels,
    std::size_t selected_wheel,float& local_vertical_force);
}
