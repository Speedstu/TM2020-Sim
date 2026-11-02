# Physics reconstruction 0.10.0

The SDK now includes the original contact-to-constraint arithmetic, prepared
normal/friction sweeps, and position/rotation correction within an explicit
angular/math domain. Sphere/sphere geometry is the first port of an actual
narrow-phase collision handler. These are executable C++ ports, checked against
the pinned game's original instructions, rather than fitted vehicle equations.

This is still **not a complete Trackmania vehicle simulator**. In particular,
remaining shape-pair handlers, Stadium collision assets, tire/slip/material
forces, complete suspension, and contact-interleaved scheduling remain unfinished.
No new real-game training result, stable player root or physics-tick capture is
claimed in this release. The previous live-debugger failure and default-disabled
capture remain documented in `PHYSICS_0_9_0.md`.

## Build and provenance

Original `Trackmania.exe`, build 2026.2.2.1751:

`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`

The executable is unchanged. Pure original routines execute only in owned test
processes; position sweeps and collision-table initialization execute in synthetic
Unicorn memory. No game startup/imports, live attachment, input or game-memory
writes are performed by these qualification tests. No original instructions are
patched or substituted. The distributed runtime contains the C++ ports; it does
not load the original executable or require game assets for these kernels.

Public headers:

- `native/include/tm2020/recovered_jacobian.hpp`
- `native/include/tm2020/recovered_position.hpp`
- `native/include/tm2020/recovered_collision.hpp`

## Prepared velocity constraints and friction

| Original RVA | Operation | Native stride |
| --- | --- | --- |
| `0x85ecd0` | Dynamic Jacobian coefficient preparation | 68-byte subobject |
| `0x85fc50` | Dynamic unilateral Jacobian sweep | 88 bytes |
| `0x85ffd0` | Static unilateral Jacobian sweep | 56 bytes |
| `0x85ff00` / `0x85eab0` | Dynamic friction sweep / bounded impulse helper | 96 bytes |
| `0x8601a0` | Static friction sweep | 64 bytes |

These layouts differ from the 44/40-byte compact normal-velocity constraints
ported in 0.9. They also differ from the separate position-constraint records.
Static assertions preserve sizes and key offsets.

For a dynamic row, stored direction `n`, offsets `rA/rB`, angular coefficients
`IA/IB`, and inverse-mass coefficients `mA/mB`:

```text
angularA = rA cross n
angularB = rB cross n
weightedA = angularA * IA
weightedB = angularB * IB
effective = 1 / ((dot(weightedA,angularA)+mA)
               +(dot(weightedB,angularB)+mB))
speed = dot(vA-vB,n) + dot(angularA,wA) - dot(angularB,wB)
candidate = (speed-target)*effective + oldImpulse
newImpulse = clamp(candidate, lower, upper)
delta = newImpulse-oldImpulse
vA -= n*(delta*mA); wA -= weightedA*delta
vB += n*(delta*mB); wB += weightedB*delta
```

Dot products retain `(Y + X) + Z` evaluation order. Unilateral rows clamp to
`[0, FLT_MAX]`. Friction rows reference a normal row by index and clamp each
tangent independently to `[-mu*normalImpulse, +mu*normalImpulse]`. This is the
observed independent-axis rule, not a substituted circular friction cone.
Return values indicate whether any nonzero delta occurred. Signed-zero behavior,
shared bodies and same-body rows are included in differential cases.

SDK validation and staged commits reject invalid indices, nonfinite/out-of-domain
values or generated overflow without partially updating caller buffers. These
guards are SDK behavior; the game does not provide these C++ exception contracts.

## Contact preparation and restitution

`0x85eea0` prepares a dynamic contact; `0x85f5b0` prepares a static contact.
The 44-byte input contains body IDs, point, normal, signed separation, friction
and restitution. The solver direction is the **negative** input normal.

Position anchors split separation with `+0.5/-0.5`, converting body anchors with
the stored transpose rotation. Velocity Jacobians use offsets from the original
world contact point. When friction is positive, the original chooses a tangent
according to `abs(nX)>abs(nY)`, normalizes the appropriate two-component vector,
then uses `n cross tangent` for the second axis. It creates exactly two friction
rows referencing the newly appended normal row.

The target-velocity branch is reproduced, including restitution suppression:

```text
penetrationVelocity = max(0, -separation/dt)
if restitution>0 and speed < -restitutionSpeedThreshold:
    target = restitution*speed if speed < -penetrationVelocity else 0
else:
    target = penetrationVelocity
```

The oracle executes both original procedures from entry to return with sufficient
native container capacity. All position, normal and tangent record bytes and
append counts match. Native allocation/reallocation is outside qualification;
the C++ API returns caller-owned structures instead. This is contact preparation,
not broad-phase or narrow-phase contact discovery.

## Position constraints and rotation correction

`0x8603b0` and `0x860980` now have working C++ arithmetic ports. Their configuration
argument reads floats at `+0x14/+0x18/+0x1c`; it is **not** a reinterpretation of
the reflected `SolverParameters` layout. Callers supply allowed separation,
maximum correction and factor explicitly. Their effective race values remain
unverified.

