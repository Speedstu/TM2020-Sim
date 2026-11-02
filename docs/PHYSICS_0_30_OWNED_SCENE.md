# Owned original-code stepping and scene continuation 0.30

The exact complete Trackmania simulator is still unqualified. This continuation
adds reproducible restart discovery, fresh pedal/steering captures, native
episode reset, guarded interactive stepping and the missing original
body-to-vehicle pose synchronization. It does not establish complete tire
contact regeneration or readiness for faithful autonomous PPO training.

## Verified changes

The original main step `0x7bd0e0` reproduces a **300-tick mixed command sequence**
in Unicorn and native x64. The sequence contains acceleration, braking,
release, and both steering directions. **1,000 resets reproduce all 300,000
typed frames bit for bit**. One typed frame includes the entire 88-byte rigid
state plus all observed vehicle/accumulator bytes. This repeats one frozen
episode; it is not 1,000 independently sampled driving situations.

Native reset restores the captured numeric pages, reconstructs owned TLS,
resets the allocation registry, time and MXCSR, and decommits/recommits all
**150,994,944 bytes** of synthetic scratch/heap arenas. Restoring only sparse
pages would leave old unobserved scratch bytes. Throughput reports include
reset, reference comparison and progress output, exclude binary loading,
and describe these fixed traces only. They are not general RL throughput.

Fresh capture supplies the previously missing configuration `+0xc80` binary32
value **3000.0**, alongside observed `+0xc4c=11000`, `+0xc7c=6000` and
`+0xc88=11500`. Units and unvisited parameter branches remain unverified.
The old failed pedal experiments in 0.29 remain negative historical evidence;
fresh source capture now qualifies this particular 100-tick pedal schedule.

A same-seed comparison first differs physically at **tick 26**, when the
pedal pulse switches from acceleration to braking. The first 25 rigid frames
agree. Maximum position separation is **2.661437 m**, maximum linear-velocity
separation **8.052847** in state units. This shows physical responsiveness
within the constructed scenario, not complete tire/traction fidelity.

## Scene ordering and the stale vehicle pose

Instruction checks pin this scene order in `0x12e9ea0`:

1. Collision-world `0x2a6360`, `0x2a6960` and vehicle preparation `0x1501f00`.
2. Main step `0x7bd0e0` at call site `0x12eb053`.
3. Collision-world `0x2a9b50`, manager `0x7bfcb0`, contact dispatch `0x7d2b90`.
4. Vehicle update `0x1501f50`.
5. Later body-to-vehicle synchronization `0x7d2cf0` at `0x12eb2b7`.

These are selected procedures from a larger scene update. Other intervening
scene calls are not covered; this is not a port of `0x12e9ea0` in full.
Native fixture **version 7** carries an explicit, bounded scene-pipeline
selection and captured receivers. Earlier versions 3/4/5/6 remain supported.
The supported pipeline selections retain the successive experiments:

| Selection | Added procedures around the original main step |
| --- | --- |
| 1 | Three post-step contact/query procedures |
| 2 | Selection 1 plus vehicle preparation and vehicle post-update |
| 3 | Selection 2 plus original body-to-vehicle synchronization |
| 4 | Selection 3 plus collision-world query begin/update |

The earlier main-step-only and selection-2 traces move the rigid body while
vehicle `+0x12e0..+0x1310` retains the initial pose/velocities. Calling the
original **`0x7d2cf0`** closes that gap: quaternion, XYZ position, linear and
angular velocity, **52 bytes per frame**, now match the rigid state exactly
for all 100 retained frames. Selections 3 and 4 each pass **100,000 native
frames over 1,000 resets**, with full guarded offline replay.

## Wheel contact interpretation and the remaining gap

The four words `+0x17b4 + wheel*0xb8` are consumed by the wheel/engine update,
then cleared by `0x8427d0` before it returns. **Zero at the step boundary does
not prove zero during the force calculation.** Probes at the entry of
`0x8447b0` resolve this timing: the main-step-only 300-tick fixture has four
nonzero wheel flags at its first engine update, then zero at the remaining
299 updates. Neither `0x843920` nor the contact adapter `0x1500140` executes
in that reference sequence.

