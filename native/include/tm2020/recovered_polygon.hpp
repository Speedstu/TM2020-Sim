#pragma once
#include "tm2020/recovered_convex.hpp"
#include <vector>
namespace tm2020::recovered {
struct ContactPlane {ConvexVector normal{};float constant{};};
enum class PlaneSide:std::uint32_t {positive=0,negative=1,on_plane=2};
// 0x1cc390: +/-1e-4 classification, inclusive on-plane band.
PlaneSide classify_point(const ConvexVector& point,const ContactPlane& plane);
struct PolygonSplit {std::vector<ConvexVector> positive,negative;};
// 0x1cc3e0: native polygon split, including order/duplicate boundary vertices.
// Crossing segments whose intersection denominator has abs<=1e-5 are rejected:
// that original branch can append uninitialized stack data, not stable geometry.
// This guard defines the SDK's deterministic domain; it is not a game behavior.
PolygonSplit split_polygon(std::span<const ConvexVector> polygon,const ContactPlane& plane);
// 0x1cca10: clip an incident face against the transformed reference face's edge
// planes, retain its positive sides, then keep points on/behind its face plane.
// Ordered convex face loops; transform is row-major R[9], translation[3].
// Normal orientation corresponds to the native face's +0x14 flag.
// Same deterministic intersection domain as split_polygon; owned output.
// Preserves the native ping-pong buffers' stale-content behavior after an empty
// intermediate split. Do not substitute generic mathematical polygon clipping.
std::vector<ConvexVector> face_contacts(std::span<const ConvexVector> incident,
    std::span<const ConvexVector> reference,const ConvexVector& reference_normal,
    const std::array<float,12>& transform,bool keep_normal=true);
}
