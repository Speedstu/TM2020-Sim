#pragma once
// Causal observation ONLY: finite differences of externally observed XYZ.
// This is not Trackmania's internal physics velocity, wheel speed or yaw.
#include "tm2020.hpp"
#include <cstdint>
#include <deque>
namespace tm2020 {
struct PoseEstimate {
    Vec3 position{};
    Vec3 observed_velocity_ms{}; // finite-difference world velocity
    double path_heading_rad{};   // atan2(vz,vx), NOT chassis yaw
    double speed_kmh{};
    double sample_age_ms{};
    bool velocity_observable{};
    bool presumed_teleport{}; // discontinuity heuristic
    int history_count{};
};
enum class VelocityEstimateMethod { TwoPointSecant, WeightedLeastSquares };
class PoseKinematics {
public:
    // Max length for a causal weighted fit in milliseconds.
    explicit PoseKinematics(double max_window_ms=100.0,
                            VelocityEstimateMethod method=VelocityEstimateMethod::TwoPointSecant);
    PoseEstimate observe(double monotonic_time_ms,Vec3 position);
    void reset() noexcept;
    std::size_t samples() const noexcept{return history_.size();}
private:
    struct Sample {double t; Vec3 p;};
    std::deque<Sample> history_;
    double max_window_ms_{};
    VelocityEstimateMethod method_{};
};
}
