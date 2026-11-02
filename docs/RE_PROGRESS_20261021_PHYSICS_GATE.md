# Trackmania 2020 — native RE, state observer and SDK validation

Date: 2026-10-21. User's Windows desktop. Source H:\Projects\Trackmania2020-RE.
Installed game D:\SteamLibrary\steamapps\common\Trackmania.
Game version 2026.2.2.1751, pinned by SHA-256. Ubuntu/Openplanet NOT required.

## New native SDK state estimation

- C++20 native/include/tm2020/pose_kinematics.hpp and
  native/src/pose_kinematics.cpp: causal velocity estimate from XYZ samples.
  TwoPointSecant default, WeightedLeastSquares optional, reset on teleport,
  duplicate/reversed time or stale long gap.
- Real held-out replay validation: 7 maps / 3,284 eligible samples.
  Two-point speed MAE **1.9583 km/h**; weighted 100ms speed MAE
  **2.8600 km/h**. Default was changed to the demonstrably better 2-point.
  Velocity vector MAE **1.6381 m/s** for the selected 2-point estimator.
  These are based on **recorded 50ms positions** and measured replay state,
  NOT realtime 100Hz validation, not internal car velocity.
- Report: local/recon/pose-kinematics-heldout.csv.

## Reverse pointer graph research

- New read-only Windows native/src/pointer_links.cpp. Requires manifest
  v3 pinning canonical PID, process creation FILETIME, installed exe SHA-256.
  Scans readable private pages and main module image; collects only a bounded
  list of pointer-to-struct hypotheses (relative offsets within 2KiB for
  first-level sources, 1KiB second-level). NO raw game memory dumps, patches,
  DLL injection or gameplay actions.
- On the already running, authenticated Solo process PID 13884:
  * 768MiB bound: 395 first-level, 1,388 second-level candidate references.
  * 2,048MiB bound: **399 first-level**, **1,390 second-level** references.
  * **ZERO static module references found** in those two levels.
  * Both scans are INCOMPLETE due to the chosen per-level memory budget.
  * No pointer chain is verified across process restart, no physical owner
    pointer found. These are candidate backlink relationships, not a
    usable/portable SDK vehicle state locator.
- Reports local/recon/reverse-pointer-edges-2048mb.json and previous
  ...current-session.json. Read-only selftest passes.

## Nearby quaternion-like numerical fields in actual running game

- scripts/inspect_live_pose_neighborhood.py samples only 28 to 320 bytes of
  FLOAT aggregates around independently map-correlated position copies
  (never arbitrary page dumps). Nine pose-copy addresses available; for
  some, four preceding float fields are approximately a unit quaternion:
  **(0.6981, -0.0854, -0.7057, 0.0863)**.
- The C++ native/src/live_pose_reader.cpp was extended to read 4 candidates
  before XYZ, reject non-unit-length data and require quorum across
  independently located copies.
- 160/160 samples in this Solo session passed POSITION consensus and
  quaternion-CANDIDATE consensus; raw quaternion fields are written to
  local/recon/live-position-quat-candidates.csv with explicit
  **orientation_verified=false** and **vehicle_state_verified=false**.
- Candidate remains an unproven rendering/visual pose; cannot name
  quaternion component convention, chassis heading or rotation state without
  a controlled in-game turn compared with replay/video physics.
- scripts/test-live-pose-reader.ps1 enforces quaternion quorum but also
  that all fields remain labeled unverified.

## GBX course navigation anchors

- Native Map::course_markers() reads block and item authored markers.
  Fall 2026 - 01 real official map has 1 start, 3 checkpoints, 3 item finish
  gates. No inferred road connectivity or collider geometry from markers.

## Existing baseline and hard blockers

- Installed CMake C++ SDK, map/replay parsers, known-route KD-tree, partial
  custom item collision BVH and C-ABI action advisor are real and tested.
- Experimental fast 100Hz batched toy sandbox is NOT Trackmania physics.
  Held-out real replay differential fails (0.952m position MAE / 50ms).
- Native Stadium collision meshes, tire and suspension forces, actual
  authoritative 100Hz car state, game inputs and stable pointer chain still
  UNRESOLVED.
- Bot C ABI runs in a separate test-host, NOT injected into Trackmania,
  and an actual powerful online/offline live game bot is NOT finished.
- Full headless high-fidelity RL training is therefore **NOT READY**.

## Reproduction

From Windows PowerShell:

  & 'H:\Projects\Trackmania2020-RE\scripts\run-framework-tests.ps1'

One-off bounded read-only pointer scan on the currently running game:

  & 'H:\Projects\Trackmania2020-RE\native\build\tm2020_pointer_links.exe' --scan 'H:\Projects\Trackmania2020-RE\local\recon\session-pose-candidates-v3.txt' 'H:\Projects\Trackmania2020-RE\local\recon\reverse-pointer-edges-2048mb.json' 2048

Read-only numeric candidate visual pose:

  & 'H:\Projects\Trackmania2020-RE\native\build\tm2020_pose_reader.exe' --sample 'H:\Projects\Trackmania2020-RE\local\recon\session-pose-candidates-v3.txt' 'H:\Projects\Trackmania2020-RE\local\recon\pose-observed.csv' 150

All runtime memory offsets in the manifest are PID- and process-start-bound
and MUST NOT be reused after a restart. No hourly tasks or continuing
background work were created.
