# Physics reconstruction 0.11.0

The SDK adds executable C++ ports for mesh cooking, native AABB construction and
traversal, sphere/mesh contact generation, convex SAT, polygon/face clipping,
engine curve interpolation, mode-2 suspension force/torque application, and
surface response. Together with the previous release, **35 public operations
have 20,000 original-instruction differential cases each**, within the domains
below. This count describes public operations, not 35 complete engine stages.

**The complete faithful Trackmania vehicle simulator remains unfinished.** Full
convex manifolds, physical tire/slip forces, race tuning and collision assets,
and contact-interleaved scheduling remain necessary. No additional in-game
learning or driving result is claimed. Earlier gold-medal and 602-transition PPO
evidence remains in [0.7.0](NATIVE_0_7_0.md). The prior failed phase capture and
default-disabled experimental debugger remain documented in
[0.9.0](PHYSICS_0_9_0.md).

## Provenance and execution

Original build 2026.2.2.1751 SHA-256:

`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`

The original executable is unchanged. Owned test processes map only selected
original arithmetic routines; Unicorn executes other routines in synthetic
memory. No imports, game startup, game process access or substituted original
instructions are used by these oracles. SDK runtime code uses the C++ ports and
does not require the original executable. Test fixtures use sufficient native
capacity or precommitted scratch arenas; native allocation is not an SDK port.

New public headers are `recovered_mesh.hpp`, `recovered_convex.hpp`,
`recovered_polygon.hpp`, `recovered_vehicle.hpp`, and `recovered_material.hpp` in
`native/include/tm2020/`. They are installed with the CMake package.

## Geometry

| Public operation | Original RVA | Qualification |
| --- | --- | --- |
| `cook_triangles` | `0x1adb10` | Full arithmetic; preallocated original output |
| `triangle_aabbs` | `0x1ae3ba..0x1ae55a` | Bounded loop before tree allocation |
| `build_aabb_tree` | `0x19fad0`, helpers `0x19ee90`, `0x19f2e0`, `0x19f580` | Recursive algorithm; owned buffers |
| `query_aabb_tree` | `0x1a01b0` | Full traversal, closed overlap |
| `collide_sphere_mesh` | `0x1af710` | Full face/edge/vertex arithmetic |
| `project_vertices` | `0x1cab20` | Full projection interval |
| `separating_axes` | `0x1cae40`, `0x1cad10` | Full SAT arithmetic, defined witness bytes |
| `classify_point` | `0x1cc390` | Reviewed leaf, inclusive tolerance band |
| `split_polygon` | `0x1cc3e0` | Deterministic intersection domain |
| `face_contacts` | `0x1cca10` | Full clipping/filter arithmetic within that domain |

The cooker emits 32-byte triangles: normal at 0, plane constant at 12, three
indices at 16, and 16-bit surface ID at 28. It normalizes when squared cross
length exceeds bits `0x1e3ce509` (approximately `1e-20`). Plane evaluation order
is `((-nx)*vx-ny*vy)-nz*vz`. The unused last word is initialized to zero by the
SDK; the native oracle's corresponding unused storage is preinitialized.

AABB nodes are 28 bytes. The low tag bit identifies a leaf; the remaining bits
hold either its triangle index or a preorder subtree skip count. Tree building
selects maximum center variance, partitions centers strictly greater than the
mean to the front, and retains the original swap order. The midpoint fallback
uses the partitioned array. Mesh construction supplies leaf width 2; smaller
groups may be a flat leaf forest. **990,915 nodes** match bit for bit across
20,000 construction cases, including equal centers and leaf widths 1 through 4.

Sphere/mesh collision is one-sided and accepts mesh tangency. This differs from
the strict overlap in the previously ported sphere/sphere handler. Edge and
vertex contact normals are radial, but penetration vectors still follow the
triangle normal. Vertex squared cutoff is approximately `1e-10`; edge-interior
squared cutoff is approximately `1e-5`. Shared-edge duplicates and native
emission order are preserved. The oracle includes arbitrary 3D rigid rotations,
back faces, tangency, degeneracy, empty trees, and native boolean/emission gates.

SAT expands A's interval by the supplied margin. It tests both face-axis sets
and normalized cross-edge axes. Cross-edge witness replacement has an
approximately `1e-4` bias. Unused native feature bytes contain stack data and
are **not compared**; all defined outputs match. An empty axis set returns the
native no-witness result and is not a proof that arbitrary volumes overlap.
The complete convex/convex and convex/mesh handlers remain unported.

Polygon classification returns positive above `+1e-4`, negative below `-1e-4`,
and on-plane inclusively between them. Face clipping retains positive edge-plane
sides, then filters against its face plane with exact `distance <= 0`.
**Empty intermediate input does not clear the original split output.** Because
face clipping swaps two reused buffers, old polygon contents can reappear.
This behavior is preserved and verified against the original function.

