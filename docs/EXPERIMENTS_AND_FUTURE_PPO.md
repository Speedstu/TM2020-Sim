# Experiments, lessons, and future PPO work

This is the project's retrospective through 2 November 2026. It consolidates
the main experiment families, useful results, failed approaches, integration
mistakes and remaining work. The linked version notes contain the detailed
protocols. Some original traces and checkpoints remain private local artifacts;
their historical paths in those notes are not files supplied by this repository.

**The two bundled champions are hardcoded controllers, not PPO agents.** Their
neural correction arrays contain zero nonzero coefficients. Their parameters
and reference trajectories were optimized with black-box search. The presence
of PPO code, a neural-network slot in the asset format, or the word “training”
does not turn those artifacts into learned PPO policies.

**Maintainer's intent:** I want to conduct new PPO experiments in the future.
The hardcoded champions remain the working baseline and are preserved while
testing other approaches. This is a research direction, not an announcement
that a new PPO training run is active. Training remains paused at this update.

## Reading the results

- Simulator finishes, actual client finishes and official online rankings are
  different evidence. One must not be substituted for another.
- Finish rate comes with the time statistics. A fast best lap does not erase
  failures; a mean among finishers excludes DNFs unless explicitly stated.
- Comparisons are causal only when map, physics, observations, input mode,
  seeds, perturbations and budget are matched. Different historical suites
  cannot be ranked simply by comparing their reported means.
- Reused development seeds are selection data, not fresh holdouts. Sixty-four
  seeds need not represent 64 distinct physical starts in every input mode.

## 1. Building and validating the simulator

Early experiments included simplified kinematic/system-identification models,
recovered arithmetic and original-instruction tests. They were useful for
isolating SDK components, but they did not establish a faithful complete racing
environment. A fast toy model was not a sufficient basis for training a fast
Trackmania driver.

The practical headless backend uses the pinned Gearbox physics and installed
game assets, with a Linux port and native vectorized wrappers. Independent
work also used the official server as an oracle and compared selected original
instruction paths. These are different validation methods with different scopes.
The project did not independently reverse-engineer the entire game.

What helped: replaying original controls, checking actual checkpoints and
finish time, preserving validation seeds, full-state reset/restore, and testing
that parallel environments do not advance each other's state. Visual samples
also required an explicitly declared post-step timestamp convention; a small
visual-position error is not proof of bit-exact arbitrary game physics.

The source distribution was rebuilt separately and reproduced the external
02 replay's 21.328 s finish. Unsupported mechanics and untested client versions
remain limitations. Sources: [headless backend 0.33](PHYSICS_0_33_HEADLESS_BACKEND.md),
[Linux integration 0.37](PHYSICS_0_37_FAST_PPO.md),
[source-build checks](SOURCE_VALIDATION.md).

## 2. Imitation learning, BC and DAgger

Behavior cloning could reduce supervised prediction error without producing a
reliable closed-loop driver. Once the policy drifted from the demonstrations,
its inputs no longer covered the states used for training. An imitation
initialization from a 19.967 s replay produced **0/5 finishes** in one retained
experiment and was rejected.

DAgger-style collection improved an early network's state coverage, but did not
make it more robust than the corresponding planning controller. Later BC/v8
research was also kept separate from the campaign controller; it was not promoted
as a replacement merely because its imitation loss looked better.

What helped: demonstrations as initialization or route priors, closed-loop
evaluation and collecting corrections on visited states. What did not work:
assuming a small supervised loss implied a fast race, training on too few nominal
traces, or treating a ghost's time-indexed actions as an expert on deviated states.
Sources: [early reward/BC experiments](MINIMUM_TIME_PPO_0_42.md),
[training audit](ML_PROJECT_COMPARISON_20261030.md),
[human hardcode qualification](HUMAN_HARDCODE_0_74.md).

## 3. PPO steering: continuous, 17 levels and 33 levels

