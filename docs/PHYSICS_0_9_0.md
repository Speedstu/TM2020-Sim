# Physics research 0.9.0 — contacts, suspension, subdivision and code atlas

21 October 2026. The SDK now ports six complete arithmetic procedures and two
bounded selection/suspension operations. Each operation passes 20,000 cases
against original instructions. The full Trackmania vehicle simulator is still
unfinished. This report supplements [0.8.0](PHYSICS_0_8_0.md); the executable SHA
remains `3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.

## Whole ordinary-code atlas

`scripts/reverse_atlas.py` indexes every chained-unwind procedure root in the
ordinary `.text` section into a local SQLite database. It streams Capstone
objects rather than retaining millions of them in memory. The current result:

| Evidence | Count |
|---|---:|
| Procedure roots | 69,653 |
| Runtime ranges | 113,623 |
| Linearly decoded instructions | 5,494,381 |
| Direct/indirect call/jump records | 547,952 |
| ASCII strings | 51,124 |
| String references | 46,849 |
| Rejected incomplete procedures | 1,105 |
| Excluded non-`.text` runtime ranges | 935 |

The database is about 37 MB. Full generation took about 83 seconds on this
machine. `check_reverse_atlas.py` checks its SHA-256, generator-source hash,
SQLite integrity and table counts; it rebuilds when the generator changes.
The database supports caller and string-reference queries across the ordinary
game code, removing the earlier 384-procedure traversal bottleneck.

This is an inventory, not a full decompilation or complete control-flow graph.
Unwind extents can contain jump-table data. Linear edges are not assertions of
execution. Indirect edges, leaf routines without verified bounds, rejected
decodes and excluded code sections are not silently resolved or bypassed.

## Prepared normal-contact impulse solvers

New API: `native/include/tm2020/recovered_contacts.hpp`.
Implementation: `native/src/recovered_contacts.cpp`.

`solve_dynamic_normals` ports complete original procedure `0x7f5860`.
`solve_static_normals` ports complete original procedure `0x7f5cb0`.
They execute one sequential solver sweep over **prepared** constraints,
updating linear/angular velocities and the accumulated normal impulse.

For each constraint, the native projection is:

```
point_velocity = linear_velocity + angular_velocity cross point_offset
normal_speed = (relative_y * normal_y + relative_x * normal_x)
               + relative_z * normal_z
new_impulse = max(0, -(normal_speed + bias) * effective_coefficient
                     + old_impulse)
delta = new_impulse - old_impulse
```

Impulse updates apply to both bodies with opposite signs for a dynamic contact,
or to one body for a static contact. Angular response uses the supplied native
coefficients. Binary32 operation order, signed zero at `MAXSS`, accumulated
impulses, Gauss-Seidel ordering, aliasing body indexes and the returned maximum
absolute impulse change are preserved.

Dynamic records are 44 bytes: body indexes `+0,+4`, world point `+8`, normal
`+0x14`, bias `+0x20`, effective coefficient `+0x24`, accumulated impulse `+0x28`.
Static records are 40 bytes: body index `+0`, point `+4`, normal `+0x10`, bias
`+0x1c`, coefficient `+0x20`, accumulated impulse `+0x24`.

The independent oracle executes the original unmodified procedures in the
owned test process, not in the game. Each solver passes 20,000 batches of up
to four constraints, with shared bodies, same-body indexes, zero normals,
signed zeros, positive accumulated impulses and zero-count batches. All state
bytes, constraint bytes and the return value match. Additional unit tests check
equal-mass impact conservation, convergence, static impact and transactional
rejection. Bounds and output validation occur before committing a batch.

This does **not** port geometry-to-contact generation, bias/effective-coefficient
construction, friction constraints, position constraints or the outer solver
iteration scheduler. The caller must supply their actual prepared data.

## Actual pose-subdivision selection

Two original instruction slices in `InternalPhysicsStep` were reconstructed:
`0x803114..0x8031ac` and `0x803274..0x803309`. Both compute the same selection:

```
displacement_squared = dot(dt * velocity, dt * velocity)
if displacement_squared <= limit * limit:
    selected_interval = dt
else:
    selected_interval = dt * clamp(sqrt(limit*limit / displacement_squared),
                                   0.1, 1.0)
```

`select_pose_fraction` preserves the binary32 ordering. The emulator executes
both original slices without patching them. All 20,000 cases match each other
and the C++ output bit for bit: 6,685 full intervals, 11,388 minimum fractions
and 1,927 interior fractions. Rest, zero interval and zero limit are included.

The enclosing game procedure skips items with flag `0x10`; subdivision also
depends on a model flag at `+0x5c` and a geometry pointer. It calls `0x800750`
between fractions to reevaluate contacts. A remaining interval at or below
binary32 `9.999999747378752e-6` is not processed by that loop. Only the selector
is ported here: repeatedly integrating at fixed velocity would omit the contact
reevaluation and would not reproduce the original scheduler.

## Conditional spring/damper branch and wheel observations

Original function `0x844090` contains a mode-2 spring/damper branch:

```
force_local_y = (rest_length - wheel_length) * stiffness
                - wheel_speed * damping
