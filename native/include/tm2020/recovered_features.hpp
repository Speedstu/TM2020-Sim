#pragma once
#include "tm2020/recovered_convex.hpp"
namespace tm2020::recovered {
inline constexpr std::uint32_t no_convex_feature=0xffffffffu;
struct ConvexFace {
    std::uint32_t normal_index{};bool keep_normal{true};
    std::span<const std::uint32_t> vertices;
};
struct ConvexEdge {std::uint32_t vertex_a{},vertex_b{},direction_index{};};
struct ConvexTopologyView {
    ConvexAxesView axes;
    std::span<const ConvexFace> faces;
    std::span<const ConvexEdge> edges;
};
// Complete selection arithmetic, including last-feature wins on score ties.
// 0x1cb980: edges matching a direction group, maximize endpoint projection.
std::uint32_t select_edge(const ConvexTopologyView& shape,std::uint32_t direction_index,const ConvexVector& direction);
// 0x1cbcb0: faces matching a normal group, maximize oriented normal projection.
std::uint32_t select_face_from_normal(const ConvexTopologyView& shape,std::uint32_t normal_index,const ConvexVector& direction);
// 0x1cbef0: maximize over all oriented face normals. Empty sets return the
// no_convex_feature sentinel, as in the native routines.
std::uint32_t select_incident_face(const ConvexTopologyView& shape,const ConvexVector& direction);
struct EdgeFrame {ConvexVector center{},direction{};float half_length{};};
// 0x1cc200: midpoint, direction and half-length; near-degenerate directions
// remain raw and half-length becomes zero, preserving the native behavior.
EdgeFrame edge_frame(const ConvexTopologyView& shape,std::uint32_t edge_index);
struct EdgePairResult {float squared_distance{},parameter_a{},parameter_b{};};
// Full 0x1c9080: exact piecewise segment minimization, including its parallel
// branch and evaluation order. Directions must have squared norm within 2e-4
// of one, half lengths >=0, and their sum >0 (the zero/zero parallel native
// branch divides by zero). Does not fabricate a contact manifold by itself.
EdgePairResult closest_edges(const EdgeFrame& a,const EdgeFrame& b);
}
