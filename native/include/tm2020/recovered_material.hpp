#pragma once
#include <array>
#include <cstdint>
namespace tm2020::recovered {
struct SurfaceMaterial {float impact_friction{1},restitution{.5f};};
// Constructor defaults from the original initialization slice, not a claim
// that live race configuration cannot change. Raw IDs only, no inferred names.
struct SurfaceMaterialTable {
    std::array<SurfaceMaterial,80> values;
    SurfaceMaterialTable();
};
struct SurfaceObject {std::uint32_t class_id{},vehicle_variant{};std::uint8_t category{};};
struct SurfaceResponse {float friction{},restitution{};};
struct SurfaceResponseParameters {
    float default_friction{.5f},vehicle_pair_friction{},vehicle_pair_restitution{.25f};
    float dynamic_class_friction{1},special_a_friction{.1f};
};
// 0x4eff20: positive-positive product; one nonpositive value wins; both
// nonpositive values add. Signed-zero behavior follows the native branches.
float combine_restitution(float a,float b);
// Full 0x7bf0d0 arithmetic. runtime_class_id is the initialized dynamic class
// identifier returned by 0x7d7cb0, supplied explicitly rather than guessed.
// Material IDs are masked to their low byte, as in the original routine.
SurfaceResponse surface_response(const SurfaceMaterialTable& table,std::uint16_t material_a,
    std::uint16_t material_b,const SurfaceObject& a,const SurfaceObject& b,
    std::uint32_t runtime_class_id,const SurfaceResponseParameters& parameters={});
}