```

Its native gates require configuration mode 2 and contact for the selected
wheel. If vehicle word `+0x171c` is nonzero, all four wheels must have contact.
The function then passes `(0, force_local_y, 0)` to force application `0x845100`.

`suspension_mode2` reproduces these gates and arithmetic. Its oracle executes
the original function from entry, stopping immediately before the force call
at `0x844121`. Across 20,000 cases, 4,004 active force computations and all
inactive gate cases match. The original force application call is **not**
included in this qualification; neither are other suspension modes or the
additional call-site vehicle-status gate. This is not the entire suspension.

The read-only probe now resolves the vehicle data on every sample, then reads
four wheel records at vehicle `+0x1780`, stride `0xb8`. The relevant fields are
length `+0`, speed `+4`, contact word `+0x34`, material byte `+0x40`.
Two passive trials on PID 7620 each retain 300 valid observations per wheel.
The stored branch parameters were mode 2, all-contact gate 0, coefficients
40 and 1, rest length approximately .2. All four contact words were 1 and all
material bytes were 16. SI units, wheel naming/order and actual execution of
the conditional force branch are not inferred from those values.

The attempted throttle/wheel trial `rigid-7620-v6` was rejected by the
foreground-input guard before any input or trace sampling. The failure is
retained. Previously observed whole-body throttle response remains separate.
Both attempted manager backlinks remain false; no stable player root is claimed.

## Focused pipeline and remaining stages

`reverse_wheel_pipeline.py` retains ranges, calls and supporting instructions
for 18 relevant procedures, plus 12 references in the per-wheel force loop.
It ties the observed variant `0x851f00` to its helpers; contact processing
`0x7d2b90/0x840890`; static collision dispatch `0x7fc730/0x7fc210/0x4d8c10`;
constraint construction `0x800060/0x8003f0`; solver `0x7f6ec0`; and adaptive
contact reevaluation `0x800750`.

Position constraints `0x8603b0` and `0x860980` have separate prepared layouts.
Their 44/40-byte strides happen to match the velocity constraints, but their
fields differ: local points/target points replace velocity bias and impulse
fields. They are **not interchangeable buffers**. These procedures and their
quaternion-correction helpers remain unported. Full tire/slip/material forces,
narrow-phase contact generation, friction, geometry assets and the scheduler
remain work items. No missing stage is replaced with a fitted force model.

## Experimental synchronized capture: retained failure

A development debugger probe was added to capture force entry/return phases
using hardware execution breakpoints. It changes thread debug registers;
it does not patch executable bytes or request privilege elevation. Its owned
process fixtures now verify 20 entry/return pairs, correct pre/post values,
restoration/detachment, normal child exit, and deliberate error-path cleanup.
It follows the normal
[Windows debugging API](https://learn.microsoft.com/en-us/windows/win32/debug/debugging-functions).

The real-game attempt on PID 7620 failed while reading synchronized inputs.
The game was subsequently observed to have exited; the exact cause is not
established. The first callback argument had incorrectly been treated as the
force array. Static accessor analysis instead locates the accumulator array at
dyna-manager `+0xa0`, with 24-byte entries. That correction has only been tested
in the owned fixture. Cleanup now restores debug registers while the debug
event still stops the target, before continuing it; the prior error path had
a race. No successful game phase capture or authoritative internal tick is
claimed. The game was relaunched normally afterward.

**Live debugger capture is disabled in the default build and is not installed
into the SDK package.** The source remains experimental. The owned-process tests
are always available. It must not be substituted for a qualified live physics
capture merely because its fixture passes. No debugger concealment, protection
bypass or elevated retry was attempted.

## Verification and artifacts

The full 16-group framework regression passes. Twelve CTest cases pass,
including the two owned-debugger cases added after the full release run.
Original-code differential tests cover eight operations, 20,000 cases each;
six are complete arithmetic procedures and two are bounded operations/slices.
Existing C/Rust ABI, PPO/checkpoint, installed CMake consumer and autonomous
pose-runner checks pass. These do not establish a complete vehicle simulator.

```powershell
./scripts/run-release-checks.ps1
./scripts/run-physics-research-checks.ps1
```

The commands rebuild/validate the atlas and mathematical oracles. They run
owned debugger fixtures only; they do not attach to a game or send new inputs.

Additional local evidence:

- `local/recon/game-atlas.sqlite` and `.json`.
- `local/recon/recovered-contact-oracle.json`.
- `local/recon/selection-oracle/selection-suspension-oracle.json` and fixtures.
- `local/recon/wheel-contact-pipeline.json`, `wheel-qualification.json`.
- `local/recon/rigid-7620-v5.*`, `-v6.*`, `-v7.*`.
- `local/recon/force-phase-7620-v*.log` and owned-debugger fixture traces.
- `local/physics-research-0.9.0.json`, release log and final CTest log.

Versioned source/evidence archives under `backups/` include SHA-256 manifests.
The source archive excludes the original executable, game assets and local
reverse-engineering dumps. SDK installation remains `dist/sdk-windows-x64`.