A matched comparison used continuous tanh-Gaussian steering or categorical
17/33-level steering, binary pedals, common initialization, observations,
training schedules and perturbations. Each arm received **1,441,792 transitions**
across three training seeds. The 123 reported evaluations reuse 41 departures
across those training seeds; they are not 123 independent tracks.

| Steering head | Simulator finishes | Mean among finishers | Best | Mean with DNF charged as 40 s |
|---|---:|---:|---:|---:|
| Continuous | 112/123 | 24.857 s | 22.584 s | 26.211 s |
| Discrete 17 | 87/123 | 25.275 s | 21.245 s | 29.585 s |
| Discrete 33 | 109/123 | 25.237 s | 21.521 s | 26.917 s |

Corresponding nominal client trials finished in **23.366 s**, **23.688 s** and
**23.488 s**, respectively. A separate continuous client trial repeated 23.366 s.
These small client samples are not a robustness benchmark. The 17-level arm
performed worse overall in this experiment despite its fast isolated best lap.
The continuous/33-level difference was inconclusive under the reported paired
intervals. This does not establish a universally superior action distribution.

What worked: PPO could produce a genuine internally controlled client finish.
What remained weak: speed, recovery coverage and convergence toward the fastest
trajectories. Source: [matched PPO and client comparison](INTERNAL_PIPELINE_0_46.md).

## 4. Reward, credit assignment and risk

The later minimum-time PPO objective rewarded finishing sooner at every time:
complete successful return was `100 - finish_seconds`; failure over the
40-second horizon returned `-140`. There was no special 24-second target.
Idle and straight-only controls were checked in the actual simulator and did
not gain reward by waiting or failing early.

We tested longer credit assignment, GAE lambda 1, telescoping potential shaping,
and replaying the agent's own slow cases. Four matched short pilots, each with
393,216 transitions, did not beat the frozen incumbent under the promotion gates.
Those options were left disabled. Earlier shaping and fine-tuning pilots also
failed to establish a reliable speed improvement.

The lesson is not that shaping or longer credit can never help. The terminal
objective was already rewarding time correctly; observation coverage,
exploration and risk mattered too. A large failure penalty can favor a safe but
slower line. A huge moving penalty against the previous model was not a tested
solution and was not added as a cure. Sources: [reward experiments](MINIMUM_TIME_PPO_0_42.md),
[credit and speed-loss audit](TIME_CREDIT_0_48.md).

## 5. Curriculum, observations and exploration

An earlier curriculum spent much of training near the end of the expert run.
Its graduation gate stalled, leaving a distribution mismatch between expert
reset states and the agent's own full-start driving. More steps on that same
curriculum did not resolve the bottleneck.

Follow-up pilots tested complete snapshots from the agent's own laps, stratified
across race time; a 72-feature preview encoder; pedal-temperature changes; and
larger steering exploration. The preview was a coarse geometry cue, not a solved
route graph. Some client-unqualified physical channels stayed masked.

A pedal-temperature profile was the strongest of twelve matched pilots. On its
new 64-case qualification, arrivals improved from **62/64 to 64/64**. However,
that candidate finished twice in the client in **23.875 s**, slower than the
retained 23.366 s PPO reference. Better simulation qualification did not justify
a client speed promotion. Combining all proposed improvements was not
automatically better than changing one factor.

Sources: [observation/curriculum audit](ML_PROJECT_COMPARISON_20261030.md),
[adaptive PPO pilots and client check](ADAPTIVE_PPO_0_50.md).

## 6. Planning and PPO residuals: mixed results

An early known-route planner tested candidate steering actions through the
simulated physics and allowed PPO to provide a bounded correction. One frozen
candidate finished **30/30 fresh perturbed trials**, averaging **21.954 s**,
versus **22.132 s** for the same planner without the learned correction. This
was a useful measured PPO contribution in that particular experiment. It was
not an unassisted network or an unseen-map result.

Later PPO corrections to the faster hardcoded tracker did not show the same
benefit. A paired 64-case test gave **45 base-controller finishes versus 44 with
the residual**; DNF-penalized means were **25.939 s versus 26.242 s**. The learned
residual failed promotion. The retained fast controller used zero neural
correction weights.

