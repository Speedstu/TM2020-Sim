# Fall 2026-01: reference-assisted hybrid branch, 31 October 2026

The user explicitly authorized combining hardcoded control and machine learning
to pursue the top-ten time. This branch is **map-specific and reference-assisted**.
It must not be reported as an unassisted learned policy or unseen-map driving.
The fixed candidate subsequently reached the actual-client result screen at
**19.988 s**, displayed **Top 2 World**. Evidence is under
`local/recon/internal-0.51/live-user-hybrid/`. The physical command trace has no
fault before arrival, but fault 7 appears at race time 20.080 s, after the
19.988 s finish. The post-stop readback is neutral and the original entry bytes
are restored. The strict clean-run gate remains unpassed.

The saved replay declares 19.988 s with zero respawns, but its recorded driving
inputs are all neutral: internal commands bypass the normal replay input
recorder. Do not present that replay as independently reproducing the run.
The networked Solo client automatically published the personal best. Further
campaign work is simulator-only; the user will handle offline client tests.
See `docs/FALL_CAMPAIGN_0_52.md` for the new campaign objective.

## Current evidence

The retained **unassisted PPO** real-game champion is the 0.46 continuous policy at 23.366 s.
The 0.50 candidate finished twice in the actual client at 23.875 s, slower than
that champion. Neither those files nor the original DLL were replaced.

The new assisted tracker begins with the public WR's pre-tick rigid states and
steering commands, already reproduced in the frozen simulator at 19.988 s.
Replaying them without sufficient physical correction was fragile on other
seeds. A bounded population search optimized feedback, then small smooth lateral
offsets to give the line more room near walls. Each tested candidate executes
complete native races, with no teleports, resets midtrial, or ghost commands
substituted after a failure.

Final fixed candidate: `local/training/hybrid-20261031/robust-candidate.tmhyb`.
After a 16-case development search, two fresh 64-case suites gave:

| Suite | Arrivals | Mean among arrivals | Arrival range |
|---|---:|---:|---:|
| Nominal, seed set 105271 | 63/64 | 19.988635 s | 19.988–19.997 s |
| Perturbed, seed set 105272 | 53/64 | 19.988925 s | 19.988–19.995 s |

Those times are **conditional on finishing**. Failures must not disappear from
the comparison: charging a DNF 40 s gives substantially worse expected times.
Perturbations are short additive steering kicks (.02–.1 amplitude, 10–70 ms)
at different times during the first 17 s. These are lighter disturbances than
some previous PPO suites; their finish rates are not directly comparable.
The target reference was 20.006 s at the last read-only leaderboard fetch,
2026-10-31 00:31:38 UTC (`hybrid-20261031/leaderboard-latest.json`).
These simulator races do not establish a world ranking, actual-client speed,
or guaranteed repeatability. Their margin is only milliseconds.

Files: `line-robust/{development-cases.json,best.json,nominal64.json,perturbed64.json}`.
Earlier pilots and their failures remain under `feedback-search-v2/`,
`feedback-diverse/`, `line-search/`, `nominal64.json`, `perturbed64.json`,
`line-nominal64.json`, and `line-perturbed64.json`. Four nominal development
seeds initially overestimated robustness; the later tests exposed this.

## Controller and native integration

`native/include/tm2020/trajectory_hybrid.hpp` is shared by the simulator evaluator,
portable C ABI and Windows runtime. It provides:

- 100 Hz macro-tick decisions; duplicate adaptive substeps retain commands.
- Reference matching using current physical position in a bounded local window,
  with a phase-consistency term and start-clock alignment.
- Feedforward steering plus lateral-position/velocity, heading and yaw feedback.
- An optional bounded neural residual (12 inputs → 32 tanh → 1 tanh).
- Full gas and no brake, explicitly specialized to this map's two public fast
  references, which contain no gas-off or brake ticks.
- Refusal/neutral commands on nonfinite state, backward/jumping clock, excessive
  trajectory displacement, invalid assets, wrong map UID or wrong map-file hash.
  Existing game owner/map/session/stop/heartbeat guards still apply.

The small smooth lateral offsets modify the target geometry in meters; they do
not move the actual physics car. Feedback gains and offsets are learned by
black-box population optimization, not by PPO. The fixed fast candidate has
**zero neural residual weights**. A neural residual should only be enabled
after it demonstrates a whole-race improvement against the same assisted base.

Asset format `TMHYB001` stores explicit version/dimensions, map UID/SHA256,
gains, network coefficients and 25 float values per reference tick, followed by
a checksum. The launcher stages assets/DLLs under immutable content-hash names.
`load_policy` recognizes this distinct format; old TMPPO models still use their
existing perception schemas and histories. No peripheral driving fallback,
new security bypass or anti-cheat change was added.

