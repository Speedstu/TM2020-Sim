#pragma once
// Current-build CSceneVehicleVisState registration, NOT the physics owner.
// Evidence: scripts/reverse_reflection.py -> reflection-current-build.json.
#include "tm2020.hpp"
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
namespace tm2020::live {
inline constexpr char visual_state_build_sha256[]=
    "3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda";
inline constexpr std::size_t visual_state_bytes=0x360;
inline constexpr std::size_t visual_position_offset=0x50;
struct VisualWheel {
    float rotation{},rotation_speed{},steer_angle{},damper_length{},slip{};
    float icing{},tire_wear{},brake_coefficient{};
};
struct ReflectedVisualState {
    std::array<std::uint32_t,4> raw_header_words{}; // semantics unverified
    std::array<float,9> location_rotation_matrix{};
    bool rotation_matrix_is_orthonormal{};
    Vec3 position{},world_velocity{};
    float input_steer{},input_gas{},input_brake{},front_speed{};
    bool input_is_braking{},ground_contact{},engine_on{},turbo{},top_contact{};
    std::int32_t gear{},race_start_time{};
    std::uint8_t discontinuity_count{};
    VisualWheel wheels[4]{};
    // Names and byte offsets are statically corroborated. This representation
    // may be interpolated, stale, or a ghost. No authoritative physics claim.
};
// Portable bounded decoder, independent of Win32 and C++ object packing.
std::optional<ReflectedVisualState> decode_visual_state(std::span<const std::byte> bytes);
struct FreshVisualSample {
    ReflectedVisualState state;
    std::uint32_t clock_candidate_ms{};
    std::uint32_t agreeing_copies{};
    std::uint32_t decodable_copies{};
    bool authoritative_physics{false};
};
// Modular timestamps assume candidates are less than 2^31 ms apart.
// An old throttle-on snapshot cannot shadow newer throttle-off states forever.
// "Fresh" is relative to these copies only: the host must separately verify
// that the chosen clock advances over time before considering data current.
std::optional<FreshVisualSample> select_fresh_visual(
    std::span<const std::optional<ReflectedVisualState>> copies,
    std::optional<Vec3> independent_pose=std::nullopt,bool prefer_active_throttle=false);
}