The lesson is to compare a learned correction against its exact unchanged base,
not assume “hardcode + ML” must be better. Sources: [early planner/PPO result](PHYSICS_0_37_FAST_PPO.md),
[later hybrid and residual experiments](HYBRID_PURSUIT_0_51.md).

## 7. Why the hardcoded controller became the main branch

Reference-assisted tracking combined feedforward with position, velocity,
heading and yaw feedback. Black-box population search optimized gains, smooth
spatial targets and pedal timing while evaluating full physical races. Candidate
target edits did not teleport or overwrite the actual car's physical state.

This was substantially faster on the specialized map than the retained standalone
PPO policies. An early client run finished in **19.988 s**, but its saved replay
had neutral inputs; that integration defect prevented treating the replay as a
valid reproduction of the driving commands.

The preserved legacy record artifact later reached **19.986 s** in 64/64 nominal
simulation cases and 60/64 separate perturbed cases. In that old direct-control
mode, those nominal seeds represent one physical start condition. Its historical
record claim and replay limitations are documented with the [bundled model](../models/fall-2026-01/).

What worked: physical feedback, optimized trajectories, matched seed evaluations
and retaining incumbents. Limits: map-specific reference dependence, occasional
failures under disturbances, and no demonstrated generalist policy.
Sources: [hybrid tracker](HYBRID_PURSUIT_0_51.md),
[campaign search](FALL_CAMPAIGN_0_52.md).

## 8. Input-history and replay mistakes

Writing commands only at the physical consumer moved the client car but could
leave ordinary replay controls neutral. A successful result screen therefore
did not prove that a saved replay contained the controls actually used.

The revised path changes normal inputs before the original decoder and checks
them at the physical consumer. Original client replays are decoded and compared;
inputs are not fabricated afterward. Matching simulator input history also
mattered: normal history activates real start adjustments, so old direct-control
champions did not automatically transfer to the new mode.

For example, retained 03/06 models lost much of their normal-history reliability.
A small four-seed feedback search overfit; on its independent matched 64 cases,
the 03 candidate finished 39 times against the baseline's 41, and the 06 candidate
once against the baseline's twice. Those candidates were rejected.

Other repairs included latching tracker failures until reset, committing the
verified replacement vehicle after a reset, and immutable DLL staging. Replacing
a mapped DLL had caused a client crash; later staging avoids replacing its inode.
The remaining post-finish detachment bug is still documented, not considered
fixed by a simulator test. Sources: [recording-path revision](REPLAY_CONTROL_PIPELINE_0_69.md),
[client input checks](CLIENT_INPUT_SMOKE_0_74.md),
[internal pipeline and staging](INTERNAL_PIPELINE_0_46.md).

## 9. Human-style controls: constraints, failures and fixes

Smoothing alone was insufficient. The v5 governor enforced steering-step,
change/reversal budgets, holds and pedal restrictions on actual actions. Its
first constrained 01 smoke test passed the envelope assertions but finished
**0/8**. Legal-looking inputs were not evidence that the constrained controller
could follow a feasible fast line. Continuing a large zero-finish campaign was
not useful training.

Subsequent work used more contextual action budgets and feasible normal-history
route initialization. A 02 human-input test initially stopped one physics tick
too early; a bounded tail recovered the original Top-1 finish at **21.290 s**.
Other original streams also finished, while a divergent Top-3 stream was excluded.
That diagnostic separated an end-of-replay timing bug from controller feasibility.

Human-style scoring also had bugs: duration checks accidentally reused the wrong
metric's extrema, and summaries used means where medians were advertised. Both
were corrected. Whole-lap constant-pedal holds are right-censored only under
explicit matching-duty conditions, so a faster lap is not penalized simply for
ending its full-throttle hold sooner.

The resulting **human 01** achieved 64/64 normal and 64/64 perturbed simulator
finishes within the saved Top-10 threshold and per-run human P10–P90 criteria.
Its preserved client finish is **19.995 s**, zero respawns, with 2,000 decoded
inputs and exact controller/replay-simulation command agreement. The current
source build reproduces it. These checks establish the measured input proxy,
not human indistinguishability.