Static reverse connects adapter `0x1500140` to absorber `0x840890`, and then
to wheel contact procedure `0x843920`. The final audit records their actual
entry counts for each extended pipeline, rather than inferring tire contact
from a changed trajectory or from flags after clearing. Scene selections alone
must not be described as a complete regenerated tire contact loop. The source
activation flags are essential, as the next section establishes. Full scene
context, arbitrary actions, complete map coverage and independent comparison
with actual in-game ticks remain open.

## Correct source integration branch and actual tire contacts

The fresh source has **model `+0x50 = 1`, source flags `64`**. The former
constructed active prototype changed these to model word zero and flags with
bit 3 set, forcing a different path. Its native/emulator comparisons remain
valid comparisons of that constructed experiment, but they cannot establish
the game's normal vehicle integration path.

In `0x1501800`, the original `0x7f4780` fixed-body test selects a separate
vehicle integration loop. That loop performs force update `0x14ffee0`, pose
integration `0x14ff9d0`, and collision/contact processing `0x15009d0`, including
adapter `0x1500140` and absorber `0x843920`. It can subdivide a tick based on
motion; a single generic dyna step is insufficient to reproduce it.

`--source-body-activation` restores those **observed source values** in owned
memory, with provenance for the changed seed bytes. The first 100-tick pedal
sequence executes **101 vehicle force/pose substeps**, **101 contact adapters**
and **269 wheel-contact absorber calls**. The engine update observes nonzero
wheel contact flags on **77 of its 101 entries**. This closes the disappearing
contact problem in this retained scenario. It does not prove every
tire/slip/surface/vehicle domain.

This source-activation sequence passes 100,000 native compared frames over
1,000 complete resets. The audit checks per-frame substep intervals and their
total 10 ms duration, source activation provenance, pose synchronization and
executed contact paths. It reports the extended 300-tick mixed-control source
sequence separately from the earlier constructed sequence.

The 300-tick source-activation trace now also passes strict offline comparison
of every observed frame and every retained final page. It executes **301**
force/pose/contact substeps and **744** wheel absorbers, with nonzero contact
flags on **279/301** engine entries. Together the five retained scene
experiments account for **900,000 native reset frames**, checked by
`audit_owned_step_continuation.py`. The 131-frame interactive qualification
below belongs to the earlier constructed dynamic-body pair; it does not
qualify arbitrary actions on the source-activation path.

## Additional action inputs after restart

The action-grid audit on the old source-activation capture retained **6/27**
successful initial branches and rejected the other 21. These failures are
preserved in `owned-source-action-grid.json`. Diagnostic execution identifies
configuration `+0xb24` as an unobserved curve ordinate read by original
interpolator `0x42bcb0` at instruction `0x42bd9a`; another initial braking
combination reaches configuration `+0x1d5c` through original `0x84de60`.
These are concrete data-coverage gaps, not evidence that the physical result
of those rejected steps is correct. Stack call-site candidates are checked
against decoded call instructions but are not a fully unwound call stack.

`capture_owned_action_inputs.py` captures all 27 initial combinations in
private emulators using a fresh, same-process seed. Its
`--normalize-initial-controls` option preserves the seed's initial control
record and applies the requested action before the tick, allowing strict
initial-state comparisons across branches. `merge_original_step_inputs.py`
rejects foreign processes/bindings, unrelated seeds, contradictory observed
bytes and conflicting code-data overlays. It adds only contributed observed
inputs and preserves the primary reference trace. Added final-page bytes
are explicitly derived as unchanged because the primary execution never
read or wrote them; independent full replay is required afterwards.

The fresh process-424 pedal capture independently passes strict offline
100-frame/all-page comparison and **100,000** native reset frames. It is a
new address cohort and is never mixed with process 21688's numeric inputs.
Its observed activation flags are **0**, with the same model word **1**;
the older capture's flags **64** are not imposed on this new process.

The completed 27 source captures add **16 observed configuration bytes** to
the fresh mixed-command reference. The four binary32 words are:

