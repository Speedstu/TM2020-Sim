# Native research SDK 0.5.0 — 21 October 2026

Project: `H:\Projects\Trackmania2020-RE`. Development, tools, caches, source
archives and outputs stay on H:. Game installation files are unchanged.

## Reproduce

```powershell
cd H:\Projects\Trackmania2020-RE
./scripts/install-re-tools.ps1
./scripts/run-release-checks.ps1
```

The release command runs the existing 16 regression groups plus CTest,
current-build reflection extraction, native neural training, Rust lint and
Rust-to-C-DLL prediction. Installed SDK: `dist/sdk-windows-x64`.
Source archive: `backups/trackmania2020-re-source-0.5.0.zip` plus SHA-256.
Release results: `local/release-0.5.0.json`. Live qualification is separate;
passing offline tests does not certify race completion or exact physics.

## Structural reverse engineering

Portable radare2 **6.2.4** is installed under `tools/`. Its official Windows
archive is pinned to SHA-256
`aa3454fd89e8a4ead450caff35a1d3919065744e7091540d4913a9487241799d`.
No global installation, PATH change, game patch, or elevated service is used.

`scripts/reverse_reflection.py` disassembles registration functions at PE
exception-directory (`.pdata`) boundaries with Capstone. It tracks explicit
argument assignments and invalidates volatile registers at calls/branches.
Each extracted property carries its supporting instruction RVA and bytes.
It rejects any executable whose SHA-256 differs from:

