# Internal PPO pipeline — verified in Trackmania

## Actual client result

Fall 2026-01, UID `ypPmohQofd72MyTsIsijKfrJH98`: the continuous PPO candidate
finished two nominal local trials in **23.366 seconds**, with no respawn in the
official replay. The second client result shows `+00:00.000` against that PB.
These are two nominal trials, not a real-game robustness or top-10 qualification.

Evidence under `local/recon/internal-0.46/`:

- `verified-live-result.json`: combined result, exact policy/runtime hashes,
  control readback, shutdown and explicit limitations.
- `live-control-proc-4/finish-proof.png`, `finish.Replay.Gbx`, `replay-info.json`:
  first client result and official autosave. Replay time 23366 ms, respawns 0,
  checkpoints/finish at 5526, 13364, 17450 and 23366 ms, matching map UID.
- `live-control-proc-4/physics-recovered.csv`: first successful run's physics
  trace, recovered after the initial finish-screen shutdown issue.
- `verified-trial-2/control/finish-proof.png`, `physics.csv`, `report.json`:
  second independent client run, exact same finish time, clean shutdown.
- `verified-trial-2/trial.json`: 7,396 internal consumer calls, exact command
  readback, no unexpected faults and normal worker detach.

The second trial made 527 policy decisions, with 207 distinct signed i8 steering
values. The engine continued physics for about three seconds after the finish.
After shutdown, gas/brake/steering were independently read back as zero and the
original 13 consumer bytes were restored. Following the user's code-review
request, Trackmania is now closed and all project trainers are stopped. The
driving hook is no longer active; the old hourly timer remains disabled.

## Internal execution

Supported client EXE SHA-256:
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.

The ordinary DLL loader checks this exact image before starting the explicit
worker. `runtime.cpp` reads physical state and runs perception/history/policy on
the game's consumer thread. No SendInput, virtual controller, external driving
service, expert route or MPC controls the car.

RVA `0x841500` has Win64 arguments `(manager: RCX, vehicle: RDX,
macro_timestamp_ms: R8D, interval: XMM3)`. Immediately before the original
consumer runs, the hook writes gas `vehicle+0x98`, brake `+0x9c` and steering
`+0xa0`. Derived steering at `+0x1430` is left to the game. Static audit evidence
is in `consumer-audit.json` and `consumer-audit.asm`.

The body is resolved from vehicle handle `+0x10`, manager mapping `+0xb0`, state
array `+0x70` and count `+0x78`; each rigid state has 88 bytes. The trace retains
R9, position3, quaternion4, world velocity3, angular velocity3, gear and command
readback. Gear `+0x15dc` and race-start timestamp `+0x12d8` were observed in the
actual client, rather than inferred from rendered positions.

The original body changes its integration interval with speed: actual samples
include 10, 5, approximately 3.333 and 2.5 ms. These substeps share one macro
timestamp. The controller holds one action across them and performs inference
once per five distinct 10 ms macro timestamps (20 Hz). Native tests cover
variable substeps, duplicate timestamps and invalid state/clock/owner/session.

Reset recreates the vehicle object in this client while retaining its manager
and physical body. A new object is accepted only on the previously qualified
manager/body, near the known start, in the first three seconds of a newer race.
Once armed, changing owner/body or losing valid state/session/clock neutralizes
the controller. This preserves strict ownership without rejecting normal reset.

Map rays and checkpoint tracking use the same Rust encoder compiled into
`tm2020_internal_perception.dll`. It runs in process and never places or advances
the client car. Tracker updates follow the physical substeps; rays/history/policy
run at 20 Hz. Contact/turbo channels remain unqualified, are masked in training,
and must have exactly zero actor weights at deployment.

## Explicit local test writer

The user authorized testing in the logged-in client on the local map, then
explicitly authorized a process-local workaround for its code-write refusal.
Network isolation remains the default; connected local Solo is an explicit
`--local-solo` mode, recorded honestly in the report.

VirtualProtect READWRITE/WRITECOPY and the Windows debugger-write API returned
Win32 error 5 in this client. The opt-in `--proc-debug-write` mode uses the
current Proton namespace's `/proc/PID/mem` through the DLL's file API. It validates
a per-instance memory nonce to reject a different process before any write.
The executable SHA and exact consumer prologue are also required. It changes
only the validated 13-byte consumer entry for install/remove, with the other
owned process threads paused and their instruction pointers checked.

Driving still occurs entirely inside the physical callback. This setup path
does not change global services, authentication or system security settings.
Trampolines/runtime remain pinned for the process lifetime because a thread may
be parked before its first callback counter increment. Contexts are freed only
after unpatching and callback drainage.

On normal stop, neutral is consumed on a physical tick. A finish can retire the
body and stop all such ticks. The stop-only fallback pauses other threads,
revalidates the bound body or explicit retired handle, clears the known command
fields, checks zero readback, then restores the consumer. This path was tested
in an owned PE image and exercised on the real client's retired finish body.

