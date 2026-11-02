#pragma once
#include "tm2020/recovered_mesh.hpp"
namespace tm2020::recovered {
struct RayTriangleHit {float fraction{1.00001f},u{},v{};};
struct RaySphereHit {
    float fraction{1.00001f};
    std::array<float,3> point{},normal{};
    std::uint16_t material{};
};
// Complete arithmetic path of 0x1a5580 with helper 0x18f410. The sphere may
// move by displacement over the segment; point remains on the original ray.
// The closest-hit limit is strict. Inside/on-surface starts report fraction 0.
// Finite xyz/radius inputs within +/-1e6; radius >=0. Miss preserves outputs.
bool raycast_sphere(const std::array<float,3>& center,float radius,std::uint16_t material,
    const std::array<float,3>& origin,const std::array<float,3>& direction,
    const std::array<float,3>& displacement,std::uint8_t skip_material,RaySphereHit& hit);
// Original 0x1af350, helpers 0x18ba80 and 0x18ca50. Local coordinates;
// direction is the full segment displacement, not a normalized ray direction.
// The two-sided branch compares endpoint distance SIGN BITS, including -0.
// On a miss every output byte is preserved. Native ordered binary32 arithmetic.
// Finite input coordinates/directions/plane values within +/-1e6; no errno path.
bool raycast_cooked_triangle(const std::array<std::array<float,3>,3>& vertices,
    const CookedTriangle& triangle,const std::array<float,3>& origin,
    const std::array<float,3>& direction,bool two_sided,RayTriangleHit& hit);
}
