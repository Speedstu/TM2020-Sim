# Asset-loaded headless backend, research 0.33

Measured on 2026-10-28. SDK release remains **0.26.0**. Full exact simulation of
every game mode, car, contact and platform path is **not qualified**. A general
race-winning learned policy is **not qualified**.

## What runs

A standalone Rust process loads a map and physics assets from the installed
game, initializes a race, and advances native 10 ms physics ticks without a
running game or sparse process snapshot. Our Python Gymnasium environment
communicates with it through local JSON standard input/output. Our own C++ PPO
trainer/inference DLL supplies the policy. No Openplanet runtime is involved.

The physics implementation and asset loader are upstream
[Mergemat/gearbox](https://github.com/Mergemat/gearbox/tree/e0583ee55168e950a65a645778e591bd26b6a0f2),
copyright Bagautdin Omarov and contributors. They are **not newly recovered
physics written by this project**. The host, replay comparator and asset
inspector are GPL-3.0-or-later; see
[NOTICE](../integrations/gearbox-host/NOTICE.md) and its LICENSE. The revision
and dependency checksums are fixed in Cargo.toml/Cargo.lock. Game assets stay
in the user's local installation and are not included in source/evidence ZIPs.

The existing original-code/Unicorn backend remains separate. Its independent
100-tick live rigid/force oracle does not establish this Rust engine's bit-level
equivalence. Conversely, cold world loading here does not remove the captured
working-set limits of the Unicorn backend.

## References from the original game

`gearbox-game-replay-comparison-v2` and `gearbox-game-corpus-comparison-v1`
examine **23 recorded game replays**, including three independent Autumn 01
drivers. **21 finish times across 19 maps match exactly to the millisecond**.
Twenty of those 21 checkpoint histories also match. Replay 4573 contains a
recorded first checkpoint of -171 ms versus the simulated 3,694 ms; subsequent
checkpoints and its finish match. This discrepancy is retained.

Raw equal-timestamp visual positions have a systematic error (up to
4.173 metres in some fast runs). `Session::step` increments its clock after
executing a tick. Comparing a recorded position at `t` to the fixed post-step
state at `t+10 ms` gives a maximum residual of **0.000998404 m** over the 21
matching runs. The offset is declared, never fitted independently per replay.
This remains a **timestamp-semantics hypothesis**. Visual samples are quantized
and do not expose complete wheel, constraint or internal rigid-state bits.
Neither the sub-millimetre residual nor exact finish times prove bit-exact
physics for arbitrary inputs.

The two excluded cases are explicit:

- Replay 4628 names **BayCar** in both map and recorded ghost. Upstream supports
  CarSport, CarSnow, CarRally and CarDesert, and rejects this car.
- Replay 4852's input stream begins at **21,600 ms**. It cannot reconstruct a
  cold race from the start. The initial exploratory padding produced a large
  divergence, retained in the corpus report. The comparator now rejects a
  positive-start partial history rather than substituting a neutral prefix.

Upstream's five golden traces pass (12,060 states), but their engine label is
`current (synth)`. They are self-regressions, not independent game oracles.
Upstream also contains unsupported `todo!` branches. Host panics fail the
command and require reset/restore; no replacement forces or geometry are used.

## Actual asset values

`inspect_assets` decodes **52 tuning sets** from four installed vehicle files:
Sport 28, Snow 1, Rally 11, Desert 12. The raw GBX and full decoded structs are
retained only under `local/recon/installed-vehicle-assets-v1`. This includes
spring, tire/material curves, engine/gears, force geometry, water, impacts and
post-step parameters. The public names/interpretations come from Gearbox;
independent differential qualification of every field remains separate.

For the selected Sport asset (active tuning 27), the decoded values include:

| Upstream field | Decoded value |
| --- | ---: |
| body mass | 1500 |
| body substep distance | 0.30000001192092896 |
| suspension kind | 2 |
| suspension stiffness parameter | 40 |
| suspension damping parameter | 1 |
| suspension rest length | 0.20000000298023224 |
| maximum speed parameter | 277.77777099609375 |
| air linear drag | 0.029999999329447746 |
| ground / air gravity multipliers | 3 / 2.5 |

The cold race manager gravity is `[0,-10,0]`. These raw parameters have their
upstream meanings; e.g. suspension stiffness is not asserted to be an SI
spring constant. Body mass 1500 and `Tuning.mass` 1 are different fields.
Serialized GBX.NET defaults such as mass 800 are not active race values.

Thirty-five public research/schema text files are retained with exact Git blob
SHA-1, source commit and SHA-256. Twenty numeric claims in the public TM2020 RE
table match typed bytes in our SHA-pinned executable (18 floats, two integers).
A byte match does not prove the claimed use of the constant. Sources include
[GBX.NET](https://github.com/BigBang1112/gbx-net/tree/2ca9f91000391def413b81a8de2e791fe0e85506)
and [Kelvination/TM2020](https://github.com/Kelvination/TM2020/tree/700aa88fc99d64dcaa7ad574146614def6c40a45).
Trackmania Forever projects found in the search are recorded as different
games; their values and offsets are not imported as TM2020 facts.

## Gym and native PPO

The policy receives **233 binary32 observations**, including physical state,
wheel state and upcoming checkpoint/road geometry. Its action schema is
`tm2020_gearbox_geometry233_v1|actions=unit_pedals_steering3_v1`.
The native tanh outputs are cast to binary32 by Gym, then mapped to
`gas=(a0+1)/2`, `brake=(a1+1)/2`, `steer=a2`. The engine consumes binary32
pedals in [0,1] and steering in [-1,1]. Input quantization is explicit.

Rewards use actual engine checkpoint/finish events: +10 per passed checkpoint,
+100 for finish, -0.0002 per advanced tick, and 0.01 times goal-distance
reduction while the checkpoint set is unchanged. This is a declared training
objective, not a racing-strength guarantee.

The 128-unit native PPO experiment completes 16 episodes, four updates,
**8,000 transitions / 40,000 physics ticks** on two maps. A separate resumed
checkpoint adds **1,000 transitions / 5,000 ticks** and preserves optimizer
state. A fresh host rebuild produces identical seeded models. Every accepted
trajectory is independently re-executed from a cold map instance; state hashes,
float32 actions, rewards, observations, durations, boundaries and critic
bootstrap values match. Native rollout audits recompute all behavior
likelihoods and values. This checks training integrity under the chosen engine.

**The resulting PPO policy regresses.** Deterministic evaluation on three maps
finds one finish for the configured initial policy and none for the updated
policy. A native imitation initializer trained on one Autumn 01 replay, with
a separate validation replay and final test replay, lowers supervised error
but also fails closed-loop races. Both candidates are retained as negative
results and are not promoted or injected. The initial policy is configured,
not learned. A finish under fixed full throttle is a physics/race smoke test.

Gymnasium's official `check_env` passes. Additional integration tests verify
the 17,406 ms full-throttle finish, its one-tick final partial repeat, rejection
of further steps, and truncation after exactly 5+2 ticks for a seven-tick
horizon. Three maps pass cold loading, checkpoint/future replay, reset,
repeated-rollout equality and four rejected-command/no-mutation checks each.
The native suite passes **41/41 tests**. Full qualification is audited by
`scripts/audit_headless_milestone.py` and remains false.

## Reproduce locally

Prerequisites: installed Trackmania Packs, Rustup with the MSVC linker/Windows
SDK, MinGW/CMake for this native SDK, and Python. Rust 1.99.1 was used. A
task-local RUSTUP_HOME avoids the relocated cross-volume global rustup issue.

```powershell
.\scripts\build-headless-backend.ps1 -InstallPythonDependencies
.\scripts\run-headless-checks.ps1 -Output H:\Projects\Trackmania2020-RE\local\recon\new-headless-run -Train
```

The default test maps refer to the pinned upstream checkout and the existing
local Autumn map. When restoring only sources, supply your own `-Maps` paths
and `-Packs` installation path. The host build fetches its Git dependencies at
the fixed revision. Clone the upstream checkout explicitly if its public test
maps are desired. Output folders must be new; evidence is never overwritten.

```powershell
cache\gearbox-host-target\release\inspect_assets.exe D:\SteamLibrary\steamapps\common\Trackmania\Packs local\recon\new-asset-inspection
cache\gearbox-host-target\release\replay_audit.exe D:\SteamLibrary\steamapps\common\Trackmania\Packs local\recon\new-replay-check local\replays\tmtas-4634.Replay.Gbx
```

The 233-observation policy cannot be loaded into the existing live follower's
8-observation/1-action interface. Matching authoritative live observations and
actions, supported full-race evaluation, broader car/surface coverage and
independent physical-state oracles remain completion criteria. The existing
native injection SDK is unchanged; there is no paid Openplanet dependency.
