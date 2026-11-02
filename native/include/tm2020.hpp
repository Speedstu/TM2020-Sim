#pragma once
// Trackmania 2020 native research SDK (C++20).
// Reads measured replays and map layouts. Does not simulate game physics.
#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace tm2020 {
struct Vec3 { double x{},y{},z{}; };
struct Quaternion { double x{},y{},z{},w{}; };
struct Controls {double steer{},gas{},brake{};};
struct State {
    std::int32_t time_ms{};
    Vec3 position{};
    Quaternion rotation{};
    Vec3 velocity{};
    double speed_kmh{}, yaw_rad{}, side_speed{};
    Controls controls{};
    std::array<std::uint8_t,4> contact_materials{};
    bool ground_contact{};
};
struct InputEvent {
    std::int32_t time_ms{};
    // Exact raw stream uses -32768 = unchanged/unreported for steering.
    std::int16_t steer_raw{-32768};
    // -1 = unchanged/unreported, 0 = released, 1 = pressed.
    std::int8_t gas{-1},brake{-1},respawn{-1};
};
struct InputCommand {
    // Last known event state at a given recorded timestamp (zero-order hold).
    std::int16_t steer_raw{};
    bool gas{},brake{},respawn{};
};
struct Block {
    std::string name;
    std::array<std::int32_t,3> grid{};
    std::string direction;
    bool is_ground{},is_free{},has_position{},has_rotation{};
    Vec3 position{};
    Vec3 yaw_pitch_roll{};
};
struct Item {
    std::string model;
    Vec3 position{},yaw_pitch_roll{};
};
enum class CourseMarkerKind : std::uint8_t { Start, Checkpoint, Finish };
struct CourseMarker {
    CourseMarkerKind kind{};
    Vec3 position{};
    std::string source_model;
    bool altitude_from_authoritative_item{};
    bool from_anchored_item{};
};
struct Map {
    std::string uid,name;
    std::vector<Block> blocks;
    std::vector<Item> items;
    static Map load(const std::filesystem::path& path);
    // Geometry-independent course markers; no path order or collision claims.
    std::vector<CourseMarker> course_markers() const;
    bool exact_native_collisions_available() const noexcept {return false;}
};
struct Replay {
    std::string uid,name;
    std::int32_t finish_ms{};
    std::int32_t sampling_interval_ms{};
    std::vector<State> states;
    std::vector<InputEvent> changes;
    std::vector<InputCommand> input_prefix;
    static Replay load(const std::filesystem::path& path);
    // ZOH lookup of *recorded* state at <= t, not a simulated future state.
    const State& recorded_at(std::int32_t time_ms) const;
    InputCommand input_at(std::int32_t time_ms) const;
    // Excludes vehicle samples from after finish and inter-sample discontinuities.
    std::size_t in_race_transitions() const;
    bool supports_counterfactual_physics_step() const noexcept {return false;}
};

// A 250ms FUTURE waypoint is required. That waypoint comes from an offline
// replay in current tests; a real driving bot needs a separate planner.
using BCFeatures = std::array<double,24>;
BCFeatures bc_features(const State& now,const State& future);
class BCPolicy {
public:
    static BCPolicy load(const std::filesystem::path& checkpoint);
    Controls predict(const State& now,const State& desired_future) const;
private:
    std::array<double,24> mean_{};
    std::array<double,24> stddev_{};
    std::array<std::array<double,3>,24> weights_{};
};


// REFERENCE ROUTE: generated from a recorded replay. This is NOT a native
// Trackmania road collider, nor a planner for arbitrary unseen maps.
// No Openplanet/game process interaction is necessary.
struct RouteTarget {
    Vec3 waypoint{};
    double yaw_rad{}, target_speed_kmh{};
    double distance_ahead_m{}, lateral_error_m{};
    std::size_t nearest_sample{}, target_sample{};
    bool segment_end{};
};
class RoutePlan {
public:
    explicit RoutePlan(const Replay& demonstration);
    std::size_t waypoint_count() const noexcept{return nodes_.size();}
    std::size_t segment_count() const noexcept{return segment_count_;}
    // Pick nearby replay waypoint, penalizing opposite travel direction.
    // A valid point ahead never crosses a teleport/respawn discontinuity.
    RouteTarget target(Vec3 car_position,double car_yaw,double lookahead_m) const;
    // A planner-produced pseudo-future State used solely for offline policy inputs.
    State as_desired_future(const State& current,double lookahead_m) const;
private:
    struct Node {
        Vec3 pos{};
        double heading{},speed_kmh{},distance{};
        std::size_t segment_id{};
    };
    struct KDNode {
        std::size_t sample{};
        int left{-1}, right{-1};
        Vec3 min{},max{};
    };
    int build_index(std::vector<std::size_t>& order,std::size_t begin,std::size_t end,int depth);
    void search_index(int node,Vec3 query,double yaw,
                      double& best,std::size_t& best_sample) const;
    std::vector<Node> nodes_;
    std::vector<KDNode> index_;
    int index_root_{-1};
    std::size_t segment_count_{};
};

class Dataset {
public:
    Dataset(Map layout, Replay observed);
    const Map& map() const noexcept{return map_;}
    const Replay& replay() const noexcept{return replay_;}
    const State& recorded_at(std::int32_t time_ms) const{return replay_.recorded_at(time_ms);}
private:
    Map map_;
    Replay replay_;
};

// Precise input analog conversion seen in held-out Trackmania 2020 TAS replays.
// A game input implementation needs its own tick-resolution validation.
double analog_steer_from_raw(std::int16_t raw);
// Live InputSteer uses signed seven-bit normalization (neutral raw 0 -> 0).
// analog_steer_from_raw above preserves GBX packed-state label semantics;
// that representation has a half-bin bias and must not define an actuator.
double live_steer_from_raw(std::int16_t raw);

extern "C" {
    // C++ BVH shared-library ABI (built in same repo).
    void* tm_world_open(const char* obj_path) noexcept;
    void tm_world_close(void* handle) noexcept;
    const char* tm_last_error() noexcept;
    long long tm_world_triangle_count(const void* handle) noexcept;
    int tm_world_cast_batch(const void* handle, const double* rays_nx7,
                            long long n, double* results_nx9) noexcept;
}
class CollisionWorld {
public:
    explicit CollisionWorld(const std::filesystem::path& obj_path);
    ~CollisionWorld();
    CollisionWorld(const CollisionWorld&)=delete;
    CollisionWorld& operator=(const CollisionWorld&)=delete;
    CollisionWorld(CollisionWorld&& other) noexcept;
    CollisionWorld& operator=(CollisionWorld&& other) noexcept;
    std::size_t triangle_count() const noexcept;
    // Batched rays double[N][7] => double[N][9]; OBJ and .tmcol geometry supported.
    void raycast(const double* rays, std::size_t count, double* out) const;
private:
    void* handle_{};
};
}