The solver transforms stored anchors, clamps the projected separation below by
`-maximumCorrection`, and corrects only negative error. It uses the anchor
midpoint for rotational lever arms and divides by the combined angular and
inverse-mass denominator. Linear position and orientation are corrected while
velocities remain unchanged.

Rotation helpers `0x85e4f0/0x85e7d0` use signed **axis-angle** correction, quaternion
multiplication, conditional normalization and matrix regeneration. This differs
from the normalized quaternion integration used for ordinary pose stepping.
The port retains the original approximately `1e-6` correction cutoff and the
degenerate-quaternion identity fallback.

The public contract restricts each correction-vector norm to **1.57079625 radians**.
Within this bound, half-angle trig needs no argument reduction. The scalar SSE2
sine/cosine polynomials and exact binary64 constants were recovered from
`0x195c010/0x195d240`. No call to the host's `sin/cos` substitutes for that path.
The original math-dispatch flag `0x1f840e4` is zero in qualification. Large-angle
reduction and the alternative AVX math path are **not qualified**, and their
equivalence to current live-game behavior is not assumed. Out-of-domain
corrections reject transactionally.

Both full position sweeps execute under Unicorn with the original profiling
functions and a synthetic null-profiler TLS slot. No profiling or trig call is
skipped. Native original rotation-helper execution provides a second independent
check of both signs, including tiny corrections and degenerate quaternions.

## Collision dispatch and first geometry port

The collision dispatch table at `0x1f9d230` resides in zero-filled runtime data.
Reading the executable's disk data would not recover it. The new extractor runs
the original constructor prefix `0x197d90..0x1985cb` and registration helpers,
stopping before its unrelated tail call to `0x19b250`. Independently rebuilding
the registration assignments exactly matches all 400 executed table entries.

The 20 names come from the original name-pointer table at `0x1e6f0e0`:

| ID | Surface | ID | Surface |
| --- | --- | --- | --- |
| 0 | Sphere | 10 | ConvexPolyhedron |
| 1 | Ellipsoid | 11 | Capsule |
| 2 | Plane | 12 | Circle |
| 3 | QuadHeight | 13 | Compound |
| 4 | TriangleHeight | 14 | SphereLocated |
| 5 | Polygon | 15 | CompoundInstance |
| 6 | Box | 16 | Cylinder |
| 7 | Mesh | 17 | SphericalShell |
| 8 | VCylinder | 18 | Voxel |
| 9 | MultiSphere | 19 | Diggable |

There are 38 pair registrations covering **68 ordered pairs** after swapping.
The other 332 entries retain the default diagnostic handler. Registration alone
does not prove a complete collision implementation; handlers/stubs are retained
by address in `collision-dispatch.json`. The path through candidate traversal,
pair dispatch, GJK and contact postprocessing is recorded for further work.

An earlier tentative label is corrected: `0x4d8c10` grows an **88-byte array**;
it is not the narrow-phase backend. Actual static-collision orchestration leads
through `0x7fab70`, `0x2a2f30`, `0x2a8460` and the pair dispatch at `0x2a55e0`.

The sphere/sphere handler `0x1a17f0` is ported and qualified. Tangency produces no
overlap. For distance above approximately `1e-5`, it computes the negative
center-to-center normal, penetration vector and A's surface point. For nearly
coincident centers, the original uses fixed normal `(0,-1,0)`, **B's radius alone**
for penetration and A's center as its point. That unusual fallback is preserved.
Surface-ID words and flag behavior are retained. It does not recover chassis
shape data or material response coefficients.

## Verification and remaining work

Twenty public arithmetic operations, including the earlier eight, have 20,000
differential cases each. Classification matters: thirteen complete arithmetic
procedures include an internal shared helper; two builders replace container
ownership; four position/rotation procedures have the bounded scalar-math
contract; the prior selector and suspension qualifications remain bounded
operations. This does not mean twenty complete engine stages were recovered.

The new owned regression composes contact preparation, restitution, friction and
position correction, checks penetration convergence, sphere edge cases and
transactional rejection after a late row failure. The installed external CMake consumer calls
the new APIs. All **14 CTest cases** pass, including PPO/checkpoint, DLL ABI and
owned-process checks. Rust formatting, clippy and Rust-to-native inference pass.
The installed SDK consumer also passes against version 0.10.0. The unchanged
legacy .NET framework groups were not rerun in this release's `-SkipLegacy` run;
their prior evidence is retained.

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
./scripts/run-physics-research-checks.ps1
```

New evidence: `constraint-evidence.json`, `collision-dispatch.json`,
`recovered-jacobian-oracle.json`, `recovered-contact-build-oracle.json`,
`recovered-rotation-oracle.json`, `recovered-sphere-oracle.json`, and the position
oracle's binary fixtures/report under `local/recon/position-oracle/`.

The remaining work is substantive: mesh/convex/other collision handlers and
assets, physical tire forces and surface behavior, the full suspension path,
runtime solver/substep configuration, complete scheduler and authoritative
tick-aligned vehicle validation. The SDK's `full_trackmania_physics` flag remains
false. Earlier gold-medal and 602-transition PPO evidence is preserved without
claiming this release improves the bot.