The asset is named and reported as reference-assisted control. A copied public
ghost, a simulator finish, or a successful loader return cannot qualify the
actual-client goal. No scores are intentionally submitted by the tools. Client
tests require a local offline race to avoid automatic online score handling.

## Learning experiments

`train_hybrid_residual.py` implements a separate, bounded CUDA PPO experiment
with a maximum steering residual of .05, unchanged native minimum-time reward,
10 ms decisions and complete-lap evaluation. The first base/feedback pilot
stopped after 24 updates without a better selected model. A later experiment
uses the displaced reference itself, rather than silently reconstructing the
unshifted WR line. Its source asset and gain protocol are explicit. It stopped
at update 44 with best update 20. A fresh 64-case paired qualification found
45 base-controller arrivals versus 44 with the learned residual (DNF-penalized
means 25.938859 s versus 26.242281 s). It failed promotion and is not used by
the retained fast candidate. Evidence: `residual-qualification64.json`.

The 0.50 PPO continues independently as `tm2020-top10-main.service`, under
`local/training/adaptive-20261031/main/`. Its current best/mean and any later
improvements are simulator-only until tested in the client. That principal
policy is not automatically mixed into a high-speed reference controller;
adding two incompatible steering outputs would not establish an improvement.

## Continuous hybrid pursuit

`tm2020-hybrid-pursuit.service` executes the frozen
`local/training/hybrid-20261031/frozen/code/hybrid_pursuit.py`.
Its directory is `local/training/hybrid-20261031/pursuit/`.

Each generation tests four candidates × sixteen fixed development cases,
jointly optimizing five smooth lateral offsets and four feedback gains.
Finish count is selected first, then DNF-penalized mean. After 24 generations
without improvement it returns to the retained best and broadens exploration.
Every sixteen generations it records a rotating 64-case diagnostic suite;
this is a recorded diagnostic, not a held-out final qualification or a map split.

Optimizer distribution, RNG, generation, phases and best candidate are saved.
The active frozen code/native files have a manifest; do not mutate them or
overwrite libraries mapped by a running process. The service is enabled at
user login, with at most three failure restarts per ten minutes. Normal stop
or verified-goal exits do not restart. It has no fixed overall generation limit,
but `STOP` or SIGTERM checkpoints and stops it. This is a native/Python search,
**not an LLM monitor**. The old hourly timer remains disabled/inactive.

The service does not launch the game or submit scores. Only separately collected
`verified-game.json` evidence can complete its goal: fresh board, exact map,
model/replay/runtime hashes, native zero-respawn replay metadata, target-beating
time and matching internal-control/normal-detach proof. The original 0.50
`finish_evidence.py` gate is reused. Actual tests require a working offline client.
The attempted 0.51 launch closed at loading; departure qualification failed,
and `directControlTicks` was zero. A request for the user to reopen the offline
map remains pending. No new actual-client finish is claimed.

```sh
systemctl --user status tm2020-hybrid-pursuit.service
cat local/training/hybrid-20261031/pursuit/status.json
journalctl --user -u tm2020-hybrid-pursuit.service -n 5 --no-pager
```

`local/training/current.json` keeps the PPO pointer and adds explicit hybrid
service, status, asset and qualification pointers. Both branches are work in
progress; the retained actual-client champion remains separately identified.

## Tests and tools

- Native `tm2020_trajectory_hybrid_test` checks feedforward, position/velocity
  feedback, bounded NN, i8 controls and clock/state/distance refusal.
- Existing internal-tick and hybrid-action tests pass.
- Both Python and native parsers reject a corrupted asset checksum.
- Owned Windows fixture exercised continuous/17/33 heads and the trajectory
  controller. 256 perception rows matched Linux exactly; 100 assisted decisions
  reached the consumer bitwise equal to the native simulator controller.
  State qualification, neutralization, detour restoration and stop checks remain.
- Evidence is `local/recon/internal-0.51/owned-windows-final.json` and logs.
  A second fixture for the retained robust candidate is under `internal-0.51-final/`.
  That second fixture also passed: zero observation error, all 100 trajectory
  decisions bit-exact to the native simulation controller; max perception
  time 389 microseconds in the separate legacy encoder test.
- Whole-race search moved into the native vector API to avoid Python roundtrips
  at every 10 ms tick. The physics library/reward is unchanged.
- `native/CMakeLists.txt` now provides `tm2020_trajectory`,
  `tm2020_trajectory_hybrid_test`, and the extended existing vector target.

Python entry points: `hybrid_tracking.py`, `tune_hybrid_tracking.py`,
`tune_hybrid_line.py`, `train_hybrid_residual.py`, `hybrid_pursuit.py`.
Runtime bundle: `local/recon/deployment-0.51/build.json`.