`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.

The current extraction finds **386 class registrations and 1,705 direct
property registrations**. This is a bounded, conservative extraction, not
an assertion that every game class has been recovered.

The reflection entry points were independently inspected:

| Routine RVA | Observed behavior |
| --- | --- |
| `0x2ea9e0` | Records the class-name RDX and registered extent R8D |
| `0x2eb040` | Passes property-name RCX and offset EDX into the descriptor machinery |
| `0x2eb210` | Stores the offset argument at descriptor `+0x10` |
| `0x727520` | `IsGroundContact` getter reads `+0x88`, shifts 20, masks 1 |

radare2 independently decoded that getter; output is
`local/recon/r2-ground-contact.txt`. Full extraction:
`local/recon/reflection-current-build.json`.

`CSceneVehicleVisState` has registered extent **0x360** and **59 extracted
direct properties**, including:

| Field | Byte offset |
| --- | --- |
| InputSteer / InputGasPedal / InputBrakePedal | `0x10 / 0x14 / 0x18` |
| InputIsBraking | `0x20` |
| Loc.translation | `0x50` |
| WorldVel / FrontSpeed | `0x5c / 0x74` |
| Flag word: ground contact / engine / turbo | `0x88`, bits `20 / 23 / 24` |
| Wheel 0 suspension / rotation / rotation speed / steer angle | `0xa8 / 0xac / 0xb0 / 0xb4` |
| Following wheels | stride `0x2c` |
| CurGear / RaceStartTime | `0x1a4 / 0x1b4` |

The preceding rotation matrix at `0x2c` is checked for orthonormal rows and
determinant +1. Live turning trials compare its row/column heading hypotheses
against independently stored WorldVel. The column hypothesis received 100
votes versus 0 in a controlled native driving trial. This establishes a
useful **visual chassis heading convention**, not a physics-owner pointer.

The advancing word at `+0xc` is explicitly named a **clock candidate**.
It is useful to reject old buffered copies. Its monotonic 10 ms increments
do not prove the internal physics step or a deterministic stepping API.
The reflected `RaceStartTime` also separates buffers from different resets.
The playback diagnostic `--replay-clock` uses their difference to schedule
recorded inputs after a second ordinary restart; this is an experiment and
is not a measured physics callback or learned policy.

## Actual local-game integration

The new structural scan examined approximately **5,862 MiB** of committed
private memory and found **54 candidate visual buffers**. Earlier 768 MiB
numeric scans largely found stack/render copies and missed these regions.
Those old position hypotheses cannot be reinterpreted as complete visual
objects: the full-layout decoder correctly rejected them.

New Windows native modules:

- `read_only_live`: SHA/PID/creation-time guarded observation, disposable visual
  buffer discovery after resets, clock-aware selection, optional pose anchoring.
- `local_input`: keyboard scan-code control and analog Xbox reports using an
  existing ViGEmClient/ViGEmBus installation. Releases controls on scope exit,
  invalid controls, focus loss, process exit and Escape. No Python runtime.
- `tm2020_local_probe`: per-copy CSV with actual input, velocity, gear,
  wheel/contact fields and clock candidates for causal experiments.
- `tm2020_live_drive`: real-time reference-route controller with an experimental
  spatial replay feedforward option. Normal Delete-key reset, bounded discovery,
  clock/focus/lane guards and traces. It is not deterministic `step/reset`.
- `tm2020_local_dll_loader`: ordinary, visible-to-the-OS LoadLibraryW loading,
  x64 validation, forwarded loader/ASLR handling and full-path module validation.
  It first passes an owned-child-process fixture. No hooks, manual mapping,
  hiding, protection bypass or privilege escalation are implemented.

The local Solo context is a host/user assertion. Neither a foreground PID nor
the DLL bridge can independently prove that a race is offline.

Keyboard input demonstrably moved the actual car about **9.7 m**. Analog
gamepad probing also moved it about **13.8 m** and the reflected throttle
changed to 1.0. Process PID in these captures: **24592**; the manifests are
session-specific and must not be reused after a game restart.

A 28-second native follower trial produced **2,800 observations with zero
drops**, reaching **72.4% of the reference waypoint sequence**, with maximum
reference deviation **9.17 m**. A subsequent 65-second trial reached only
34.3% and became stuck against a wall. Do not report the best trial as a
repeatable completion rate. The matrix-heading trial also became stuck.
All trials, including failed ones, remain in `local/recon/codex-follower-*.csv`.
`local/recon/live-driving-qualification.json` summarizes all eight retained
controller traces, preserving failures and separating partial actuation from
an actual game finish.
There is no verified finish or competitive lap-time claim.
The spatial feedforward trial reached 60.4% and also became stuck. A diagnostic
trial before its startup fix remained at sample zero because the demonstration's
first input preceded acceleration; it is retained as a failed trial as well.
The subsequent clock-scheduled playback also became stuck and stopped on a
stale visual-clock guard. It is not counted as race completion. During release
qualification, an old same-PID pose manifest correctly failed its live coverage
test after these resets; normal restart and bootstrap refreshed the disposable
manifest before repeating the regression. A matching PID alone does not make
cached hypotheses fresh.

Example (after running the native map-start bootstrap in Solo):

```powershell
./native/build/tm2020_live_drive.exe --confirm-local-solo `
  local/recon/live-cpp-<PID>-v3.txt `
  local/campaign-2026-autumn/native-replays/4634.tmreplay `
  local/recon/my-trial.csv gamepad <absolute-ViGEmClient.dll-path> 30 40 -7.5
```

The ViGEm bus already existed on this computer. The tested client DLL is in
the existing vgamepad installation; a native dynamic loader calls it directly.
No driver was installed as part of this work. ViGEm is an archived upstream;
the backend is optional, not a new dependency for static SDK/replay/PPO use.

## Native ML and PPO

`tm2020/rl.hpp` and `rl.cpp` provide a dependency-free C++20 CPU learner:

- Actor and critic tanh MLPs; bounded tanh-squashed Gaussian actions.
- Stable squash-Jacobian log probabilities and stored latent actions.
- Time-major vector rollouts and GAE with distinct termination/truncation.
  A time limit bootstraps from the final observation, and never leaks an
  automatically reset episode into the preceding advantage estimate.
- PPO clipped objective, shuffled minibatches, Adam, global gradient clipping,
  approximate KL stopping and normalized advantages.
- Optional **latent Gaussian entropy** regularization. It is explicitly not
  the differential entropy of the squashed action distribution.
- On-policy identity checks before updates; finite-value and shape validation.
- Versioned `.tmppo` actor/critic models with observation-schema identity and
  corruption checksum. These are inference checkpoints, not resumable optimizer
  and RNG snapshots. The checksum detects corruption; it is not authentication.

