# Physics reconstruction 0.12.0

The native SDK now has **43 public arithmetic operations with 20,000 cases
each against original instructions**, within their documented domains. Eight
operations are added to [0.11.0](PHYSICS_0_11_0.md): five convex feature/segment
kernels, two complete convex manifold arithmetic handlers, and the contact
island iteration scheduler with general joint/callback spans empty.

**Exact complete vehicle physics remains unfinished.** Tire/slip forces,
effective race tuning, Stadium collision assets, general joints and the
contact-interleaved adaptive pose scheduler remain necessary. This release
does not establish a stronger learned bot or add live training evidence.

## Original instruction evidence

Pinned executable build 2026.2.2.1751, SHA-256:
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.

The original executable is unchanged. Test processes execute selected original
routines or emulate them with Unicorn 2.1.4 and synthetic memory. No skipped
original functions or substituted instructions are used. Runtime SDK ports
require neither the executable nor a game process. Sufficient-capacity owned
buffers replace native allocation, and synthetic TLS takes the original
already-initialized scratch/null-profiler branches.

Ghidra also exports a separate 47-function contact/constraint research set.
These decompilations guide further investigation; they are not counted as
qualified arithmetic operations.

| Operation | Original RVA | Differential cases |
| --- | --- | --- |
| `select_edge` | `0x1cb980` | 20,000 |
| `select_face_from_normal` | `0x1cbcb0` | 20,000 |
| `select_incident_face` | `0x1cbef0` | 20,000 |
| `edge_frame` | `0x1cc200` | 20,000 |
| `closest_edges` | `0x1c9080` | 20,000 |
| `collide_convex` | `0x19cec0` | 20,000 |
| `collide_convex_mesh` | `0x1b4410` | 20,000 + 129-candidate saturation |
| `solve_contact_islands` | `0x7f6ec0` | 20,000 |

## Convex contacts

Feature selection preserves the last feature on projection ties. Segment
distance uses the complete native piecewise minimizer, including the parallel
branch and signed endpoint parameters. Both zero half-lengths in that branch
divide by zero in the original and are rejected by the SDK. Unit directions,
rigid transforms, valid ordered closed convex topology and finite bounded
inputs are required.

Convex/convex qualification compares **28,143 contact points**, covering both
face witnesses and cross-edge witnesses, arbitrary independent 3D transforms,
contained and separated shapes, tangency, boolean queries and emission gates.
Convex/mesh qualification compares **37,748 contact points**, using two
shared-edge floor triangles and a wall with independent 3D transforms. It also
compares saturation with 129 overlapping triangles: the original and port both
retain the first **128 triangle IDs**. Original scratch cleanup is verified.
Mesh SAT expands the convex interval by the native approximately `1e-4` margin.
Shared-edge behavior and emission order are retained without invented deduping.

Relative translation projects positive and negative translations separately,
then adds them. Combining their subtraction before projection changes float
rounding. Convex/convex multiplies local penetration before rotation;
convex/mesh rotates its normal before multiplying by depth. Both orders are
preserved. Only defined contact geometry and material IDs are compared;
unused native stack bytes and undefined flag bits are not exposed as data.

The retained polygon restriction still applies: native near-parallel clipping
intersections can append uninitialized stack contents. The SDK rejects this
branch instead of making up deterministic values. Qualification of these
arithmetic handlers does not qualify their registered three-argument dispatch
wrappers, allocator behavior or every possible convex topology.

## Contact scheduling

Native islands are `0x140` bytes. Contact spans occupy `+0x10`, `+0x20`, `+0x40`,
`+0x50`, `+0xa0`, `+0xb0`, `+0xd0` and `+0xe0`. Configuration words at 0, 4 and 8
are the static-friction, dynamic-friction and total velocity iteration counts.

For each velocity iteration the original visits all islands for dynamic
compact normals and friction below the dynamic threshold, then visits all for
static compact normals and friction below the static threshold. It next solves
static Jacobian normals, dynamic compact final normals and Jacobian normals,
and finally static compact final normals. **Friction consumes the previous
iteration's Jacobian normal impulse.** Exhausting a friction threshold does
not stop the remaining unilateral normal passes.

The oracle verifies the complete original call trace for every case, including
zero iterations, zero through three islands, empty and populated contact
spans, shared bodies and independent friction thresholds. General island spans
at `+0x30`, `+0xc0`, `+0x120`, `+0x130` and external callback constraints are
empty in this qualified domain; the original empty helper calls still execute.
The API stages state and accumulated impulses so a late invalid constraint
does not partially commit an earlier pass.

## Reproduce

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The release script runs native CTest, every retained arithmetic oracle,
reflection/atlas and source-hash audits, native PPO/BC checks, Rust lint and
native DLL inference, SDK installation and an independent installed C++
consumer. The unchanged legacy .NET suite is included when `-SkipLegacy` is
omitted. The installed headers include `recovered_features.hpp`,
`recovered_convex_collision.hpp` and `recovered_solver.hpp`.

Explicit-domain semantic tests cover cube face depth/orientation, convex floor
contacts, parallel segment endpoints, friction-before-normal scheduling and
late transactional rejection. Earlier in-game gold and 602 audited PPO
transitions remain historical evidence, not validation of the new physics.