The original near-parallel intersection branch, absolute denominator at most
`1e-5`, can append uninitialized stack contents. The SDK rejects that branch;
it does not invent a deterministic replacement or claim qualification there.
Face loops must be ordered convex polygons. The oracle compares **70,791 face
contact vertices** over 20,000 cases.

## Curves, suspension and force application

`evaluate_curve` ports complete `0x42bcb0` and Hermite helper `0x42bba0`:
endpoint clamping, empty/single-point curves, step flag 1, smoothstep flag 2,
Hermite flag `0x10`, and zero final Hermite tangent flag `0x20`. Precedence and
the `1e-5` boundary tolerance follow the original. SDK abscissae must strictly
increase. These curves are reused by vehicle force helpers; recovering their
evaluator does not supply the actual race curve data.

`apply_local_force_at_point` ports arithmetic from `0x7bda90` and `0x7bd310`:

```text
worldForce = R * localForce
worldPoint = R * localPoint + position
worldCenterOfMass = R * modelLocalCenterOfMass + position
accumulator.force += worldForce
accumulator.torque += (worldPoint-worldCenterOfMass) cross worldForce
```

`apply_suspension_mode2` now qualifies the complete `0x844090` path through its
original item-ID adapter, manager lookup, transforms and force/torque accumulation.
The native wake queue is disabled in this domain. The formula remains
`(restLength-length)*stiffness - speed*damping`, with the original contact gates.
All supplied poses/model values and output buffers are validated; late overflow
rejects without a partial caller update. **4,286 actual force-call branches**
execute in the 20,000-case oracle. Other suspension modes, wheel contact updates,
sleep/wake queue behavior and effective race tuning remain unresolved.

## Materials

The initializer writes its table into BSS at `0x1fa9a70`; reading disk bytes
alone would miss it. Executing `0x4df599..0x4dfbb8` recovers **80 entries of two
floats**, all matched by the SDK's constructor. The first field participates in
the impact tangent limit in `0x83fdd0`; the second is combined by `0x4eff20`.
No material names are assigned without separate ID evidence.

Most constructor entries are `(1, 0.5)`. Exceptions are raw IDs 3, 9, 10, 11,
23, 24, 25, 68 and 78; ID 10 has restitution `-0.5`. The combiner multiplies two
positive values, selects the nonpositive value when only one is nonpositive,
and adds two nonpositive values. Its negative-value behavior is preserved.

`surface_response` ports full arithmetic of `0x7bf0d0`. It masks surface IDs to
their low byte and applies context-dependent friction/restitution overrides:
vehicle/vehicle, vehicle versus category zero with variant 9 or 13, the runtime
generated class ID, and an A-side special class. That runtime ID is supplied
explicitly. The original initialized class getter executes under synthetic TLS;
it is not skipped. All seven response branches are covered. Constructor defaults
are not verified effective race settings, and this contact response is not the
complete tire/slip model.

## Tools and reproducibility

[Official Ghidra 12.1.4](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build)
and Temurin JDK 21 are installed only under project `tools/`, from hash-pinned
official archives. Global Java configuration is unchanged. The headless script
defines explicit PE unwind-chain bodies, follows one direct-call layer and
exports **169/169 selected functions**. It checks script completion markers and
every export status, since launcher exit zero alone did not detect an earlier
script error. C output carries the executable hash and remains research evidence;
decompiler-inferred signatures and types require instruction-level verification.

```powershell
python scripts/install_ghidra.py
./scripts/run-ghidra-physics.ps1
./scripts/run-release-checks.ps1 -SkipLegacy
./scripts/run-physics-research-checks.ps1
```

All **17 CTest cases pass**. Native regressions include cooking/tree/contact composition, SAT geometry,
curve modes, off-center torque, suspension gates, material overrides, polygon
contacts and transactional rejection. The external installed C++20 consumer
calls every new module. Unchanged legacy .NET groups are not rerun by
`-SkipLegacy`; their earlier evidence is retained. The release also checks native
PPO/checkpoints, DLL ABI, Rust formatting/clippy and Rust-to-native inference.

Machine-readable proofs are retained under `local/recon/`, including
`mesh-convex-evidence.json`, `vehicle-arithmetic-evidence.json`,
`geometry-vehicle-qualification.json`, all original-code oracle reports, binary
fixtures, selected assembly, and the static Ghidra exports. The auditor verifies
the original hash, case counts, defined-output flags and current source hashes.

Remaining work is tracked as unfinished: full vehicle forces and tire state,
actual race model/curves/assets, other geometry handlers, complete scheduler,
authoritative tick-aligned capture and held-out trajectory validation. The SDK
continues to expose `full_trackmania_physics=false`.
