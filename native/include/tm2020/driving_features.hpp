#pragma once
#include "tm2020.hpp"
#include <array>
namespace tm2020 {
inline constexpr const char* driving_observation_schema="tm2020_reference_local_xz_10_30_60_speed_ground_v1";
// Route comes exclusively from a separate demonstration. No target-frame
// future pose, current target steering, or recorded timestamp enters features.
std::array<double,8> driving_features(const RoutePlan& route,const State& current);
}
