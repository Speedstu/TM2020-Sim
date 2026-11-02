#pragma once
// EXPERIMENTAL 100Hz DEVELOPMENT SANDBOX ONLY.
// Does NOT reproduce Trackmania 2020 physics, collision, suspension or tires.
// Flat unbounded horizontal plane with illustrative kinematics.
// Do NOT train/deploy a Trackmania bot assuming this model is faithful.
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>

namespace tm2020::experimental {
inline constexpr bool faithful_trackmania_physics=false;
inline constexpr double timestep_s=0.01;
struct Action {
    float steer{},gas{},brake{};
};
struct Pose {
    double x{},y{},z{},yaw{},speed_ms{};
};
struct Snapshot {
    std::uint64_t tick{};
    std::vector<Pose> states;
};
class Sandbox {
public:
    explicit Sandbox(std::size_t n);
    std::size_t size()const noexcept{return states_.size();}
    std::uint64_t tick()const noexcept{return tick_;}
    void reset(const std::vector<Pose>& initial);
    Snapshot snapshot()const;
    void restore(const Snapshot& state);
    void step(std::span<const Action> action);
    const std::vector<Pose>& states()const noexcept{return states_;}
private:
    std::vector<Pose> states_;
    std::uint64_t tick_{};
};
} // tm2020::experimental
