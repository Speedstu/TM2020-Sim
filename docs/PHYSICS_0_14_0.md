# Physics reconstruction 0.14.0

The SDK now contains **50 public arithmetic operations with 20,000 original
instruction cases each**, within documented domains. This release adds
complete contact-patch grouping, local center-force accumulation and the
vehicle's auxiliary force branch at `0x84da80`. It also connects recovered
kernels into an **autonomous convex-body/static-mesh simulator** with owned
geometry and deterministic snapshot replay.

This is not yet the complete faithful Trackmania car simulator. The full
tire/slip generator, effective race curves, Stadium assets, general joint
position passes and adaptive contact-interleaved pose scheduling remain
unfinished. The standalone scene uses explicit synthetic geometry and tuning;
its end-to-end game fidelity has not been established. Prior in-game gold and
602 audited PPO transitions remain historical evidence, without a new claim
of improved learning strength.

## Contact geometry becomes constraints

The entire original `0x804a10` executes with synthetic TLS, a precommitted
native block allocator and sufficient container capacity. Material response
calls and scratch cleanup execute normally; no original function is skipped
or patched. The executable SHA remains
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.

The differential compares **693,629 contact points and 295,520 patches** across
20,000 cases. There are 138 cases crossing a native chunk boundary. Grouping
operates in independent chunks of at most **255 contacts**, matching low bytes
of both surface IDs and a normal dot product of at least **0.999**. Separate
runs can join an earlier matching primary run; output point order follows the
primary run and its linked runs, rather than a global input-order filter.
The patch normal comes from its primary run. Material response uses the same
recovered context-dependent routine as the prior release.

Per-point separation is exactly
`sqrt((penetrationX * penetrationX + penetrationY * penetrationY) + penetrationZ * penetrationZ)`.
It is a vector length, including when a sphere/mesh radial normal differs from
its penetration direction. Native object pointers, container bookkeeping and
unused bytes are replaced by owned result objects. Heap growth is outside the
qualified domain.

Connecting the stages exposed a previous SDK guard that rejected negative
restitution. The native material table can produce these values; contact
preparation activates bounce only for values greater than zero. The guard is
corrected. Both full native contact builders pass a refreshed 20,000 cases
including negative restitution inputs, with no changes to their equations.

## Additional complete vehicle force arithmetic

`apply_local_force`, original `0x7bdd20`, rotates a local force and updates only
linear accumulation. Its complete native path is compared in 20,000 cases.
`apply_auxiliary_vehicle_forces`, original `0x84da80`, also passes 20,000 cases,
including 1,189 cases changing accumulated force/torque. It preserves:

- Local forward speed strictly above 6 and input magnitude at least `1e-5`.
- Strict `0.1` activation thresholds for vehicle scalars at `+0x98/+0x9c`.
- Raw status tests at `+0x176c/+0x1370`.
- Configuration coefficients at `+0x1efc/+0x1f00/+0x1f04/+0x1f08`.
- Center-force and front/rear force-at-point order, including zero-force calls.
- Wheel gate word at `+0x70`, distinct from the contact word at `+0x34`.

The API retains verified source-offset field names where gameplay meaning is
not yet established. At most four wheels and a nonnegative `+0x1f00`
coefficient are supported. Wake-queue bookkeeping remains disabled in the
qualified native manager. This is a complete helper, not the complete tire
model or proof of live force-variant execution.

## Autonomous rigid contact world

`RigidMeshWorld` owns copied convex topology, cooked triangles, the native AABB
tree, material settings and solver configuration. Its explicit composition is:
force/velocity integration, convex/mesh collision, patch/material processing,
static Jacobian/friction preparation, native contact iteration order,
full-interval pose integration and position sweeps. The caller supplies all
tuning; the scene selects the recovered Jacobian constraint path. Sleeping,
adaptive CCD and general joints are outside this runner.

Failed steps preserve body state, caller forces and tick. Snapshots are bound
to the same world's immutable geometry/settings and reject invalid states or
foreign-world restoration. Tests verify ownership after input geometry is
changed, falling-body floor settling, negative restitution, linked patch order,
chunk boundaries and bit-exact replay after restoration. The C++ port executes
without Python, original game instructions, game assets, injection or a running
game. Composition validation is separate from original-instruction arithmetic
qualification; it does not prove the complete original game step.

Run the installed standalone example:

```powershell
./dist/sdk-windows-x64/bin/tm2020_rigid_mesh_demo.exe 10000 local/scene.csv local/scene.json
```

The scene is a synthetic box and two floor triangles. The interval is an
explicit `0.01` seconds for the example, not a newly verified internal race
clock. Reported timing includes snapshot replay and describes only this small
scene. The public API accepts caller-supplied owned scene geometry/settings.

A separately copied executable also completes 100,000 scene ticks with
236,128 generated contacts and bit-exact snapshot replay. Its imports are
Windows system/CRT libraries; no SDK DLL is needed. An additional 62-function
Ghidra vehicle research export supports continued wheel/suspension analysis.
Decompilation counts overlap earlier exports and are not arithmetic proof.

## Reproduce and inspect

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The release retains native regression, every arithmetic differential,
reflection/atlas/source audits, PPO/BC and C/Rust ABI checks, SDK installation
and an independent installed C++ consumer. The unchanged .NET suite is included
when `-SkipLegacy` is omitted. New installed headers are `recovered_patches.hpp`
and `recovered_world.hpp`; auxiliary vehicle APIs extend `recovered_vehicle.hpp`.
Previous constraint and manifold evidence is retained in
[0.13.0](PHYSICS_0_13_0.md) and [0.12.0](PHYSICS_0_12_0.md).
