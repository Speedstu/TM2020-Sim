#pragma once
// Windows-only read-only TM2020 process observation. C++20; NO game injection.
// These are short-lived inferred numeric pose copies, NOT verified physics.
// Only use with current PID+process creation+exact executable hash manifest.
#include "tm2020.hpp"
#include "tm2020/visual_state.hpp"
#include <cstdint>
#include <filesystem>
#include <memory>
#include <optional>
namespace tm2020::live {
std::string file_sha256(const std::filesystem::path& file);
struct NumericPoseCandidate {
    Vec3 xyz{};
    // The 4 float fields 16 bytes before XYZ look like a unit quaternion.
    // Raw ordering and physical-chassis semantics remain unverified.
    std::optional<Quaternion> raw_quaternion_candidate;
    std::uint32_t position_agreeing_copies{};
    std::uint32_t orientation_agreeing_copies{};
    std::uint32_t readable_copies{};
    bool authoritative_physics_state_verified{false};
    bool authoritative_100hz_tick_verified{false};
    bool vehicle_owner_verified{false};
};
class ReadOnlyObserver {
public:
    explicit ReadOnlyObserver(const std::filesystem::path& session_manifest_v3,double position_consensus_radius_m=.5);
    ~ReadOnlyObserver();
    ReadOnlyObserver(const ReadOnlyObserver&)=delete;
    ReadOnlyObserver& operator=(const ReadOnlyObserver&)=delete;
    ReadOnlyObserver(ReadOnlyObserver&&) noexcept;
    ReadOnlyObserver& operator=(ReadOnlyObserver&&) noexcept;
    // No action is sent, and the process memory is never modified.
    // Nullopt means candidate copies no longer agree / are not readable.
    std::optional<NumericPoseCandidate> poll() const;
    std::uint32_t process_id() const noexcept;
    std::size_t source_count() const noexcept;
    // Decodes each hypothesis as a reflected VISUAL state at position-0x50.
    // Returns individual copies so callers can expose disagreements/staleness.
    std::vector<std::optional<ReflectedVisualState>> poll_visual_copies() const;
    // Selects recent reflected copies using observed advancing header word +0xC.
    // The clock is experimentally inferred, not an authoritative engine tick.
    std::optional<FreshVisualSample> poll_fresh_visual(std::optional<Vec3> independent_pose=std::nullopt,
        bool prefer_active_throttle=false) const;
    // Reacquire full reflected buffers near the independently observed car.
    // Intended after a normal local restart; costs a bounded process scan.
    // Keeps the pose sources separate from disposable visual-state buffers.
    std::size_t discover_visual_states(std::size_t max_megabytes=8192,double radius_m=2.,
        std::optional<Vec3> known_start=std::nullopt);
    // Disposable same-process cache. Restore requires current decodability,
    // advancing timestamps and coherent positions; never a persistent owner.
    bool restore_visual_sources(const std::filesystem::path& cache);
    void save_visual_sources(const std::filesystem::path& cache) const;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
}
