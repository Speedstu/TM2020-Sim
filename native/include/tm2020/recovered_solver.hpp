#pragma once
#include "tm2020/recovered_jacobian.hpp"
#include "tm2020/recovered_joints.hpp"
namespace tm2020::recovered {
// First three words of the native solver configuration, in native order.
struct ContactSolverIterations {
    std::uint32_t static_friction{},dynamic_friction{},velocity{};
};
// Owned equivalents of the contact-related spans in a native 0x140-byte
// island. General joint/motor/bilateral constraints are outside this API.
struct ContactIsland {
    std::vector<StaticNormalConstraint> static_friction_normals; // native +0x10
    std::vector<StaticNormalConstraint> static_final_normals;    // +0x20
    std::vector<StaticFrictionConstraint> static_friction;       // +0x40
    std::vector<StaticJacobianConstraint> static_normals;        // +0x50
    std::vector<DynamicNormalConstraint> dynamic_friction_normals; // +0xa0
    std::vector<DynamicNormalConstraint> dynamic_final_normals;    // +0xb0
    std::vector<DynamicJacobianConstraint> dynamic_normals;        // +0xd0
    std::vector<DynamicFrictionConstraint> dynamic_friction;       // +0xe0
};
// Complete 0x7f6ec0 scheduling in the domain where the other island constraint
// spans and external constraint list are empty. Friction runs BEFORE that
// iteration's unilateral Jacobian normals; thresholds do not stop the latter.
// Island order and shared-body dependencies are preserved. Owned staging makes
// the complete call transactional. Zero velocity iterations is a no-op.
void solve_contact_islands(std::span<RigidState> states,
    std::span<const VelocityCoefficients> coefficients,
    std::span<ContactIsland> islands,ContactSolverIterations iterations);
struct ConstraintIsland {
    ContactIsland contacts;
    std::vector<PointConstraint> early_points; // native +0xc0
    std::vector<PointConstraint> late_points;  // +0x30
    std::vector<AngularCouplingConstraint> angular_couplings; // +0x120
    std::vector<AngularConstraint> angular_constraints;       // +0x130
};
// Full 0x7f6ec0 arithmetic scheduling with all of its island velocity spans
// available. Only the separate external callback constraint list is empty.
// Joint preparation, position passes and pose/contact reevaluation are separate.
void solve_constraint_islands(std::span<RigidState> states,
    std::span<const VelocityCoefficients> coefficients,
    std::span<ConstraintIsland> islands,ContactSolverIterations iterations);
}
