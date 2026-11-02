#pragma once
#include <array>
#include <cstdint>
#include <span>
namespace tm2020::recovered {
using ConvexVector=std::array<float,3>;
struct ProjectionInterval {float minimum{},maximum{};};
// Original projection reduction 0x1cab20, including Y+X+Z and SSE min/max ties.
ProjectionInterval project_vertices(std::span<const ConvexVector> vertices,const ConvexVector& axis);
struct ConvexAxesView {
    std::span<const ConvexVector> vertices,face_normals,edge_directions;
};
struct SeparatingAxisResult {
    bool overlap{},has_witness{};
    float depth{};
    ConvexVector normal{};
    // Native feature bytes: 0 = A face normal, 1 = B face normal,
    // 2 = cross(A edge direction,B edge direction). index_b applies only to 2.
    std::uint8_t kind{},index_a{},index_b{};
};
// Original SAT 0x1cae40 / 0x1cad10. Inputs must share the same coordinate frame.
// Margin expands A's projection interval. Cross-edge axes have the original
// 1e-4 witness-selection bias. This identifies overlap/axis; generating the
// convex contact manifold and gathering topology remain separate stages.
// On separation, depth/witness describe only axes visited before the early exit.
// With no usable axes, the original returns overlap with depth=FLT_MAX and no
// witness; this is retained, rather than claiming a geometric collision proof.
SeparatingAxisResult separating_axes(const ConvexAxesView& a,const ConvexAxesView& b,float margin=0);
}
