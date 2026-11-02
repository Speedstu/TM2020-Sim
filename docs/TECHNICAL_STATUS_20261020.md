# Trackmania 2020 reverse engineering — technical status

Date: 2026-10-20. Main PC SPEEDMKV; original Trackmania.exe v2026.2.2.1751.
Workspace is **H:\Projects\Trackmania2020-RE**. Game is installed on **D:**.
No Python virtual environment or global package reinstall; pre-existing .NET 9,
Python 3.11 + NumPy and MinGW G++ are used. Project caches set to H:.

## Completed and verified

1. **Official game identity**: SHA256 and section metadata recorded, all 21 package entries inventoried, game executable and packages never modified.
2. **Eight Map.Gbx parsed** into structured JSON including all anchored items, full lists of blocks, baked block counts, world placements and transforms.
3. **Four Replay.Gbx decoded**: 2,885 vehicle visual samples at 50ms, 4,196 change events for steering, throttle, brake. Wheel materials and telemetry exported.
4. **Four real map/replay pairs** UID verified, manifest saved; 2,641 race-valid transitions after filtering post-finish telemetry.
5. **Leakage-safe dynamics reference**: fixed ridge regression on per-map holdouts. 50ms one-step speed delta MAE 2.608 km/h vs naive 2.105 km/h (worse); yaw delta MAE 1.012 deg vs naive 1.610 deg (better). Never call this an accurate physics engine.
6. **Embedded custom assets**: ZIP extraction restricted to project output, limited decompressed bytes, checks path traversal.
7. **Item.Gbx**: inspect CGameCommonItemEntityModel and CPlugStaticObjectModel, export CPlugSurface.Mesh vertex and triangle arrays as OBJ; distinguish real *physical_shape*, *trigger_shape*, and *IsMeshCollidable* visual-only shapes. Trigger volumes are not used as drivable colliders.
8. **Partial local collision map**: place extracted physical_shape OBJ vertices at matching map Item model instances, with tentative Y(yaw)*X(pitch)*Z(roll) transforms (not yet validated). 43,595 triangles on TMX 365553, 6,760 on TMX 364956.
9. **Native 64-bit C++ BVH raycaster**: no game API needed; ray intersection, normal, distance, batch rays, diagnostic benchmark. 1000/1000 synthetic triangle-normal rays hit per mesh; measured ~404k/536k rays per second in this specific benchmark.
10. **Reality check**: of 562 replay state positions on TMX 365553, only three downward rays intersected the partial embedded geometry. This shows inadequate mesh coverage for a usable full-map training simulator.

## NOT complete

- Protected/installed **native Stadium block geometry**; no extraction from NadeoPak v18 container content.
- Physical meshes for collidable visual-only items; custom material IDs & exact per-triangle friction coefficients.
- Exact car dynamics, hidden internal simulation state, 100Hz physics stepping, deterministic reset/save/restore, closed-loop validation and multi-environment parallelization.
- Openplanet telemetry/plugin integration (not installed, and user requested no newly stored files on C:).
- Correct placement rotation conventions and physics contact error benchmark from official game in real time.
- Any bot that can drive, train or generalize reliably to arbitrary tracks.
- Do not bypass DRM, anti-cheat or access controls; no multiplayer automation.

## Tool commands

Run the complete local tests:
```powershell
& 'H:\Projects\Trackmania2020-RE\scripts\run-all-tests.ps1'
```

Print current status:
```powershell
& 'H:\Projects\Trackmania2020-RE\scripts\status.ps1'
```

## Next research gates

A. Capture first-party supported game telemetry / offline repeatable inputs and measure timestamp and replay integrator differences.
B. Determine how to obtain *authorized* built-in collision geometry; use Openplanet-compatible export tooling and existing public GBX.NET APIs instead of bypassing package encryption.
C. Compare world geometry raycasts to known reference points to validate transform ordering/coordinate convention.
D. Model tire contact, slip, gears, steering, air control, surface friction and vertical suspension against held-out real replay traces.
E. Only after multi-step differential tests and track-complete colliders implement headless 100Hz reset/save/restore and vectorized RL training.

The source code and tests are reproducible on the installed machine.