| Configuration offset | Stored bits | Observed value | Original consumer |
| --- | --- | --- | --- |
| `+0xb24` | `0x3dcccccd` | 0.10000000149011612 | Curve interpolation `0x42bcb0` |
| `+0xb2c` | `0x3fc00000` | 1.5 | Curve interpolation `0x42bcb0` |
| `+0x1d58` | `0x41a6aaab` | 20.83333396911621 | Threshold in `0x84de60` |
| `+0x1d5c` | `0x40400000` | 3.0 | Threshold in `0x84de60` |

These are values for this vehicle/configuration cohort. Units and complete
semantic field names are not established by this capture. The union's
300-tick native reference still matches over 1,000 resets after the additions.
Strict offline, alternative-branch and complete grid checks are separate
qualification steps.

Those checks now pass: the fresh union reproduces all 300 strict offline
frames and all retained final pages; **131** source-vehicle interactive frames
verify braking, checkpoint replay and recovery; **27/27** initial action
branches pass the coverage guard and **54** native reset comparisons.
`owned-input-coverage-audit.json` ties these to the same source cohort,
contributors and unchanged primary trace. Its three fresh native references
total **700,000 repeated frames**, in addition to the earlier 900,000.
This finite grid is one initial state and does not qualify a continuous
action domain or arbitrary long rollouts.

## Portable original substep arithmetic

`select_vehicle_substeps` in `recovered_step.hpp` ports the arithmetic slice
`0x1501b57..0x1501bd7`, with its single-step exit at `0x1501ce4`.
The caller supplies the already computed motion numerator and model limit.
The original divides them in binary32, truncates to an integer, adds one and
clamps the count at **1,000**. Repeated intervals divide the unscaled interval
first and multiply by the vehicle time scale second. The final interval is
the original accumulated residual after repeated binary32 subtractions;
replacing it with the repeated interval changes results at large counts.

The timestamp coefficient at pinned `.rdata` RVA `0x1d1fe58` is **-1e9**.
The original converts the unscaled float interval to double, multiplies by
that negative coefficient, truncates to signed 64 bits, then subtracts that
signed quantity from its timestamp. The port preserves this convention.

`oracle_vehicle_substeps.py` compares **20,000** generated cases with the
unchanged original selector instructions, including **8,064** clamped cases
and **13,639,116** original residual `SUBSS` executions. The residual repeats
that unchanged instruction inside an explicitly owned loop scaffold; it does
not claim to execute the complete original scene loop. Bounds are motion
`[0,1e9]`, limit `[1e-6,1e6]`, ratio at most `1e6`, scale `[1e-4,100]` and
interval `[1e-6,1]`. Invalid inputs are rejected. Pointer ownership, tire
updates and contact dispatch remain outside this arithmetic slice.

`scaled_vehicle_substep_motion` additionally ports the preceding
`0x15019f7..0x1501b52` arithmetic: lengths of the linear/angular velocity
vectors and vehicle record vectors `+0x1348`/`+0x1354`, their ordered sum,
and multiplication by `(time_scale * interval)`. All four vectors use
finite components within +/-10000. A further **20,000** unchanged-instruction
cases match bit for bit, including signed zeros and subnormal inputs.
An overload composes this numerator with the verified selector. The model
lookup, pointer validation and complete scene scheduler remain separate.

## Observed near-stationary start and five-second continuation

The source-velocity mode now retains an initial velocity of approximately
`[0.00835334, 0.000171762, -0.0000000301457]`, together with the source pose.
It applies explicit throttle commands in the owned scene. The 100-tick trace
and its same-seed **500-tick** continuation both pass strict offline checks of
every observed frame and every retained final page. The first 100 shared
frames and all common initial input bytes also agree between the captures.

The five-second continuation executes **794** original vehicle substeps and
**3,124** wheel-contact absorbers. The engine sees grounded wheel flags on
all **794** update entries; individual wheels need not all be grounded.
The native runner reproduces the complete 500-tick trace across **1,000**
resets (**500,000** compared frames). A further 100,000 native frames validate
the shorter source-velocity trace. These are repetitions of two retained
episodes, not 600,000 independently generated driving states.

