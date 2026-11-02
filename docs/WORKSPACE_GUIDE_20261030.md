# Trackmania2020-RE — workspace for review (30 October 2026)

> Historical snapshot. Use the [current workspace guide](WORKSPACE.md) and
> [project README](../README.md). Training is paused; the services described
> below are not a current process inventory.

The user requested continued training toward the top-ten time. Current runner,
experiments, phase plateau rules and evidence are in `HYBRID_PURSUIT_0_51.md`
and `ADAPTIVE_PPO_0_50.md`.
Consult its run's `status.json` and user-service state for live progress.
The old hourly timer remains disabled. Historical paths below are retained.

## Code and retained artifacts

| Purpose | Location |
|---|---|
| Review entry point | `docs/CODE_REVIEW_0_46.md` |
| Internal tick, state and driving commands | `integrations/generalist-training/runtime.cpp` |
| Hook and control guards | `integrations/generalist-training/internal_hook.hpp`, `native/include/tm2020/internal_tick.hpp` |
| DLL loader and immutable staging | `native/src/local_dll_loader.cpp`, `scripts/proton_sdk.py` |
| Common map perception | `integrations/generalist-training/environment.rs` |
| Vector physics | `integrations/generalist-training/vector_physics.cpp`, `scripts/vector_physics.py` |
| Matched PPO comparison | `scripts/compare_hybrid_ppo.py` |
| New guarded continuation | `scripts/robust_ppo.py`, `docs/ROBUST_PPO_0_47.md` |
| Current run and status | `local/training/adaptive-20261031/main/` (`tm2020-top10-main.service`) |
| Explicit assisted hybrid pursuit | `local/training/hybrid-20261031/pursuit/` (`tm2020-hybrid-pursuit.service`) |
| Shared native hybrid control and format | `native/include/tm2020/trajectory_hybrid.hpp`, `native/src/trajectory_hybrid.cpp` |
| Current training entry point | `scripts/train_adaptive_ppo.py`, frozen execution copy under `adaptive-20261031/frozen/code/` |
| New encoder, own-state resets and bounded experiment | `scripts/preview_ppo.py`, `integrations/generalist-training/preview.rs`, `scripts/train_preview_adapter.py` |
| Matched pilot and actual-client evidence | `local/training/adaptive-20261031/`, `local/recon/internal-0.50/verified-live-result.json` |
| Stopped 0.49 run | `local/training/top10-20261030/ppo20/` |
| Stopped 100 Hz research | `local/training/top10-20261030/ppo100/` |
| Stopped time-credit continuation | `local/training/time-main-20261030/` |
| Reward/credit diagnostics and comparisons | `local/training/time-credit-20261030/`, `scripts/ppo_time_credit.py` |
| Historical robust run | `local/training/robust-main-20261030/` (stopped) |
| Continuous continuation runner to inspect | `scripts/resume_internal_continuous.py` |
| CUDA PPO and history helpers | `scripts/gpu_ppo.py`, `scripts/cuda_history.py` |
| Real-game validated export | `local/recon/deployment-0.46/candidate.tmppo` and `candidate.json` |
| Source policy for that export | `local/recon/internal-0.46/ppo-comparison/46602-continuous/best.pt` |
| Later, simulator-only continuation | `local/training/internal-continuous-resume-20261030/` |
| Other retained discrete experiments | `local/training/discrete33-antiplateau-20261030/`, `local/training/discrete33-cuda-eco-20261030/` |
| Real-game evidence | `local/recon/internal-0.46/verified-live-result.json`, `real-policy-comparison.json` |
| Experiment protocol and held-out simulation | `local/recon/internal-0.46/ppo-comparison/` |
| Native vector library | `native/build-linux/libtm2020_vector_physics.so` |
| Frozen simulation library | `cache/reward-study-target/release/libtm2020_speed.so` |
| CUDA environment | `tools/venv-gpu/` |

The selected continuous candidate finished Fall 2026-01 twice in the real client
in 23.366 s. Matching discrete-17 and discrete-33 candidates finished in 23.688 s
and 23.488 s. Each matched arm has one nominal real-game departure; see the
[pipeline guide](INTERNAL_PIPELINE_0_46.md) for exact evidence and limitations.
Later training outputs do not inherit this real-game qualification merely
because they started from that policy.

## CPU and CUDA boundaries

PPO actor/critic optimization uses CUDA. Physics remains native CPU code.
`cuda_history.py` provides an optimized history path for runners that import it;
it is not used by every historical or comparison script. Worker benchmarks and
simulator parity tests apply to their documented actions, seeds and maps.

The frozen backend and matched comparison are retained. No claim of perfect
physics, all Trackmania mechanics, unseen-map strength or a top-10 time follows
from the completed tests.

## Cleanup boundaries

The review cleanup removes the disposable owned-test Wine prefix, redundant
Rust/MinGW installer downloads and extracted installers, and the Rust debug
build cache. The owned fixture recreates its prefix when explicitly run again.
The actual Steam game prefix is untouched.

Source, installed compilers, CUDA environment, release libraries, all model
checkpoints, official replays, validation traces and backups remain. In
particular, keep `cache/rust-cross-0.46/lzokay-native-0.1.0/`: Cargo references
this source directory directly. `cache/gearbox-linux-0.37/` also contains source
and dependencies needed for builds, despite the `cache` name.

This cleanup's plan, preserved-file hashes and result are under
`local/cleanup/review-*/`. Prior cleanup records remain in
`local/cleanup/rollout-pruning-20261030.jsonl` and
`local/cleanup/rollout-pruning-summary.json`. Those earlier deletions are not
counted again. Documentation snapshots are in `backups/review-cleanup-*/`.

## Checks without starting the game or training

```sh
ctest --test-dir native/build-linux -R 'internal_physics_tick|internal_raw_hybrid' --output-on-failure
python3 scripts/test_immutable_staging.py
tools/venv-gpu/bin/python scripts/test_vector_physics.py
systemctl --user is-active tm2020-training-monitor.timer tm2020-internal-continuous-resume.service tm2020-discrete33-cuda-eco.service
systemctl --user is-enabled tm2020-training-monitor.timer
```

These historical-service checks should report `inactive` and the timer `disabled`; systemctl
returns a nonzero status for these expected stopped states. No start command is
part of the review procedure.
