#pragma once
#include "tm2020/recovered_vehicle.hpp"
#include "tm2020/recovered_wheel.hpp"
namespace tm2020::recovered {
struct FastSinCos {float sine{},cosine{};};
// Complete 0x18ce30 polynomial and binary32 range reduction, |angle| <= 1e6.
// Distinct from the scalar runtime trig used by contact rotation correction.
FastSinCos fast_sin_cos(float angle);
struct DirectionFactorParameters {std::uint32_t recovery_duration_324{};float minimum_328{};};
// Complete 0x84f1a0; raw verified fields keep their offsets. Positive recovery
// duration, |interval|<=1, quaternion components<=16; staged factor update.
void update_direction_factor(float& factor_14bc,const std::array<float,4>& quaternion,
    const std::array<float,3>& velocity_12fc,float scalar_98,const DirectionFactorParameters&,float interval);
struct VerticalResponseParameters {float begin_19e4{},end_19e8{},begin_19ec{},end_19f0{};};
// Complete 0x8456b0, thresholds 0<=begin<end<=1. Each response uses the
// original fast cosine of the normalized absolute vertical velocity ratio.
std::array<float,2> vertical_response(const std::array<float,3>& velocity,const VerticalResponseParameters&);
struct WheelSurfaceParameters {
    std::array<float,10> values_18_3c{};
    std::uint32_t word_40{};
    std::array<float,3> values_44_4c{};
    std::uint32_t flags_50{};
    VehicleCurveView curve_128,curve_88,curve_178,curve_1c8;
};
struct WheelMaterialContact {std::uint32_t contact_34{};std::uint8_t material_40{};std::array<float,3> normal_44{};};
struct SurfaceBlendValues {
    std::array<float,10> values_00_24{};
    std::uint32_t word_28{};
    std::array<float,3> values_2c_34{};
    std::uint32_t flags_38{};
};
static_assert(sizeof(SurfaceBlendValues)==60);
struct WheelSurfaceBlend {
    SurfaceBlendValues values;
    std::array<float,4> curve_response{};
    std::array<float,3> transformed_normal{};
    std::uint32_t has_contact{},last_contact_kind{};
};
// Complete 0x845b60 INCLUDING 0x845880 four-curve aggregation. Typed integer
// lanes preserve native rounding, flags and last-contact-wins classification.
// Four wheels, material IDs 0..79, word_40<=1e6, finite values bounded by 1e6.
// Curves/tuning are explicit caller data, not verified effective race values.
WheelSurfaceBlend blend_wheel_surfaces(const std::array<WheelMaterialContact,4>& wheels,
    std::span<const WheelSurfaceParameters> materials,const RigidState& state,
    const std::array<float,3>& curve_velocity,float scalar_13a4,bool classify_15a8,bool remap_14);
}
