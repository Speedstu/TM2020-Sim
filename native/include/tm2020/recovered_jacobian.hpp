#pragma once
#include "tm2020/recovered_contacts.hpp"
#include <cstddef>
namespace tm2020::recovered {
// Native prepared constraint formats. These buffers differ from the compact
// normal-contact formats in recovered_contacts.hpp. No geometry is inferred.
struct DynamicJacobian {
    std::array<float,3> angular_a{},angular_b{},weighted_angular_a{},weighted_angular_b{};
    float inverse_mass_a{},inverse_mass_b{},effective_coefficient{},target{},accumulated_impulse{};
};
struct DynamicJacobianConstraint {
    std::uint32_t body_a{},body_b{};
    std::array<float,3> direction{};
    DynamicJacobian jacobian{};
};
struct DynamicFrictionConstraint {
    DynamicJacobianConstraint constraint{};
    std::uint32_t normal_index{};float friction{};
};
struct StaticJacobianConstraint {
    std::uint32_t body{};
    std::array<float,3> direction{},angular{},weighted_angular{};
    float inverse_mass{},effective_coefficient{},target{},accumulated_impulse{};
};
struct StaticFrictionConstraint {
    StaticJacobianConstraint constraint{};
    std::uint32_t normal_index{};float friction{};
};
static_assert(sizeof(DynamicJacobian)==0x44);
static_assert(sizeof(DynamicJacobianConstraint)==0x58);
static_assert(sizeof(DynamicFrictionConstraint)==0x60);
static_assert(sizeof(StaticJacobianConstraint)==0x38);
static_assert(sizeof(StaticFrictionConstraint)==0x40);
static_assert(offsetof(DynamicJacobianConstraint,jacobian)==0x14);
static_assert(offsetof(StaticJacobianConstraint,accumulated_impulse)==0x34);
// Complete arithmetic initializer 0x85ecd0. Keeps the caller's accumulated
// impulse; computes cross products and the effective coefficient in native
// binary32 evaluation order. Rejects a zero/nonpositive denominator.
void prepare_dynamic_jacobian(DynamicJacobian& result,const VelocityCoefficients& a,
    const VelocityCoefficients& b,const std::array<float,3>& offset_a,
    const std::array<float,3>& offset_b,const std::array<float,3>& direction,float target);
// Each function is ONE sequential sweep. Returns whether any delta was nonzero.
// Friction axes are clamped independently, as in these original procedures;
// this does not substitute a circular friction cone or recover vehicle tires.
bool solve_dynamic_unilateral(std::span<RigidState> states,std::span<DynamicJacobianConstraint> constraints);
bool solve_static_unilateral(std::span<RigidState> states,std::span<StaticJacobianConstraint> constraints);
bool solve_dynamic_friction(std::span<RigidState> states,std::span<DynamicFrictionConstraint> constraints,
    std::span<const DynamicJacobianConstraint> normals);
bool solve_static_friction(std::span<RigidState> states,std::span<StaticFrictionConstraint> constraints,
    std::span<const StaticJacobianConstraint> normals);
struct ContactPoint {
    std::uint32_t body_a{},body_b{};
    std::array<float,3> world_point{},normal{};
    float separation{},friction{},restitution{};
};
struct DynamicPositionConstraint {
    std::uint32_t body_a{},body_b{};
    std::array<float,3> local_a{},local_b{},normal{};
};
struct StaticPositionConstraint {
    std::uint32_t body{};
    std::array<float,3> local_point{},target_point{},normal{};
};
static_assert(sizeof(ContactPoint)==0x2c);
static_assert(sizeof(DynamicPositionConstraint)==0x2c);
static_assert(sizeof(StaticPositionConstraint)==0x28);
struct PreparedDynamicContact {
    DynamicPositionConstraint position{};
    DynamicJacobianConstraint normal{};
    std::array<DynamicFrictionConstraint,2> friction{};
    std::uint32_t friction_count{};
};
struct PreparedStaticContact {
    StaticPositionConstraint position{};
    StaticJacobianConstraint normal{};
    std::array<StaticFrictionConstraint,2> friction{};
    std::uint32_t friction_count{};
};
// Contact-to-constraint arithmetic at 0x85eea0 / 0x85f5b0, including restitution
// and both tangent axes. The collision backend must supply ContactPoint; these
// functions do not discover colliders or compute geometry contact manifolds.
// Native append/allocation containers are replaced with these owned results.
// Negative restitution values are retained native inputs: only values >0
// activate the bounce branch; nonpositive values use ordinary bias behavior.
PreparedDynamicContact prepare_dynamic_contact(const ContactPoint& contact,
    std::span<const RigidState> states,std::span<const VelocityCoefficients> coefficients,
    float interval,float restitution_speed_threshold,std::uint32_t normal_index=0);
PreparedStaticContact prepare_static_contact(const ContactPoint& contact,
    std::span<const RigidState> states,std::span<const VelocityCoefficients> coefficients,
    float interval,float restitution_speed_threshold,std::uint32_t normal_index=0);
}
