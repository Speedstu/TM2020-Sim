# Physics reconstruction 0.20.0

This release adds a local captured collision workflow. The 64 arithmetic
operations and their documented domains retain the original-code differential
checks described in [0.19.0](PHYSICS_0_19_0.md). It does not qualify complete
vehicle physics or a complete map collision representation.

## Geometry recovered from Solo memory

The native read-only inventory and capture tools inspect the SHA-pinned build
using a process-bound manifest. They copy numeric type-7 mesh structures, bound
all extents, check finite values and indices, and recheck mesh headers after
copying. No game memory is written. The retained Solo session contains 351
accepted prototypes, 197,692 vertices and 348,332 triangles. For every prototype,
the recovered cooker matches all 30 defined bytes of every triangle, and the
recovered AABB constructor matches the complete captured tree bit for bit.

The instance scan finds 13,619 pointer-plus-orthonormal-pose hypotheses. Exact
geometry/pose deduplication yields 6,805 placements. These are hypotheses:
their membership in the authoritative scene hierarchy is not established.
The conversion preserves separate binary32 Y-X-Z transform operations before
promoting coordinates into the existing native double-precision ray format.
It excludes five triangles degenerate after world-coordinate rounding and
writes 795,089 triangles plus a parallel physical-surface sidecar.

Captured geometry stays in the local user cache; source and evidence archives
contain code, metadata and checksums, without geometry blobs. The installed
native ray runtime needs neither the game nor Python. Python performs cache
conversion and independent qualification, not runtime inference.

## Independent checks and material namespaces

The original pointer table at RVA `0x1f66bf0` contains 80 physical surface names.
The extraction checks every SDK enum name against the SHA-pinned executable.
Physical Asphalt is ID 16; the existing portable dataset represents Asphalt
as 1. Conversion uses the name table and leaves unrepresented names unknown.
It does not change previous replay datasets or trained model inputs.

On the Fall 2026 - 01 reference replay, all 400 in-race grounded states produce
a downward ray hit. Of those, 399 have matching mapped surface material. The
first replay state reports Concrete while captured floor geometry is Asphalt;
this discrepancy remains in the report. The start floor is Y=34 with surface
16. Body-origin clearance percentiles P05/P50/P95 are approximately
0.009265/0.035452/0.085125 m. These are route coverage checks, not tire contact
queries or a predicted vehicle trajectory.

A separate NumPy plane-and-barycentric implementation exhaustively checks
every cached triangle for 256 rays: 197 hits and 59 misses. All nearest hit
distances agree with the native BVH within 1e-7 m; observed maximum error is
about 4.97e-10 m. This checks the cache's BVH against an independent geometric
implementation. It is not an original-game raycast oracle or a proof about
triangle-ID ties.

## Reproduction

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

This rebuilds and tests the SDK, validates retained geometry hashes and original
arithmetic evidence, reconstructs the partial ray cache, runs the native replay
audit and exhaustive differential, and checks the installed independent consumer.
It uses retained local captures and does not require a running game.

For a fresh live session, generate a new read-only manifest and validated
manager binding first; addresses from earlier processes must not be reused.
Native capture entry points are:

```powershell
tm2020_live_mesh_inventory.exe manifest.txt 8192 inventory.jsonl
tm2020_live_mesh_capture.exe manifest.txt inventory.jsonl local-capture-directory
tm2020_vehicle_parameter_probe.exe manifest.txt validated-manager-address parameters.json
```

The retained-cache audit scripts intentionally identify this specific session.
Recapturing another session requires explicit new paths and coverage baselines.
All 20 native shape types, authoritative instance ownership, tire/drive forces,
joint preparation, sleeping and contact-interleaved adaptive scheduling remain
unfinished. The faithful autonomous Trackmania vehicle simulator is not ready.