Files staged into the Wine prefix are immutable and content-named. Existing
files are hash-checked and never truncated or replaced: rewriting a loaded DLL
caused a client crash during development. New files are published without
replacing an existing inode. `test_immutable_staging.py` guards this regression.
The map is staged into the prefix too, avoiding Flatpak project-path visibility
issues.

## Matched PPO comparison

Three steering distributions share binary pedals, the same history-5/width-512
encoder prior, map, training seed schedule, perturbations, reward and PPO budget.
Continuous steering is a tanh Gaussian; discrete steering has 17 or 33 levels.
All use the game's signed i8 steering quantization. Discrete inference takes
argmax over raw logits before saturation.

The common prior is warm-started. Categorical logits derive from the same
Gaussian mean on the atanh steering grid; this does not establish a universal
advantage for any distribution. Reward v3 is pure minimum time: a finish earns
`100 - seconds`; failure costs the full 40-second horizon plus 100. Reward scale
is .01, gamma 1, lambda .995. No progress bonus, replay bank or expert controller
is used by this comparison.

Seeds 46601/46602/46603 ran 24/32/32 updates, each 16,384 transitions per arm.
The first seed stopped all arms together at a shared plateau. Total per arm:
1,441,792 transitions; total overall 4,325,376. Measured collection plus CUDA
optimization: about 7,611 policy decisions/s, with native CPU physics.

Held-out simulator cases: 41 common departures per seed, 40 early steering
perturbations plus one nominal departure. Reusing cases over three trained
seeds does not create 123 independent maps.

| Steering | Finishes | Mean | Median | Best | Mean with DNF = 40 s |
|---|---:|---:|---:|---:|---:|
| Continuous | 112/123 | 24.857 s | 24.439 s | 22.584 s | 26.211 s |
| Discrete 17 | 87/123 | 25.275 s | 25.018 s | 21.245 s | 29.585 s |
| Discrete 33 | 109/123 | 25.237 s | 25.348 s | 21.521 s | 26.917 s |

The first three time columns exclude failures; the last includes them. Checkpoint
selection uses development trials, not held-out results. The 17-level arm was
behind continuous in this experiment; the 33/continuous difference remains
inconclusive with the paired bootstrap intervals in `ppo-comparison/summary.json`.
The 123-trial statistics are simulator results, not real-game outcomes.

The actual client was also tested with matching seed 46602, update 16
(262,144 new transitions) and a 36-second trial budget on the same nominal reset:

| Steering | Actual finishes | Actual client time |
|---|---:|---:|
| Continuous | 1/1 | 23.366 s |
| Discrete 17 | 1/1 | 23.688 s |
| Discrete 33 | 1/1 | 23.488 s |

A separate continuous run reproduced 23.366 s. An exploratory seed 46601
discrete17 candidate finished in 25.536 s and is excluded from the matched table.
All five finishes have client result evidence. Only the first continuous finish
has its own archived official PB replay; the slower/equal runs did not replace
that PB autosave. Real-game samples are nominal and small, not a perturbed-start
robustness study or proof that one distribution is universally better.
See `real-policy-comparison.json` / `.md` for exact model hashes, traces and
screenshots. All final trial workers detached normally, with exact command
readback and no unexpected physics fault. Continuous remains the candidate.

The continuous deployment candidate is seed 46602, development checkpoint 16.
Its provenance is in `local/recon/deployment-0.46/candidate.json`. No unseen-map
strength or top-10 performance is claimed.

## Build and test

Private Zig, Rust cross tools and extracted MinGW already exist in this
workspace. The frozen engine source is unchanged.

```sh
python3 scripts/build_internal_runtime.py
ctest --test-dir native/build-linux -R 'internal_physics_tick|internal_raw_hybrid' --output-on-failure
python3 scripts/test_immutable_staging.py
tools/venv-gpu/bin/python scripts/test_vector_physics.py
tools/venv-gpu/bin/python scripts/test_hybrid_export.py
tools/venv-gpu/bin/python scripts/test_internal_windows.py --proc-debug-write
```

The Windows fixture uses its own Wine prefix and no game process. It checks
actual PE image patch/restore, full in-process perception/policy/consumer parity
for all three action heads, neutralization and shutdown without a future tick.
Vector physics matches individual physics byte for byte at sizes 1, 4 and 17.

## Run a local trial

Keep the same map open in the current client and start from its playable race
screen. This command observes and qualifies the current process, resets the
race, then runs the candidate. Only reset/menu input uses XTest; driving uses
the DLL's internal commands. Capture skips unrelated foreground applications.

```sh
tools/venv-gpu/bin/python scripts/run_internal_trial.py \
  --local-solo --proc-debug-write --capture --seconds 36 \
  --output local/my-new-internal-trial
```

Output must be new. Use `--model path/to/policy.tmppo` to choose a policy.
The report exposes the worker's STOP file; creating it requests neutral stop.
No timer or indefinite training is started. The trial helper deliberately does
not infer a finish from movement, an approximate goal volume or normal DLL
return: attach the actual client result/replay evidence, as in the verified runs.
