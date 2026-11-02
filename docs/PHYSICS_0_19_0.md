# Physics reconstruction 0.19.0

**64 public arithmetic operations remain qualified with 20,000 original-code
cases each.** This release expands their domains: it adds the active game's
bounded AVX/FMA position path and tests material response using records captured
from the running Solo session. The public operation count does not increase
for these additional math-path tests.

## Effective parameters captured from Solo

Trackmania was launched normally, then Automne 2026 - 01 was opened in Solo
without opponents. A read-only native bootstrap recovered seven agreeing
position copies. A wider typed search found four coherent 88-byte rigid states;
the manager candidate at index zero links model, ID map, user data and a vehicle
whose ID round-trips back to that state. The process, creation time and exact
executable SHA are checked before observation. The original game is unchanged.

The new native `tm2020_vehicle_parameter_probe` copies selected numeric fields,
80 material records and **411 curves**: 11 configuration curves and five curves
per material. It bounds curve counts, verifies finite and strictly increasing
points, rechecks headers and bindings, then writes the completed JSON. Reading
or validation failures leave an existing output file intact. Runtime needs no
Python. The retained capture can be audited without reopening the game.

Observed values include:

| Parameter | Captured value |
|---|---:|
| Math dispatch flag `0x1f840e4` | 1 |
| Solver static/dynamic friction, velocity, position iterations | 4 / 1 / 4 / 4 |
| Model center | (0, 0.4384999871, 0.2882934809) |
| Suspension mode | 2 |
| Spring stiffness, damping, rest length | 40 / 1 / 0.200000003 |
| Separate position allowed separation, maximum correction, factor | 0.02 / 0.2 / 0.2 |
| Material integer `+0x40` range | 0 to 20,000 |

The manager/header backlink is not established. The capture preserves
`authoritativeOwnerVerified=false` and `internalTickVerified=false`; it does
not claim an atomic physics-tick snapshot or a validated player owner. Raw
manager `+0x80` words retain an auxiliary label rather than being treated as
verified contact coefficients. A curve's trailing word at `+0x14` is opaque:
live curves can contain five points while this word is zero, so it must not
be used as a capacity bound.

## Material response with actual captured records

The material integer bound is expanded to 1,000,000. Its averaging conversion
and rounding are checked against the original helper across 20,000 cases.
**10,000** aggregator cases use the captured material records and their actual
four response curves in synthetic wheel/state contexts; the other cases vary
coefficients and curves independently. All defined outputs match bit for bit.
The captured material curves contain up to seven points, so fixtures own
variable-length point arrays. These tests execute complete original `0x845b60`
and its curve/material callees; they do not validate a whole live trajectory.

## Bounded AVX/FMA position corrections

The observed game math flag is 1, while previous position tests selected 0.
The new path ports the exact double-precision fused multiply-add polynomials
in original sine/cosine helpers `0x195c010` and `0x195d240`. Explicit
`std::fma` preserves fused rounding independently of compiler contraction or
the target machine's AVX code generation. The existing scalar path remains
available. Correction norm is still limited to `1.57079625`; larger-angle
argument reduction remains unported.

The native oracle executes both complete original rotation procedures and both
complete position sweeps, **20,000 cases per sign and per sweep**, with dispatch
flag 1. Cases include small-polynomial thresholds, signed zero, maximum allowed
correction and quaternion normalization fallbacks. Its test executable contains
a loader-managed zeroed TLS template. The original profiler's ordinary null
branch runs normally; no TEB, GS base, original instructions or callees are
patched or skipped. Only private copied configuration data sets the math flag.

Callers choose `PositionMathPath::scalar_sse2` or `fused_avx_fma` explicitly.
Position-island composition and `RigidMeshWorld` propagate this choice. Native
semantic tests resolve rotating contacts with FMA, and both standalone scene
modes verify bit-identical snapshot replay. The original entire eight-pass
island loop has direct instruction-oracle coverage for scalar dispatch; the
new FMA evidence covers its complete primitive sweeps, not the entire enclosing
loop or complete game step.

## Reproduce

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
./dist/sdk-windows-x64/bin/tm2020_rigid_mesh_demo.exe 10000 trace.csv report.json fma
```

The release workflow reaudits retained parameters, regenerates numeric fixture
inputs, runs both math domains and checks the independently installed C++
consumer, Rust bindings, native PPO/BC and prior reverse evidence. Live recapture
requires a fresh process-bound manifest and independently checked manager
candidate; old addresses must not be reused after restarting the game.

Complete tire/drive forces, wheel collision queries, Stadium geometry, joint
construction, sleeping, adaptive contact reevaluation and full held-out
trajectory agreement remain unfinished. The faithful autonomous Trackmania
vehicle simulator is not ready. No new race time or learned-policy improvement
is claimed. Earlier resistance evidence is retained in
[0.18.0](PHYSICS_0_18_0.md).
