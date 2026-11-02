#pragma once
#include "rl.hpp"
#include <optional>
namespace tm2020::rl {
// Samples an unchanged policy at nominal 100 ms intervals of a measured clock.
// Rewards define a reference-route task, not the game's competitive score.
// An incomplete last action is discarded; completed prefixes bootstrap at their
// actual final observation. No inferred race finish is labeled terminal.
class RealtimeResidualRollout {
public:
    RealtimeResidualRollout(const ActorCritic& policy,std::uint64_t seed=0);
    RealtimeResidualRollout(const ActorCritic& policy,const std::mt19937_64& rng);
    double observe(std::span<const double> observation,std::uint32_t clock_ms,
                   double reference_sample,double route_error_m);
    void truncate();
    void write_csv(const std::filesystem::path& file) const;
    const std::vector<Transition>& transitions() const noexcept{return rows_;}
    const std::mt19937_64& sampling_rng() const noexcept{return rng_;}
private:
    const ActorCritic& policy_;
    std::mt19937_64 rng_;
    struct Pending{Transition transition;std::uint32_t clock;double progress,action;};
    std::optional<Pending> pending_;
    std::vector<Transition> rows_;
    double correction_{};
    bool closed_{};
};
// Holds deterministic actions for 100 ms. No sampling, transitions or training.
class RealtimeResidualEvaluation {
public:
    explicit RealtimeResidualEvaluation(const ActorCritic& policy):policy_(policy){}
    double observe(std::span<const double> observation,std::uint32_t clock_ms);
private:
    const ActorCritic& policy_;
    std::optional<std::uint32_t> last_clock_;
    double correction_{};
};
}
