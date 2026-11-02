#pragma once
#include "tm2020/recovered_contacts.hpp"
namespace tm2020::recovered {
inline constexpr std::uint32_t fixed_constraint_body=0xffffffffu;
// Complete prepared record consumed by 0x7f56d0. Body A must exist; body B
// may be the fixed sentinel. A zero softness selects native unilateral clamp;
// nonzero softness permits a signed accumulated impulse. Values are supplied
// by the caller; this API does not infer joint construction from game assets.
struct PointConstraint {
    std::uint32_t body_a{},body_b{fixed_constraint_body};
    std::array<float,3> world_point_a{},world_point_b{},direction{};
    float bias{},softness{},effective_coefficient{},accumulated_impulse{};
};
// 0x7f5f40. Either body may be fixed. The original angular application uses
// coefficient lane 3 for all axes; the SDK preserves that arithmetic literally.
struct AngularConstraint {
    std::uint32_t body_a{},body_b{fixed_constraint_body};
    std::array<float,3> direction{};
    float bias{},softness{},effective_coefficient{},accumulated_impulse{};
};
// 0x7f67a0. Both bodies must exist. Project angular velocities onto the supplied
// axes, couple their scalar rates and overwrite the full angular vectors only
// when the relative error exceeds the native 0.001 scaled threshold.
struct AngularCouplingConstraint {
    std::uint32_t body_a{},body_b{};
    std::array<float,3> axis_a{},axis_b{},coefficient_weights_a{},coefficient_weights_b{};
    float ratio{};
};
static_assert(sizeof(PointConstraint)==60&&sizeof(AngularConstraint)==36&&sizeof(AngularCouplingConstraint)==60);
// One complete native sweep. Return is max absolute accumulated impulse delta.
// Inputs/outputs are finite and bounded; a late singular coupling or invalid
// index rejects the entire call without changing state or accumulated impulse.
float solve_point_constraints(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<PointConstraint> constraints);
float solve_angular_constraints(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<AngularConstraint> constraints);
void solve_angular_couplings(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,std::span<const AngularCouplingConstraint> constraints);
}
