# Original-code scene training — research 0.31, SDK 0.26.0

The owned scene now supports a complete **bounded PPO collection, update,
checkpoint, resume and independent physics-audit cycle** through our native SDK.
The complete exact Trackmania simulator and general race-training fidelity remain
unqualified. This milestone has one source scene, one vehicle and short episodes.

## What changed

`native/src/owned_unicorn_guard.cpp` moves per-instruction and per-memory-access
validation out of Python. It attaches to the **same private Unicorn engine**;
Unicorn still executes original instructions. It does not inject, patch the game,
open a source process, replace physics with a learned approximation, or provide
a general native-CPU arbitrary-action executor.

Every executed instruction is checked against the separately pinned local image.
Only declared platform ABI entries are modeled. Source data reads require covered
bytes. Unmapped code/data, changed instructions and syscalls stop the episode.
The existing strict mode remains available. No missing source coefficient is
filled with zero or estimated from a replay.

Optional `--initialize-writes` tracks bytes produced by execution. A full store
makes its written bytes readable; a partial store leaves the other bytes unknown.
This also applies to the explicit host control and platform memory adapters.
It does not make an untouched source byte readable. Generated-byte masks travel
with checkpoints and are cleared on reset. Instruction/data guards remain active.
Unknown reads in owned allocator arenas also stop execution; the whole reserved
arena is not silently accepted as captured input.

Fourteen adversarial guard cases cover unknown reads/writes, cross-page accesses,
changed or unknown executable bytes, partial initialization, initialized-byte
restore, scratch accounting, and collection of engine/callback ownership cycles.
Both strict and generated-byte modes pass the retained 131-frame source-vehicle
branch/reset/rewind check, including all checkpoint pages and failure recovery.
Those 131-frame checks use the earlier source424 control cohort; they are not a
claim that every state of the new training fixture has been checkpoint-tested.

The 500-tick source-velocity reference still matches every observed frame and
every final data page. A measured guarded replay took **22.28 s**, compared with
the earlier Python replay's **674.99 s**. The current 131-frame strict check took
4.91 s, compared with its historical 211.94 s. These are observed runs, not a
hardware-independent throughput guarantee. Native fixed-reference execution is
still substantially faster than guarded arbitrary-action execution.

## New input coverage and reverse evidence

Four read-only source-backed captures exercise 300 ticks each:

| Plan | Owned controls |
|---|---|
| coast | 100 ticks full throttle, then 200 neutral |
| brake | 100 ticks full throttle, then 200 brake |
| left | 300 ticks throttle plus full negative steering |
| right | 300 ticks throttle plus full positive steering |

They preserve the source rigid/vehicle velocity, observed model activation, fixed
10 ms interval and selected scene pipeline 4. All four reproduce in guarded
Unicorn and original-code native CPU execution. Each native reference also passes
100 reset episodes. Additional short captures follow the exact rejected PPO
action histories, not a guessed replacement trajectory.

The final numeric fixture is:

`local/recon/rest-history-training-canonical-v5/owned_control_schedule.tmstep`

SHA256: `0452595c3a7d1f4c76163d54b26553e4cb69acfcddce83596b78262a7f16e0ed`.

It contains 336 sparse data pages and adds **20,813 covered input bytes** relative
to the retained rest500 fixture. Of these, 600 belong to explicit synthetic
runtime arenas and 20,213 are outside those arenas. This distinction matters:
owned runtime initialization is not a live game's atomic heap snapshot. The
source address space also contains explicit owned preparation fields. The byte
count is not a count of newly recovered physical coefficients.

`reverse_owned_frontiers.py` pins the rejected instructions and offsets. Examples
include configuration `+0x17a8`, `+0x1d5c`, curve dependencies near `+0x1ebc`, and
vehicle state writes/reads in the original `0x84de60` routine. The direct constant
at RVA `0x1d1f2ac` is binary32 **0.75**. The dependency at `0x1d21c20` is part of a
vector XOR operand, so treating its first four bytes as the whole operand is
insufficient. Physical units and semantic names are not inferred from offsets.

The canonical reference family covers 12 retained sequences and **204,000 repeated
native frame comparisons** across their 100 resets. Repetitions of a fixed
sequence are not independent action histories. The earlier 2.2-million comparison
family remains historical evidence with its original scope.

The broader 20-plan scout improved from 0/20 complete plans and 2,111 accepted
prefix ticks to **10/20 complete plans and 4,348 accepted prefix ticks** in its
recorded expanded cohort. Its remaining rejection addresses are retained. That
scout uses the canonical-v4 fixture in strict mode, not the final training mode;
it is not evidence of a continuous, fully covered action domain.

## Native PPO SDK and actual training

`tm2020/trainer.h` adds a handle-based C ABI in `libtm2020_policy.dll`:

