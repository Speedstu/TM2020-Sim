#pragma once
#include "tm2020/recovered_position.hpp"
#include "tm2020/recovered_joints.hpp"
namespace tm2020::recovered {
struct ProjectionPositionConstraint {
    std::uint32_t body_a{},body_b{fixed_constraint_body};
    float projection_limit{};
    std::array<float,3> world_point{},direction{};
};
struct AnchoredPositionConstraint {
    std::uint32_t body_a{},body_b{fixed_constraint_body};
    std::array<float,3> local_a{},local_b{};
    float projection_target{};
    std::array<float,3> world_point{},direction{};
};
struct QuaternionAxisConstraint {
    std::uint32_t body{},opaque_4{};
    std::array<float,3> axis{};
    std::uint32_t opaque_14{};
    std::array<float,4> reference{};
};
static_assert(sizeof(ProjectionPositionConstraint)==36&&sizeof(AnchoredPositionConstraint)==60&&sizeof(QuaternionAxisConstraint)==40);
static_assert(offsetof(QuaternionAxisConstraint,reference)==0x18);
// Complete 0x1955c0 arithmetic, without assuming a normalized quaternion.
// Quaternion components are bounded by 16, vector components by 1e6.
void rotate_vector_quaternion(std::array<float,3>& vector,const std::array<float,4>& quaternion);
// Complete 0x7f63f0: apply only negative projection error; fixed B gets the
// full translation, two bodies get equal half corrections. No mass weighting.
void solve_projection_positions(std::span<RigidState> states,std::span<const ProjectionPositionConstraint> constraints);
// Complete 0x7f6590: transform A's local anchor AFTER multiplying by 0.95,
// transform B normally, project relative to the supplied world point, apply
// bilateral error. Native two-body correction multiplier is 0.1, not 0.5.
void solve_anchor_positions(std::span<RigidState> states,std::span<const AnchoredPositionConstraint> constraints);
// Complete 0x7f6a50: relative quaternion/rotated-axis projection, native
// normalization/fallback/sign selection, then reference-quaternion product.
// Preserves the state's rotation MATRIX exactly, as the original does.
// Reference quaternion and axis components <=16; fixed-body sentinel skips.
void solve_quaternion_axes(std::span<RigidState> states,std::span<const QuaternionAxisConstraint> constraints);
struct PositionIsland {
    std::vector<QuaternionAxisConstraint> dynamic_orientation,static_orientation; // +0x100/+0x80
    std::vector<AnchoredPositionConstraint> dynamic_anchors,static_anchors;       // +0x110/+0x70
    std::vector<ProjectionPositionConstraint> dynamic_projection,static_projection; // +0x90/+0x00
    std::vector<DynamicPositionConstraint> dynamic_contacts; // +0xf0
    std::vector<StaticPositionConstraint> static_contacts;   // +0x60
};
// Scheduling arithmetic inside 0x8025a0, bounded loop 0x8033b2..0x80359a.
// All eight original passes run in the listed order per island per iteration.
// Contact rotation corrections retain the existing scalar trig domain limit.
// This is NOT the full outer physics step or adaptive contact reevaluation.
void solve_position_islands(std::span<RigidState> states,std::span<const VelocityCoefficients> coefficients,
    std::span<const PositionIsland> islands,std::uint32_t iterations,const PositionParameters& parameters,PositionMathPath math=PositionMathPath::scalar_sse2);
}