The portable selector is additionally checked against the actual inputs and
executed interval counts of **all 500 scene ticks**, beyond its generated
cases. This establishes the composed arithmetic for this episode; it does
not qualify every collision placement, vehicle, surface or action history.
The complete audit families account for **2,200,000 native reset frames**
plus 54 finite-grid comparisons. Capture remains non-atomic and selected
outer-scene calls remain incomplete. Faithful general PPO training is not
qualified by these bounded results.

## Restart and source provenance

`tm2020_manager_discovery --discover original.exe new-report.json 6144` uses
read-only memory access and the pinned force callback `base+0x8427d0` to
identify coherent manager/item/vehicle bindings after restart. It validates
the registered force-context manager backlink, managed-vehicle span,
item-ID lookup, configuration, rigid quaternion/matrix and array bounds.
It does not assume the first vehicle pointer is the registered force context.
The owned self-test rejects seven broken pointer graphs and accepts a nonzero
item ID independently of ID zero. Discovery does not identify an authoritative
player object or prove a permanent static root.

`capture_original_step.py --source-binding report.json` pins process creation
identity, module/file hashes and typed pointer relationships before/after
capture. `--initial-fixture seed.tmstep` preserves known observed initial
inputs; newly visited working-set bytes come from the same still-running
source process. **This is non-atomic**, and is not a complete serialized world.
The initial active experiments intentionally set velocity to `[0,0,30]` and select
serial execution. Earlier experiments additionally forced dynamic activation;
the source-activation experiments preserve the observed model/flags.
These are not untouched in-game runs.
All source access is read-only; original execution occurs in private memory.
New `--preserve-source-velocity` captures retain the observed rigid/vehicle
velocities instead of this constructed push. A forced-velocity fixture cannot
seed that mode. It still uses serial execution and the explicit owned timebase.

## Interactive owned backend

`owned_step_machine.py` factors the strict execution core out of the reference
replayer. It supports `step([drive,brake,steering])`, `reset()`, `save()` and
`restore(checkpoint)`. Checkpoints preserve CPU/TLS/stack, captured data,
touched synthetic pages, timing and modeled heap allocation state. An unknown
data byte or unvalidated instruction stops the episode; no observation is
returned until reset or restoration. Commands are finite scalars in [-1,1],
with steering applied at vehicle `+0xa0`. Raw keyboard/gamepad decoding remains
separate and unqualified.

The differential checks **131 interactive frames**: a checkpoint at tick 25,
continuation/replay through tick 60, an alternative braking branch compared
with an independent retained trace, reset, invalid inputs, and recovery from
a rejected unobserved input. Every checkpoint page is also compared. The
native executor remains a reference-trace runner; arbitrary native actions
do not yet have this byte-level coverage guard.

The JSON-lines entry point permits a local client to operate the guarded
backend without a running game or Openplanet:

```powershell
python scripts/serve_owned_step.py --exe D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe --fixture local/recon/main-step-fixtures-source424-input-union/owned_control_schedule.tmstep
```

Requests are `{"id":1,"op":"reset"}`, `{"id":2,"op":"step","controls":[1,0,0]}`,
`{"op":"save","name":"branch"}`, `{"op":"restore","name":"branch"}`,
`{"op":"drop","name":"branch"}` and `{"op":"close"}`. The service is local
stdio only; it supplies no invented reward or claim of full training fidelity.
It still requires the pinned original image, captured numeric inputs and the
captured Windows module cohort. The Python guarded backend is an inspection
backend; its speed is far below the native reference runner.

## Reproduce

```powershell
./scripts/run-owned-step-checks.ps1
./scripts/run-owned-input-checks.ps1
./scripts/run-vehicle-substep-checks.ps1
./scripts/run-preserved-velocity-checks.ps1
./scripts/run-ghidra-physics.ps1 -ResearchSet wheelpipeline
python scripts/audit_owned_step_continuation.py
python scripts/snapshot_owned_step_evidence.py
```

The ordinary native suite includes **34 tests**; fixture bounds include the
four scene selections. Native malformed-input checks reject ten cases before
executing original code. Private `.tmstep`/`.tmstepnative` files and complete
game/OS executable images or code pages are excluded from the evidence bundle.
Selected instruction evidence and decompiler research sources are included.
The audit keeps
complete simulator, complete tire/slip domain, arbitrary native actions and
full headless RL qualification explicitly false.
