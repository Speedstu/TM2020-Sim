# Code review — internal pipeline and PPO

The review pause has ended at the user's request; see `ROBUST_PPO_0_47.md` for
the original simulation-only continuation and `TIME_CREDIT_0_48.md` for the
current run and reward audit. Trackmania remains closed. Historical source
and experiments are retained so references and reproducibility remain intact.
This guide identifies the active path rather than moving interdependent files.

## Read the runtime first

1. `native/include/tm2020/internal_tick.hpp`: tick acceptance, duplicate/substep
   handling, policy cadence and latched neutral state.
2. `integrations/generalist-training/runtime.cpp` and `internal_hook.hpp`:
   physical-state ownership, exact client/prologue qualification, input writes
   before the consumer, new-race rebinding and shutdown on retired finish bodies.
3. `native/src/local_dll_loader.cpp`, `scripts/proton_sdk.py`,
   `scripts/run_internal_live.py`: explicit loader, immutable content-named
   staging, process/map qualification and STOP handoff.
4. `scripts/run_internal_trial.py`: qualification, reset, bounded local trial
   and evidence capture. UI reset uses XTest; the driving path is internal.

Check that a lost owner, wrong clock or invalid state stops commands, and that
detach neutralizes pedals/steering and restores the original consumer bytes.
The ordinary and explicit local process-writer setup paths are documented in
`INTERNAL_PIPELINE_0_46.md`; the exact executable hash and ownership checks are
part of their contract.

## Then review perception and learning

| Layer | Files | Review focus |
|---|---|---|
| Shared perception | `integrations/generalist-training/environment.rs`, `integrations/internal-perception/Cargo.toml` | Same map rays/history inputs in simulator and runtime; unqualified contact/turbo channels masked |
| CPU physics batch | `integrations/generalist-training/vector_physics.cpp`, `scripts/vector_physics.py` | Persistent workers, reset isolation, deterministic action boundaries |
| PPO experiment | `scripts/compare_hybrid_ppo.py` | Equal seeds/budgets/departures, binary pedals, continuous vs 17/33 steering, pure time reward, held-out evaluation |
| Export/inference | `native/include/tm2020/hybrid_actions.hpp`, `native/src/rl.cpp` | Signed-i8 steering, raw categorical argmax, input layout and deployment guards |
| Continuation | `scripts/resume_internal_continuous.py` | Checkpoint provenance, plateau stopping, optimizer/RNG restore and stop lifecycle |
| Optional optimizations | `scripts/cuda_history.py`, `scripts/gpu_ppo.py` | Confirm which runner uses each path; optimizer CUDA, physics CPU |

The historical continuous continuation runner deserves a lifecycle review before
reuse: its final save uses the loop variable `u`, which can count an update skipped
by an immediate STOP. The new `robust_ppo.py` runner instead tracks completed
updates explicitly, with stop/resume regression tests.
Resuming restores model/optimizer/CUDA RNG but creates fresh environments; it
does not promise a bit-identical continuation of partially completed episodes.
No training algorithm or runner was changed as part of the earlier cleanup.

## Evidence to inspect

The deployment export is `local/recon/deployment-0.46/candidate.tmppo`, with
provenance in `candidate.json`. Its SHA-256 is
`a9b2508ff232062784a8838fb29b2971e5dc9274968b4626bea0548d0f930443`.
It corresponds to seed 46602, continuous steering, update 16.

- `local/recon/internal-0.46/verified-live-result.json`: two continuous real-game
  finishes in 23.366 s, replay provenance, command readback and shutdown checks.
- `local/recon/internal-0.46/real-policy-comparison.json`: matched real-game
  continuous/17/33 results, plus explicitly separate extra trials.
- `local/recon/internal-0.46/live-control-proc-4/finish.Replay.Gbx` and
  `replay-info.json`: official replay, correct map UID and zero respawns.
- `local/recon/internal-0.46/ppo-comparison/protocol.json`, `summary.json`:
  matched seeds/budgets and 41 simulation departures per seed, with uncertainty.
- `local/training/internal-continuous-resume-20261030/status.json`: stopped
  later continuation, whose weights have not been validated in the real game.

These results establish this pipeline on this map. They do not establish a
perfect simulator, general map competence or robustness over many real-game
perturbed starts. Build manifests describe builds; a `gameFinishVerified` flag
in one build manifest does not replace a trial report tied to matching hashes.

## Existing focused checks

`native/tests/internal_tick_test.cpp`, `native/tests/hybrid_actions_test.cpp`,
`scripts/test_immutable_staging.py`, `scripts/test_vector_physics.py` and
`scripts/test_hybrid_export.py` cover the key contracts. The separate
`scripts/test_internal_windows.py` fixture recreates its disposable Wine prefix;
it is not needed to inspect source and does not launch Trackmania.

Recheck the selected weights in simulation and then in a bounded client trial
after any later training or runtime change. Keep the real-game validated
candidate separate from an improved simulator-only checkpoint. The old hourly
monitor remains disabled; no automatic training restart is scheduled.
