#pragma once
// Native CPU PPO. Environment fidelity is a separate, explicit responsibility.
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <random>
#include <span>
#include <string>
#include <vector>
namespace tm2020::rl {
struct Network {
    std::size_t inputs{},hidden{},outputs{};
    std::vector<double> parameters;
    Network(std::size_t in,std::size_t width,std::size_t out,std::mt19937_64& rng);
    std::vector<double> forward(std::span<const double> x) const;
    void forward_into(std::span<const double> x,std::span<double> output) const;
    // Adds d(output)/d(parameters) times upstream into gradient.
    void backward(std::span<const double> x,std::span<const double> upstream,std::span<double> gradient) const;
};
struct Decision {
    std::vector<double> action,latent;
    double log_probability{},value{};
};
class ActorCritic {
public:
    ActorCritic(std::size_t observations,std::size_t actions,std::size_t width=32,std::uint64_t seed=0);
    Decision sample(std::span<const double> observation,std::mt19937_64& rng) const;
    // The caller draws standard normals in stable order before parallel work.
    Decision sample_with_noise(std::span<const double> observation,std::span<const double> standard_normals) const;
    Decision deterministic(std::span<const double> observation) const;
    // No heap allocations on this inference path (hidden width <=1024).
    void predict_into(std::span<const double> observation,std::span<double> actions,double& value) const;
    double log_probability(std::span<const double> observation,std::span<const double> latent) const;
    double value(std::span<const double> observation) const;
    void save(const std::filesystem::path& file,const std::string& observation_schema) const;
    static ActorCritic load(const std::filesystem::path& file,std::string* observation_schema=nullptr);
    Network actor,critic;
    std::vector<double> log_std;
};
struct Transition {
    std::vector<double> observation,latent;
    double old_log_probability{},old_value{},reward{},next_value{};
    bool terminated{},truncated{};
    // Semi-Markov duration in nominal decision periods (default: one step).
    // Real-time adapters record actual elapsed game-clock time, including jitter.
    double elapsed_steps{1.};
};
struct Advantage {double advantage{},target{};};
// Time-major vector rollout: [time0/env0, time0/env1, ..., time1/env0, ...].
// next_value MUST describe the final observation before an automatic reset.
// Termination zeroes bootstrap. Truncation bootstraps but stops GAE recursion.
std::vector<Advantage> generalized_advantage(std::span<const Transition> rollout,
    std::size_t environments,double gamma=.99,double lambda=.95);
struct PpoConfig {
    double learning_rate=3e-4,gamma=.99,lambda=.95,clip=.2,value_coefficient=.5;
    double latent_entropy_coefficient=0.,max_gradient_norm=.5,target_kl=.02;
    std::size_t epochs=8,minibatch=64;
};
struct UpdateMetrics {
    double policy_loss{},value_loss{},approx_kl{},clip_fraction{},gradient_norm{};
    std::size_t minibatches{},epochs{};
    bool kl_stopped{};
};
class PpoTrainer {
public:
    explicit PpoTrainer(ActorCritic& policy,PpoConfig config={},std::uint64_t seed=0);
    UpdateMetrics update(std::span<const Transition> rollout,std::size_t environments);
    // Self-contained, atomic training checkpoint: weights, Adam, configuration,
    // shuffle RNG and rollout sampler RNG. Load validates before mutating state.
    // Call only between rollouts. Inference .tmppo files remain ABI-compatible.
    void save_checkpoint(const std::filesystem::path& file,const std::string& schema,
                         const std::mt19937_64& sampler_rng) const;
    void load_checkpoint(const std::filesystem::path& file,const std::string& expected_schema,
                         std::mt19937_64& sampler_rng);
    std::uint64_t optimizer_steps() const noexcept{return updates_;}
private:
    ActorCritic& policy_;
    PpoConfig config_;
    std::mt19937_64 rng_;
    std::vector<double> first_moment_,second_moment_;
    std::uint64_t updates_{};
};
}
