# Physics reverse engineering — SDK 0.8.0

21 October 2026. Four arithmetic kernels are now ported from the installed
game and independently compared with its original instructions. A native,
autonomous runner executes these kernels, including explicit force-to-pose
composition and snapshot/restore. Complete Trackmania vehicle simulation is
unfinished: tire forces, suspension, contacts, constraint solving, collision
geometry, sleeping decisions and adaptive scheduling still have to be recovered
and validated together. The existing experimental flat-plane model remains a
separate, failed-fidelity experiment.

## Pinned executable and tools

`D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe`, build
2026.2.2.1751, SHA-256:

```
3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda
```

The installed executable was not changed. Development tools are portable
radare2 6.2.4, pefile, Capstone, MinGW C++20, and Unicorn 2.1.4 installed under
`tools/physics-python` on H:. Python, Unicorn and original game instructions are
**development oracle dependencies only**. The installed kernel runner uses
our compiled C++, with no game process, assets, original code, or Python.

## Corrected procedure boundaries and reflection

The old analysis mistook chained `.pdata` entries for complete procedures.
`scripts/pe_unwind.py` follows validated `UNW_FLAG_CHAININFO` parents, including
odd unwind-slot padding, exact parent-entry matching, cycle rejection and
overlap rejection. This follows
[Microsoft's x64 unwind specification](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170).

The ordinary `.text` scope contains 113,623 runtime ranges grouped into
69,653 roots. Another 935 entries outside `.text` are excluded; their
overlapping ranges are not assigned guessed precedence. Leaf procedures need
explicit, individually checked bounds. Unwind extents can contain jump-table
data, so a successful linear decode is not a complete control-flow proof.

`InternalPhysicsStep` is root `0x8025a0`, with seven ranges, rather than a
series of unrelated short functions. `MgrDyna_Integrate` is an internal profiler
label in that procedure. The current bounded graph records 384 procedures,
50 named string references, unresolved indirect calls, and incomplete-decode
rejections. `graphTruncated=true` is intentional and remains in the evidence.

Reflection now accepts namespace struct names beginning with `N` and tracks
constant aliases in nonvolatile 32/64-bit registers. This produces 819 class
registrations, 3,080 properties and 2,532 member type edges. The former README
counts were incomplete. Registration/type evidence alone does not establish
pointer storage or a live player object.

## Recovered rigid-body representation

`NSceneDyna::SItemState` has registered size `0x58`; its registered `Vel` and
`AngularVel` fields independently confirm offsets `0x40` and `0x4c`.

| Offset | Representation |
|---|---|
| `0x00` | Nine binary32 rotation-matrix values |
| `0x24` | Position, three binary32 values |
| `0x30` | Quaternion, scalar-first **w,x,y,z** |
| `0x40` | Linear velocity |
| `0x4c` | Angular velocity |

This differs from the 0x360-byte **visual** state used by the earlier bot.

## Four arithmetic ports and their qualification

Public API: `native/include/tm2020/recovered_rigid.hpp`.
Implementation: `native/src/recovered_rigid.cpp`.

| Original RVA | Recovered operation | Independent comparison |
|---|---|---|
| `0x194de0` | Quaternion integration and normalization/fallback | 20,000 native cases |
| `0x1886d0` | Scalar-first quaternion to matrix | 20,000 native cases |
| `0x7f4d40` | Pose integration, auxiliary copy, velocity caps | 20,000 native cases |
| `0x7f89d0` | Gravity, force/torque to new velocities, supplied sleep state, attenuation and accumulator clearing | 20,000 emulated cases |

The first three routines run from a private copy of the pinned PE sections
inside the **owned test process**, with only reviewed arithmetic-code pages
executable. No entrypoint, imports, startup or game process is invoked.
The test includes zero quaternions, zero angular velocity, the angular
threshold, velocity caps, nonzero array indexes, untouched neighboring states
and auxiliary padding. Every one of 1,000 composed post-force rollout states
also matches the native original. Snapshot/restore reproduces the future.

The fourth routine has profiler/TLS dependencies. Its entire unmodified x64
procedure, helper `0x7f5130` and original profiler functions are run under
[Unicorn's CPU emulator](https://www.unicorn-engine.org/docs/tutorial.html).
A synthetic TEB/TLS block supplies a null profiler, following the original
disabled-profiler branch. **No function is patched or skipped.** Cases run in
batches of four and cover active, skip-flag, sleep-sentinel, attenuation enabled
and disabled, zero, threshold-equality and signed-zero inputs. Entry/branch
coverage assertions verify that the helper and original profiler paths ran.
The native C++ fixture output is compared byte for byte with emulator output.

These are exact comparisons over the tested synthetic domains, under the
current compiler and round-to-nearest binary32 arithmetic, without FMA,
FTZ or DAZ. They are not an exhaustive proof over all float patterns or over a
complete race. The caller owns its floating-point environment. NaN/infinite,
oversized and invalid interval inputs are rejected by the public API.

### Pose order matters

Position is updated **before** clamping linear velocity to ±10,000. Rotation
is integrated before limiting angular velocity to the supplied model's `+0x4c`
value. Angular quaternion integration is conditional on squared angular norm
exceeding binary32 bits `0x2edbe6ff`. The matrix is regenerated unconditionally.
Three model fields at `+0x1c,+0x2c,+0x3c` are copied to a separate 16-byte
output; its fourth lane stays untouched. Their higher-level meaning is not
asserted by the API.

### Velocity update

The recovered routine accepts explicit coefficients and environment inputs.
For an active, non-sleeping item it performs, in binary32 instruction order:

```
gravity_scale = (model[0x18] + item[0x08]) * item[0x0c]
force[k] = gravity_scale * world_gravity[k] + force[k]
v[k] = force[k] * (dt * coefficients[3]) + v[k]
w[k] = (torque[k] * coefficients[k]) * dt + w[k]
```

The two velocity norms sum Y² before X², then Z². Enabled small-velocity
attenuation precedes the update. Pinned data-image defaults are threshold .01,
multiplier .9 and enabled=true; these are not automatically treated as effective
race settings. Item flag bit 1 skips the item and preserves accumulators.
Supplied sleep index `0xffff` zeros both velocities. Consumed force/torque
accumulators are cleared. The actual decisions assigning sleep state and
producing tire/suspension forces remain outside this port.

`SolverParameters` also reproduces all 44 bytes of original constructor
`0x805890`, independently checked against original instructions. These are
constructor defaults, not verified effective Stadium solver settings.

## Autonomous runner

`RigidWorld` provides reset, batched pose stepping, explicit
`step_force_then_pose`, snapshot and restore. Force inputs, velocity
coefficients and environment remain caller-owned; preserve them too when
reproducing a future. Invalid reset/restore/force input is checked before
mutating the world, including a force result outside the bounded finite domain.
The force-to-pose composition has a 1,000-step deterministic
restore test. It does not implement the contact solve between these stages or
the game's adaptive subdivisions.

The reproducible benchmark runs 65,536 bodies for 100 pose steps and verifies a
restored rerun. The initial measurement was about **50 million post-force body
steps/s**; the full release run measured **45.15 million**, and the JSON retains
the latest measurement on this machine.
This measures only the recovered pose kernel, not Trackmania vehicle or RL
environment throughput. `full_trackmania_physics=false` is explicit in the API
and all qualification outputs.

## Live vehicle relationship and actual force variant

In one real local Solo session, Fall/Automne 2026 - 01, PID 7620:

1. A bounded read-only layout scan found five start-position candidates.
2. Three ordinary one-second throttle trials each recorded 300 samples.
   One address, `0x2db730ca240`, retained all 300 coherent samples in every
   trial, moved 25.54–25.97 m and reached 15.64–15.80 m/s.
3. Matrix and scalar-first quaternion agree throughout those observations.
   Other initial numeric matches mostly fail once the car moves; they are not
   promoted to physics states.
4. Manager candidate `0x2db672a9bb0` has state array `+0x70`, model array
   `+0x10`, ID-index map `+0xb0` and user-data array `+0x40`, matching separately
   bounded native accessors `0x7be670`, `0x7be690`, `0x7bea40`.
5. User-data entry `+8` leads to a vehicle whose item ID at `+0x10` maps back to
   state index zero. Vehicle `+0x88` leads to configuration selector `+0x1790=5`.
6. `ComputeForces` root `0x8427d0` uses the recovered 17-entry jump table at
   `0x842e84`. Selector 5 goes to `0x851f00`: nine unwind ranges, 1,824 decoded
   instructions. This is the concrete force variant to reverse next for the
   observed car. Calling it the universal Stadium variant would require more
   maps, vehicle types and sessions.

A fourth, passive 300-sample pass rechecks the relationship after restart.
The vehicle data address changes between the third and fourth passes while
the rigid-state array and configuration address remain the same. Resolve the
user-data relationship anew; the vehicle data pointer is not a persistent root.
An additional hypothesis that the first user-data word points directly to a
vehicle manager with a `+0x110` backlink **fails** and is retained as false.

Observed model values include `+0x18=1500`, `+0x1c=+0x2c≈0.0016`,
`+0x3c≈0.004` and angular cap `+0x4c=100`. Raw bits and pointer relationships
are retained; `1500` is not labelled mass solely from its numeric plausibility.

All process handles request read/query access only; the probe does not write
game memory or install hooks. The normal local input backend returns to neutral
and requests an ordinary restart after each trial. The game remains at the
start. Addresses are disposable, bound to PID/creation-time/executable SHA.
There is still no respawn/relaunch-stable player root or verified internal tick.
Wall-time velocity/position comparisons have about 5 cm median discrepancy
between reads, consistent with asynchronous sampling; this is not tick-exact
state-transition evidence.

The earlier numeric V3 bootstrap on this PID **failed** its quaternion-copy
consensus threshold (20/30 valid). That failure is retained. The new typed probe
uses its manifest only to verify process identity, then checks the recovered
88-byte layout independently; the failed numeric consensus is not relabelled a
successful physics bootstrap.

## Reproduction and local evidence

Full release regression and installation:

```powershell
./scripts/run-release-checks.ps1
```

Focused build and physics qualification:

```powershell
./scripts/run-physics-research-checks.ps1
```

The focused command installs Unicorn 2.1.4 under project-local `tools/` if
needed. Existing Python/pefile/Capstone, MinGW and the exact installed game build
are required for development oracles. A different executable hash fails closed.
Neither command starts a new live input experiment.

The public probe accepts a valid current Solo manifest, reference replay,
output prefix, scan limit and `observe` or `keyboard`. An optional manager
address rechecks accessor relationships without a fresh broad scan. Use a new
identity manifest for a new game process; never reuse the documented addresses.

Evidence under `local/` is kept out of Git/source archives:

- `recon/physics/physics-procedure-graph.json` and annotated procedure listings.
- `recon/reflection-current-build.json`, `recon/reflected-member-types.json`.
- `recon/recovered-kernel-oracle.json`.
- `recon/force-oracle/recovered-force-oracle.json` and synthetic fixture files.
- `recon/recovered-kernel-benchmark.json`.
- `recon/rigid-7620-v{1,2,3,4}.*`, including rejected numeric and backlink hypotheses.
- `recon/physics-live-qualification.json`, `recon/physics-solo-after-probes.jpg`.
- `physics-research-0.8.0.json`, `release-0.8.0.json`, full regression log.

Source snapshot: `backups/trackmania2020-re-source-0.8.0.zip` plus `.sha256`.
No installed game executable or game assets are included in the source archive.
The separate `backups/trackmania2020-re-physics-evidence-0.8.0.zip` stores explicit
proof artifacts and a per-file SHA-256 manifest. It excludes the installed game,
game assets and full process dumps.

The full 16-group framework regression, nine CTest cases, five unwind tests,
reflection selftest, four 20,000-case differential comparisons, Rust format/lint
and inference checks pass. The installed SDK is also consumed by a separate
C++ project that calls the new force-to-pose API, and the installed autonomous
benchmark runs successfully. The later force-overflow guard is covered by a
transactional rejection test and a rerun of the affected physics qualification.

## Remaining work for exact vehicle simulation

Recover the observed force variant and its helpers, per-wheel state, tuning
semantics, contact materials and geometry; qualify their state transitions with
independent original-code oracles and synchronized live traces. Port contact
generation and constraints, reproduce sleep decisions and adaptive scheduler
branches, then validate multi-second held-out trajectories and complete races
before using the environment as faithful PPO training physics. No readiness
flag bypasses these missing components.
