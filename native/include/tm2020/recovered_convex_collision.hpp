#pragma once
#include "tm2020/recovered_features.hpp"
#include "tm2020/recovered_mesh.hpp"
namespace tm2020::recovered {
struct ConvexInstance {ConvexTopologyView shape;MeshTransform transform{};std::uint16_t surface_id{};};
struct ConvexContact {
    ConvexVector penetration_vector{},normal{},world_point{};
    std::uint16_t surface_id_a{},surface_id_b{};
};
static_assert(sizeof(ConvexContact)==40);
struct ConvexCollision {
    bool overlap{};std::uint8_t witness_kind{};
    std::vector<ConvexContact> contacts;
};
// Arithmetic of complete convex/convex handler 0x19cec0. Ordered closed convex
// topology, rigid transforms, unit face/edge directions; same deterministic
// polygon and finite edge-pair domains as the underlying recovered kernels.
// World point is the native selected incident-face point or edge midpoint.
// Native undefined record bytes are not exposed. Boolean queries can suppress
// emission. Runtime scratch allocation/TLS bookkeeping is outside SDK ownership.
ConvexCollision collide_convex(const ConvexInstance& a,const ConvexInstance& b,bool generate_contacts=true);
struct ConvexMeshCollision {bool overlap{};std::vector<ConvexContact> contacts;};
// Complete 0x1b4410 arithmetic in the same deterministic clipping/edge domains.
// Caller supplies the model-local broadphase AABB used by the engine.
// Original candidate collection is capped at 128 overlapping triangles.
ConvexMeshCollision collide_convex_mesh(const ConvexInstance& convex,const CookedMeshView& mesh,
    const AabbPrimitive& local_bounds,bool generate_contacts=true);
}
