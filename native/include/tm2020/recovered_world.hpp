#pragma once
#include "tm2020/recovered_patches.hpp"
#include "tm2020/recovered_position.hpp"
#include "tm2020/recovered_solver.hpp"
#include "tm2020/recovered_frames.hpp"
#include "tm2020/recovered_joint_position.hpp"
#include <memory>
namespace tm2020::recovered {
struct RigidMeshConfiguration {
    BodyParameters model;
    std::array<float,3> model_center{};
    VelocityStepParameters velocity;
    GravityEnvironment environment;
    ContactSolverIterations velocity_iterations;
    PositionParameters position;
    PositionMathPath position_math{PositionMathPath::scalar_sse2};
    std::uint32_t position_iterations{};
    float restitution_speed_threshold{};
    SurfaceMaterialTable materials;
    SurfaceObject body_object,mesh_object;
    std::uint32_t runtime_class_id{};
    SurfaceResponseParameters surface_parameters;
    std::uint16_t body_surface_id{};
};
struct RigidMeshStepReport {std::uint64_t tick{};std::size_t contacts{},patches{},normal_constraints{},friction_axes{};};
class RigidMeshWorld;
struct RigidMeshSnapshot {
    RigidState state;
    AuxiliaryOutput auxiliary{};
    std::uint64_t tick{};
private:
    friend class RigidMeshWorld;
    std::shared_ptr<const std::byte> identity;
};
// Autonomous single-convex-body/static-mesh runner composed of recovered
// kernels. Owns geometry and settings; needs no game, original instructions,
// Python or DLL injection. Configuration is EXPLICIT, not inferred race tuning.
// Forces -> center-frame shift -> collision/patches -> contact velocity solve
// -> full-interval pose -> native position pass order -> model-origin shift.
// External states/snapshots use the model-origin frame. No adaptive CCD, sleeping, general
// joints or tire-force generator: this is not a complete Trackmania car world.
// Every step stages state/force changes; rejected geometry/math leaves it intact.
class RigidMeshWorld {
public:
    RigidMeshWorld(const ConvexTopologyView& body,const AabbPrimitive& local_bounds,
        std::span<const ConvexVector> mesh_vertices,std::span<const IndexedTriangle> mesh_triangles,
        const MeshTransform& mesh_transform,const RigidMeshConfiguration& configuration);
    RigidMeshWorld(const RigidMeshWorld&)=delete;
    RigidMeshWorld& operator=(const RigidMeshWorld&)=delete;
    RigidMeshWorld(RigidMeshWorld&&)=delete;
    void reset(const RigidState& state);
    RigidMeshStepReport step(float interval,ForceAccumulator& forces);
    RigidMeshSnapshot snapshot()const;
    // In-memory snapshots are bound to this world's immutable geometry/settings.
    void restore(const RigidMeshSnapshot& snapshot);
    const RigidState& state()const noexcept{return state_;}
    std::uint64_t tick()const noexcept{return tick_;}
private:
    std::vector<ConvexVector> body_vertices_,body_normals_,body_directions_,mesh_vertices_;
    std::vector<std::vector<std::uint32_t>> face_indices_;
    std::vector<ConvexFace> faces_;
    std::vector<ConvexEdge> edges_;
    std::vector<CookedTriangle> mesh_triangles_;
    std::vector<AabbNode> mesh_tree_;
    AabbPrimitive bounds_;
    MeshTransform mesh_transform_;
    RigidMeshConfiguration configuration_;
    RigidState state_;
    AuxiliaryOutput auxiliary_{};
    std::uint64_t tick_{};
    std::shared_ptr<const std::byte> identity_{std::make_shared<const std::byte>()};
    ConvexTopologyView body()const;
    void validate_state(const RigidState& state)const;
};
}
