#pragma once
#include "tm2020/recovered_vehicle.hpp"
#include "tm2020/recovered_mesh.hpp"
namespace tm2020::recovered {
struct VehicleCurveView {std::span<const CurvePoint> points;std::uint32_t flags{};};
struct WheelKinematicState {
    float length{},speed{},pending_compression{},spin_rate_1c{};
    std::array<float,3> normal_44{};
    float phase_78{},angle_7c{},target_angle_80{};
    std::uint32_t contact_word_34{};
    std::uint8_t material_40{};
};
struct WheelKinematicParameters {
    std::uint32_t suspension_mode_238{};
    float rest_length_244{},pose_offset_250{},relaxation_258{};
    float reference_cd4{},angle_limit_118c{},angle_rate_1190{};
    bool material_parameters_1a48{},remap_material14_to0{};
    VehicleCurveView angle_curve_19f8;
};
struct WheelSteeringMaterial {float angle_rate_4c{};VehicleCurveView angle_curve_d8;};
struct WheelKinematicInput {
    std::array<float,3> model_local_point{};
    bool model_word_4{};
    // Internal steering-angle scalar at native offset +0x1430; raw-input
    // quantization and conversion are outside this recovered kernel.
    float steering_1430{},blend_1c3c{},blend_1c44{},speed_parameter{};
};
// Full physical arithmetic of 0x844130: phase wrap, normal normalization,
// angle selection/slew, and suspension modes 2/3 length/speed/pose updates.
// Phase wraps at the ORIGINAL stored-unit period 1608.4954833984375, not 2*pi.
// The +0x1a08 test is the count of angle_curve_19f8, not an independent flag.
// Modes other than 2/3 retain the caller's wheel pose. Rendering-cache copies
// at the native tail are caller-owned; the resulting pose is returned directly.
// Explicit tuning/material curves; this does not perform wheel collision queries
// or implement the complete tire/drive force generator. Transactional on error.
void update_wheel_kinematics(WheelKinematicState& state,MeshTransform& wheel_pose,
    const WheelKinematicInput& input,const WheelKinematicParameters& parameters,
    std::span<const WheelSteeringMaterial> materials,float interval);
struct WheelSpinParameters {float drive_d90{},brake_d94{},blend_d98{},special_spin_1ef4{};};
struct WheelSpinInput {
    float speed_parameter{};
    // In the 0x843190 wheel-spin argument record, +0x98 behaves as a
    // drive-like scalar and +0x9c as a brake-like scalar. Other record types
    // reuse these offsets for different values; raw control mapping is unknown.
    float scalar_98{},scalar_9c{};
    float blend_1c3c{},blend_1c40{},model_radius_8{};
    bool model_word_4{},override_14b8{};
    std::uint32_t state_word_176c{},state_word_1370{},future_tick_13a0{0xffffffffu},tick{};
};
// Full 0x843190: update only spin_rate_1c using native airborne/contact,
// material IDs 74/3/21, scalar, raw-state and uint32 timer branches. This runs
// before 0x844130 in the engine. Radius >0; the active blend denominator
// 1.0000100135803223 - blend_d98 must be nonzero. No tire force is inferred.
void update_wheel_spin(WheelKinematicState& state,const WheelSpinInput& input,
    const WheelSpinParameters& parameters,float interval);
}