Finite-difference gradient maximum error was about **4.3e-13**. The complete
PPO learner reduced a synthetic bounded contextual-control MSE from **0.2166
to 0.0055** in three updates. That is an algorithm test, not Trackmania skill.

`tm2020_ppo_warmstart` initializes the same actor from real demonstrations.
Its eight features use local reference-route points at 10/30/60 m, speed and
ground contact. It receives neither the evaluated car's future pose nor its
current steering label as input. Reference run 4634, fitting run 4902 and
held-out run 4754 are distinct; the model is selected using only an internal
split of the fitting run.

The same-map held-out steering MAE was **0.2531** for the neural actor,
**0.2446** for pure pursuit and **0.7425** for neutral steering on the same
raw-input labels. The neural actor is therefore not the preferred current
controller. Existing older metrics using replay-state labels differ slightly;
compare matching label definitions, not the two protocols interchangeably.

Real-game PPO collection/training and GPU training have not been validated.
The learner is usable through its C++ transition API; an unattended game
training adapter still needs robust reset/ownership/finish semantics.

## C ABI, Rust and injection boundary

`tm2020/policy.h` defines independent **policy ABI 1**, preserving the existing
game bridge **ABI 3**. Policies use independent immutable handles. Hosts must
check the full observation-schema string, not just its dimension. Close must
not race a prediction. C++ `predict_into` and C ABI prediction perform no
heap allocation in the inference path; Rust offers reusable output storage.

`rust/tm2020-sdk` has no Cargo dependencies. It dynamically loads the Windows
DLL, checks version/dimensions/schema, owns both the model and DLL lifetime,
and rejects non-finite inputs. It was built with the installed MSVC Rust
target and tested against the MinGW C DLL. The policy DLL statically links
its MinGW runtime so it also loads without relying on the compiler's PATH.

Loading the policy DLL into a game process establishes module loading only.
The existing C host can call prediction with trusted observations; this release
does not pretend that DLL loading discovers the game's simulation callback,
provides a reversible physics snapshot, or automatically runs the external bot
inside the game. Live loader results are recorded separately.

Actual qualification **succeeded in the running Trackmania process 24592**:
the policy module was loaded from `local/runtime/tm2020-policy-0.5.0.dll`, its
full path was independently found in the game's module list, and the exported
Windows-thread-compatible SDK probe executed there and returned **policy ABI 1**.
Module SHA-256:
`35534062d7bda52be59ba73798052737bb8a892068061374723d39396a5dd581`.
The installed game executable retained its original pinned SHA-256.
Only the temporary DLL-path allocation was written remotely; no game code or
physics data was patched. This qualifies native module/entry execution, while
the driving trials used the external C++ host. Evidence:
`local/recon/injected-policy-module.json` and `codex-game-dll-load.log`.

Reproduce explicitly in local Solo with a current pose manifest:

```powershell
./scripts/qualify-local-sdk.ps1 -ConfirmLocalSolo
```

The script preserves a runtime copy separately from the installable SDK, checks
its hash and reuses an already loaded identical module. The module remains
loaded until normal game exit; it does not start a background driving worker.

## Remaining research

Recover a stable player/physics owner across process restarts, callback/tick
and finish/reset semantics; improve repeatable completed laps; acquire actual
modern Stadium colliders and materials; validate native physics differentially.
The existing toy sandbox remains explicitly unfaithful. Full headless,
Trackmania-equivalent PPO training is **not ready**.

Primary references consulted: [radare2 releases](https://github.com/radareorg/radare2/releases/tag/6.2.4),
[PPO-Clip](https://spinningup.openai.com/en/latest/algorithms/ppo.html),
[time limits](https://gymnasium.farama.org/v1.2.3/tutorials/gymnasium_basics/handling_time_limits/),
[ViGEmClient](https://github.com/nefarius/ViGEmClient),
[TMRL](https://github.com/trackmania-rl/tmrl),
[TM2020-TAS](https://github.com/Polybagel/TM2020-TAS).