On 02, genuine route initialization recovered a 5/16 initializer from a zero-finish
screen. Later search changed individual pedal intervals and their count/duration
instead of only tuning steering. The tested 02 client candidate finished in
**21.328 s**, under the saved Top-100 threshold but 13 ms above the saved Top-10
threshold. It was not fully qualified across all 128 cases. The complete 25-map
human Top-100/Top-10 goal remains unfinished.

Sources: [v5 failure](HARDCODE_INPUT_RHYTHM_0_71.md),
[human 01 qualification](HUMAN_HARDCODE_0_74.md),
[02 diagnosis and rhythm search](HUMAN_HARDCODE_0_75.md),
[published 01 evidence](../models/fall-2026-01/human-validation.json).

## 10. Performance and monitoring

Native vectorization, persistent workers, binary rollouts and CUDA optimizer
work improved throughput. One historical end-to-end PPO service measured about
**13,896 decision transitions/s**. Higher environment-count benchmarks reached
larger rates, but did not demonstrate better driving. Standalone physics-tick
benchmarks are not PPO SPS, especially when each decision advances multiple
ticks or performs many lookahead simulations.

GPU optimization helped the optimizer; it did not move the Rust physics to the
GPU. More hours, more parallel maps or higher SPS did not resolve broken input
parity, poor resets, an infeasible action envelope or a plateau by themselves.

Bounded stages, plateau stops, checkpoint preservation and process checks were
useful. Historical hourly automation was not an LLM continuously diagnosing the
bot. It stays disabled. An obsolete service that restarted at login was found
and disabled during cleanup. No monitor or training is started by this update.
Source: [throughput measurements](THROUGHPUT_0_43.md).

## Future PPO experiments I want to run

The objective is to learn a stronger, robust driver while preserving plausible
inputs and a verifiable client replay path. PPO remains worth investigating;
the previous results do not prove it is fundamentally inferior to hardcode.
The following are planned experiments, not completed results:

1. **Freeze the environment contract first.** Use the same normal input decoder,
   history, quantization, time alignment and reset semantics in training and
   deployment. Include legal holds/transitions in the action contract itself.
2. **Compare standalone PPO and a bounded PPO residual separately.** Keep the
   current hardcoded champion unchanged as a baseline. Declare any route prior,
   demonstration warm start or planner assistance explicitly.
3. **Retest continuous versus 17/33-level steering fairly.** Match seeds,
   observations, pedal actions, physical time generated and optimization budget;
   also report wall-clock cost. Keep PPO probabilities consistent with the actual
   action parameterization rather than silently modifying sampled actions.
4. **Improve coverage before extending a plateau.** Compare own-state full-race
   resets, midrace recoveries, coherent pedal exploration and route preview one
   factor at a time. Treat new observations as a separate schema requiring client
   parity, not assumed working offsets.
5. **Keep the time objective auditable.** Faster successful finishes should earn
   more return. Recheck idle, looping, early failure and truncated episodes.
   Test shaping or credit changes as controlled ablations, not automatic fixes.
6. **Measure performance and human style together.** Use matched 64 normal plus
   64 perturbed development cases, then fresh holdouts after model selection.
   Report finishes/DNFs, mean, median, best, tail performance and per-run pedal,
   steering, hold and reversal metrics. Human-style statistics do not certify
   that a replay is indistinguishable from a human's.
7. **Evaluate generalization separately.** Hold out entire maps when testing an
   unseen-map claim. A route-assisted 01 success cannot establish it.
8. **Promote only a verified benefit.** Preserve the hardcoded champions; require
   a defensible speed/robustness improvement without breaking input constraints.
   Validate a fresh local/offline client finish and its original recorded inputs
   before describing simulator gains as game results.

The immediate deliverable here is an honest record and a reproducible baseline
for that work. No new PPO run, model replacement, client injection or record
submission is implied by this roadmap.
