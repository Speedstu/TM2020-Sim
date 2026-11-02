# Physics reconstruction 0.13.0

**47 public arithmetic operations now pass 20,000 original-instruction cases
each within documented domains.** Four operations extend
[0.12.0](PHYSICS_0_12_0.md): general point constraints, angular constraints,
angular rate coupling and the velocity island scheduler with every island
velocity span populated. The separate external callback list is empty in the
scheduler oracle.

The complete faithful vehicle simulator remains unfinished. These prepared
constraint solvers do not recover joint construction, general joint position
passes, tire/slip force generation, effective race tuning or Stadium assets.
The adaptive pose loop's contact reevaluation is also still required. No new
in-game driving or learning result is claimed.

## Complete original sweeps

The source executable remains unchanged and is pinned to SHA-256
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.
Native owned-process oracles execute the full selected routines with synthetic
inputs; scheduler oracles use Unicorn 2.1.4, including all original helper calls.
No game process, substituted original instructions or skipped calls are used.
Runtime SDK code uses C++ ports without the original executable.

| New public operation | Original RVA | Defined behavior |
| --- | --- | --- |
| `solve_point_constraints` | `0x7f56d0` | Full point constraint sweep, signed/unilateral modes |
| `solve_angular_constraints` | `0x7f5f40` | Full angular constraint sweep, either body fixed |
| `solve_angular_couplings` | `0x7f67a0` | Scaled-threshold angular rate coupling |
| `solve_constraint_islands` | `0x7f6ec0` | All native island velocity passes, external callbacks empty |

Point records are 60 bytes: two body IDs, two world anchors, direction, bias,
softness, effective coefficient and accumulated impulse. Body B can be
`0xffffffff`; body A must exist because native application does not guard it.
The updated impulse is clamped nonnegative **only when softness is zero**.
Nonzero softness allows signed accumulated impulses. The oracle covers 26,668
zero-softness and 53,332 nonzero-softness record injections, fixed and aliased
bodies, and both signs of accumulated impulse.

Angular records are 36 bytes. Both body IDs can be fixed. The original uses
**coefficient lane 3 for all angular components** in this particular helper;
the SDK preserves that arithmetic instead of substituting an inertia model.

Coupling records are 60 bytes, containing two body IDs, axes, coefficient
weights and a ratio. The original compares scalar rate error against
`max(1, abs(projectedA), abs(projectedB)) * 0.001`. Below this threshold it does
nothing, including avoiding denominator evaluation. Otherwise it computes
weighted reciprocal coefficients, couples the scalar rates and **overwrites
both full angular vectors with axis projections**. This is the recovered
operation, not a generic conservation-law approximation. Zero/singular active
denominators are rejected transactionally. The oracle retains 17,391 updating
cases and 2,609 unchanged cases.

## Complete island velocity order

The previous contact-only API remains available. `ConstraintIsland` adds the
four general spans: early point constraints at native `+0xc0`, late point
constraints at `+0x30`, angular couplings at `+0x120` and angular constraints at
`+0x130`. All are owned vectors; native allocator/container behavior is not
exposed as an SDK ABI.

After the conditional dynamic/static friction passes, each iteration visits
all islands for angular coupling, then all for angular constraints, then all
for early points. It next visits each island for late points followed by
static Jacobian normals, then each for dynamic compact and Jacobian normals,
then each for static compact final normals. The external callback list between
the last two groups is empty in qualification. The ordering matters when
islands share bodies or constraints reuse previous accumulated impulses.

Every differential case verifies the original call trace as well as all state
and prepared-record bytes. Cases include zero through three islands, empty or
populated spans, zero through seven iterations, independent friction thresholds
and mixed general/contact constraints. SDK limits permit up to 128 iterations;
this is a runtime bound rather than a claim that every count was exhaustively
enumerated. Errors in late passes leave the entire original state and island
impulses unchanged.

## Validation and installation

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

Native regression includes explicit signed/unilateral behavior, fixed-body
application, lane-3 angular scaling, coupling threshold/projection, scheduler
integration and late transactional rejection. The independent installed C++
consumer calls both general and contact-only schedulers. Prior geometry,
material, force/pose, PPO, C/Rust ABI and reflection checks are retained.
`recovered_joints.hpp` is installed with the CMake package. The unchanged legacy
.NET suite is included when `-SkipLegacy` is omitted.
