#pragma once
// Offline advisory track-following controller. No game action or physics.
// Requires measured vehicle yaw and a reference replay of the SAME map.
#include "tm2020.hpp"
namespace tm2020 {
struct PurePursuitConfig {
    double lookahead_m{24.0};    // Distance along reference replay route
    double heading_gain{1.0};   // Steer gain per radian, calibrated separately
};
Controls propose_reference_controls(
    const RoutePlan& reference, const State& observed,
    const PurePursuitConfig& parameters);
struct ReferenceTrackingConfig {
    double heading_gain{-3.},lateral_gain{.15};
    std::size_t smoothing_radius{2};
    bool scale_feedforward_with_speed{true};
};
// Route must have been constructed from this same reference replay.
// Demonstration feedforward + measured pose feedback; not a physics model.
Controls propose_tracking_controls(const Replay& replay,const RoutePlan& route,
    const State& observed,const ReferenceTrackingConfig& parameters={});
}
