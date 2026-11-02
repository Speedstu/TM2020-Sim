#pragma once
#include "tm2020/recovered_collision.hpp"
#include <span>
#include <vector>
namespace tm2020::recovered {
// Packed runtime geometry consumed by 0x1af710. Building/cooking this data
// from game assets is a separate stage; these declarations preserve its layout.
struct CookedTriangle {
    std::array<float,3> normal{};
    float plane_constant{};
    std::array<std::uint32_t,3> vertices{};
    std::uint16_t surface_id{},reserved{};
};
struct AabbNode {
    std::array<float,3> center{},half_extent{};
    // bit 0: leaf. Leaf payload = triangle index; internal payload = number
    // of preorder nodes to skip when this subtree's AABB does not overlap.
    std::uint32_t packed{};
};
static_assert(sizeof(CookedTriangle)==0x20&&sizeof(AabbNode)==0x1c);
struct IndexedTriangle {
    std::array<std::uint32_t,3> vertices{};
    std::uint16_t surface_id{},reserved{};
};
static_assert(sizeof(IndexedTriangle)==0x10);
struct AabbPrimitive {
    std::array<float,3> center{},half_extent{};
    std::uint32_t index{};
};
static_assert(sizeof(AabbPrimitive)==0x1c);
// Arithmetic from GmSurfMesh_ComputeCookedTris (0x1adb10). Includes its
// 1e-20 squared-normal normalization gate and sequential plane-constant order.
// Owned result buffers initialize the unused/reserved output word to zero.
std::vector<CookedTriangle> cook_triangles(std::span<const std::array<float,3>> vertices,
    std::span<const IndexedTriangle> triangles);
// Triangle-bound arithmetic inside 0x1ae360, followed by the native recursive
// tree algorithm (0x19fad0 and helpers). Partitions by center variance, retains
// the original strict mean split and fallback, and emits native preorder.
// Game mesh construction passes leaf_width=2. No native allocation is reused.
std::vector<AabbPrimitive> triangle_aabbs(std::span<const std::array<float,3>> vertices,
    std::span<const IndexedTriangle> triangles);
std::vector<AabbNode> build_aabb_tree(std::span<const AabbPrimitive> primitives,std::uint32_t leaf_width=2);
struct MeshTransform {
    std::array<float,9> rotation{1,0,0,0,1,0,0,0,1};
    std::array<float,3> translation{};
};
struct CookedMeshView {
    std::span<const std::array<float,3>> vertices;
    std::span<const CookedTriangle> triangles;
    std::span<const AabbNode> tree;
    MeshTransform transform{};
};
struct MeshContact {
    SphereContact geometry{};
    std::array<float,3> triangle_normal{},surface_point_b{};
    std::uint32_t triangle_index{};
};
// Recovered traversal 0x1a01b0. Result contains leaf NODE indices in native
// preorder. Closed AABB overlap, no sorting or duplicate removal.
std::vector<std::uint32_t> query_aabb_tree(std::span<const AabbNode> nodes,
    const std::array<float,3>& center,const std::array<float,3>& half_extent);
// Complete sphere/cooked-mesh arithmetic 0x1af710, including face/edge/vertex
// branches and native per-triangle emission order. Caller supplies cooked data.
// Flags bit 0 marks a face case; bit 1 is set on every emitted mesh contact.
// This does not implement convex/mesh or recover Stadium chassis/track assets.
std::vector<MeshContact> collide_sphere_mesh(const Sphere& sphere,const CookedMeshView& mesh,
    std::uint32_t initial_flags=0);
}
