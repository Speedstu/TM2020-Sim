#pragma once
// Port of the SHA-pinned build's post-force rigid pose integration kernels.
// These kernels alone do NOT include vehicle forces, gravity, tire/suspension
// contacts, collision solving, sleeping, or the game's scheduling/owner state.
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <vector>
namespace tm2020::recovered {
inline constexpr char executable_sha256[]="3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda";
inline constexpr std::uint32_t integrate_pose_rva=0x7f4d40;
inline constexpr std::uint32_t integrate_quaternion_rva=0x194de0;
inline constexpr std::uint32_t quaternion_matrix_rva=0x1886d0;
inline constexpr std::uint32_t force_velocity_rva=0x7f89d0;
inline constexpr bool full_trackmania_physics=false;
struct RigidState {
    std::array<float,9> rotation{1,0,0,0,1,0,0,0,1}; // +0x00
    std::array<float,3> position{};                    // +0x24
    std::array<float,4> quaternion{1,0,0,0};           // +0x30, scalar first
    std::array<float,3> linear_velocity{};            // +0x40
    std::array<float,3> angular_velocity{};            // +0x4c
};
static_assert(sizeof(RigidState)==0x58);
static_assert(offsetof(RigidState,position)==0x24&&offsetof(RigidState,quaternion)==0x30);
static_assert(offsetof(RigidState,linear_velocity)==0x40&&offsetof(RigidState,angular_velocity)==0x4c);
struct BodyParameters {
    // Native model reads +0x1c,+0x2c,+0x3c and copies them to a separate
    // 16-byte-per-body output. Their higher-level meaning remains unverified.
    std::array<float,3> auxiliary_model_values{};
    float angular_speed_limit{}; // native model +0x4c; supplied, not guessed
};
using AuxiliaryOutput=std::array<float,4>; // final lane remains unchanged
// Recovered constructor defaults, not the effective Stadium race settings.
struct SolverParameters {
    std::uint32_t friction_static_iterations{4},friction_dynamic_iterations{1},velocity_iterations{4},position_iterations{4};
    float depenetration_impulse_factor{.2f},max_depenetration_velocity{1.f};
    std::uint32_t enable_position_constraint{};
    float allowed_penetration{-1.f};
    std::uint32_t velocity_bias_mode{},use_constraints2{};
    float min_velocity_for_restitution{1.f};
};
static_assert(sizeof(SolverParameters)==0x2c);
// IEEE binary32, round-to-nearest, without FTZ/DAZ or contraction. Caller owns
// its floating-point environment. Throws before mutation on invalid input.
void integrate_quaternion(std::array<float,4>& q,const std::array<float,3>& omega,float interval);
void quaternion_to_matrix(std::array<float,9>& matrix,const std::array<float,4>& q);
void integrate_pose(RigidState& state,const BodyParameters& model,AuxiliaryOutput& auxiliary,float interval);
struct ForceAccumulator {
    std::array<float,3> linear{},angular{};
};
static_assert(sizeof(ForceAccumulator)==0x18);
struct VelocityStepParameters {
    // Native 16-byte array: the routine multiplies torque by lanes 0..2,
    // and force by lane 3. Caller must supply the actual engine coefficients.
    std::array<float,4> coefficients{};
    std::uint32_t flags{}; // native per-item +4; bit 1 skips the velocity kernel
    float model_gravity_scale{},item_gravity_offset{},item_gravity_multiplier{};
    bool sleeping{}; // native sleep entry's uint16 +4 equals 0xffff
};
struct GravityEnvironment {
    std::array<float,3> gravity{};
    // Defaults in the pinned executable's data image, not verified race values.
    bool attenuate_small_velocities{true};
    float small_velocity_threshold{.01f},small_velocity_multiplier{.9f};
};
// Exact arithmetic from ComputeGravityAndSleepStateAndNewVels, with explicit
// configuration inputs. Profiling/TLS side effects are outside this API.
// Clears consumed force/torque; skipped items retain both state and forces.
void integrate_forces(RigidState& state,ForceAccumulator& forces,
    const VelocityStepParameters& parameters,const GravityEnvironment& environment,float interval);
struct RigidSnapshot {
    std::uint64_t tick{};
    std::vector<RigidState> states;
    std::vector<BodyParameters> parameters;
    std::vector<AuxiliaryOutput> auxiliary;
};
// Autonomous post-force kernel runner: no game process, assets, original code,
// DLL injection, or Python required. World snapshot is only this runner's state.
class RigidWorld {
public:
    explicit RigidWorld(std::size_t bodies);
    void reset(std::span<const RigidState> states,std::span<const BodyParameters> parameters);
    void step(float interval);
    // Explicit composition of the recovered velocity and pose kernels.
    // The game also solves contacts and adaptively subdivides pose steps;
    // neither behavior is reproduced here. External inputs are caller-owned.
    void step_force_then_pose(float interval,std::span<ForceAccumulator> forces,
        std::span<const VelocityStepParameters> parameters,const GravityEnvironment& environment);
    RigidSnapshot snapshot()const;
    void restore(const RigidSnapshot& snapshot);
    std::span<const RigidState> states()const noexcept{return states_;}
    std::span<const AuxiliaryOutput> auxiliary()const noexcept{return auxiliary_;}
    std::uint64_t tick()const noexcept{return tick_;}
private:
    std::vector<RigidState> states_;
    std::vector<BodyParameters> parameters_;
    std::vector<AuxiliaryOutput> auxiliary_;
    std::uint64_t tick_{};
};
}
