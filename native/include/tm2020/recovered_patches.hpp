#pragma once
#include "tm2020/recovered_convex_collision.hpp"
#include "tm2020/recovered_material.hpp"
namespace tm2020::recovered {
struct ContactPatchPoint {ConvexVector world_point{};float separation{};};
static_assert(sizeof(ContactPatchPoint)==16);
struct ContactPatch {
    ConvexVector normal{};
    SurfaceResponse response{};
    std::vector<ContactPatchPoint> points;
    bool first_chunk{};
};
// Complete arithmetic/order of 0x804a10. Native geometry's defined 40-byte
// fields are supplied using ConvexContact (sphere contacts can copy these
// corresponding fields). Patches combine runs with matching low material
// bytes and normal dot >= 0.999, preserving native linked-run point order.
// Input is divided into independent chunks of at most 255 contacts. Separation
// is sqrt((penX^2+penY^2)+penZ^2), not a normal projection. Owned results replace
// native allocator/container and object-pointer metadata. Inputs explicitly
// supply material table, object descriptors and initialized runtime class ID.
std::vector<ContactPatch> build_contact_patches(std::span<const ConvexContact> geometry,
    const SurfaceMaterialTable& materials,const SurfaceObject& object_a,const SurfaceObject& object_b,
    std::uint32_t runtime_class_id,const SurfaceResponseParameters& parameters={});
}