- sample a decision and retain its exact latent, behavior likelihood and value;
- commit it only after a valid successor observation;
- cancel a failed decision without fabricating a transition;
- truncate the last accepted prefix while retaining its observed bootstrap;
- export accepted rows for an independent behavior audit;
- update PPO and save/resume the policy, Adam, configuration and both RNG streams.

The inference ABI stays at version 1. The new trainer ABI has its own version 1.
The source library version is **0.26.0**. C++20, C ABI and the existing game bridge
remain separate layers. A loaded training DLL is not itself a game hook.

`train_owned_scene.py` uses the SDK's C++ actor-critic/PPO and the guarded original
scene. It uses 13 state observations and 3 latent actions. Drive and brake are
affine mappings to `[0,1]`; steering stays in `[-1,1]`. Each decision holds controls
for 5 original ticks. Observations encode relative position, quaternion and linear
and angular velocity. This is a partial observation, not a proof of a Markov state.

The explicit experimental reward is displacement along world axis `(0,0,-1)`.
It is not lap progress, checkpoint completion, or a general race objective.
An unknown access discards the pending decision, including any incomplete
five-tick window; it cannot become a reward or terminal observation.

The final retained run has four PPO updates, **320 audited decisions**, and all
16 requested one-second episodes complete. A checkpoint resume adds one update,
**40 audited decisions**, and two more completed episodes. The resumed behavior
model is byte-identical to the preceding exported model; optimizer steps continue
from 64 to 72. Thus this milestone has **360 decisions / 1,800 physics ticks /
18 completed short episodes**, independently replayed.

Two complementary audits check the accepted data:

1. `tm2020_rollout_audit --multiple-episodes` reloads the behavior model and
   recomputes every retained likelihood and value for all three actions.
2. `audit_owned_ppo_rollout.py` re-executes every accepted control history, checks
   before/after observations and trace hashes, recomputes displacement rewards
   and successor values, and checks every truncation and duration. Bootstrap
   maximum error is zero in both final runs.

The collector's recorded guard digest and the current replay guard digest can
differ after a guard ownership/cleanup fix. The original trajectories are
independently reproduced with the current guard; this is not an assertion that
the collector binary was unchanged.

Deterministic evaluation performs no updates and repeats each policy/baseline
twice from reset. All four traces are repeatable and complete:

| Controller | One-second forward displacement |
|---|---:|
| initial PPO | 3.320556640625 |
| trained PPO | 3.491455078125 |
| neutral | 0 |
| full throttle | 7.81103515625 |

The PPO improves this local scalar by 0.1708984375, but full throttle remains
better. There is no claim of stronger racing, unseen-map generalization or an
improved injected bot. This 13-observation/3-action profile is different from the
existing injected route follower's encoder; model files must not be interchanged
on dimensional similarity alone. No Openplanet runtime is used.

## Validation, reproducibility and limits

All **36 CTests** pass. The installed SDK under `dist/sdk-windows-x64` includes
the trainer header, policy DLL and compiled guard. An external MinGW CMake
consumer finds SDK 0.26, links it and executes trainer creation/sample/cancel.
The installed header/DLL hashes match the built artifacts. The C++ static
library consumer uses the matching MinGW toolchain; a default MSVC consumer is
not an ABI-compatible test of the MinGW C++ library.
The bundled Rust inference crate remains at version 0.25.0; the new trainer
interface is exposed through C/C++, without a new Rust trainer wrapper.

```powershell
python scripts/verify_owned_training_sdk.py
./scripts/run-owned-training-checks.ps1
python scripts/audit_owned_training.py
python scripts/snapshot_owned_training_evidence.py
```

The final training reports are under
`local/recon/owned-ppo-rest-history-canonical-v5` and its `-resume` sibling.
The consolidated gate is `local/recon/owned-training-milestone-audit.json`.
Image hashes, the captured Windows module cohort and private numeric fixtures
remain necessary. The evidence bundle excludes game/OS images, raw code pages,
private snapshot archives and compiled game-derived native fixtures.

During development, two short captures inherited constant descriptors but did
not serialize constants unvisited by the shorter branch. Verification rejected
those fixtures. They remain as negative evidence in `rest-ppo-initial-gap` and
`ppo-frontier-source-v3`; neither is in the canonical reference family. The
serializer now retains explicitly pinned constants and verifies the completed
archive before reporting success. The corrected ten-tick capture and all
canonical contributors pass image/constant validation and native comparisons.

Complete world/map initialization, an atomic simulation-stage capture, the full
outer scene `0x12e9ea0`, all collision/surface/tire-slip histories, other vehicles,
raw player input ownership and a validated general race objective remain open.
The selected scene sequence is not the full game tick. General arbitrary-action
native CPU execution, general RL fidelity and the complete exact autonomous
Trackmania simulator remain explicitly **false** in the capability gates.
