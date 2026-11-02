#pragma once
#include <array>
#include <cstdint>
namespace tm2020::recovered {
struct Sphere {std::array<float,3> center{};float radius{};std::uint16_t surface_id{};};
struct SphereContact {
    std::array<float,3> penetration_vector{},normal{},surface_point_a{};
    std::uint16_t surface_id_a{},surface_id_b{};
    std::uint32_t flags{};
};
// Full sphere/sphere geometry arithmetic 0x1a17f0 with caller-owned output.
// Tangency is NOT an overlap. At distance <=1e-5, the original's fallback
// penetration uses radius B alone, fixed normal (0,-1,0), and A's center.
// Existing flags are preserved in that fallback; otherwise bits 0/1 clear.
// Returns false without modifying output when separated. No material response
// coefficients or Stadium chassis geometry are inferred by this primitive.
bool collide_spheres(const Sphere& a,const Sphere& b,SphereContact& output);
}
