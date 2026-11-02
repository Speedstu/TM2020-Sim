# Trackmania 2020 RE — native physics research continuation

Date: 2026-10-20 (late evening), Windows SPEEDMKV.
Sources, datasets, builds, plugins and logs: H:\Projects\Trackmania2020-RE.
Game remains untouched: D:\SteamLibrary\steamapps\common\Trackmania (version 2026.2.2.1751).

## Goals and trust boundaries

The long-term goal is a faithfully measured 100 Hz Trackmania 2020 offline
simulator that responds to arbitrary controls, with correct Stadium collisions,
replayable reset/restore and efficient batched RL steps.

**THIS GOAL IS NOT YET ACHIEVED.** The speed of native C++ and the new
experimental 100 Hz step/reset implementation do not establish fidelity.
The experimental solver is kinematic with a flat plane and made-up force gains;
it is a test rig for architecture, not the game.

No anti-cheat/DRM bypass, unauthorized game asset extraction or online race
automation. All probes use local replay data and read-only file analysis.

## Tested C++20 improvements in this session

1. RoutePlan in tm2020.hpp + native/src/route.cpp. It constructs reference
   routes from known real replay positions, preserves segments across detected
   teleports, and returns nearest point, lookahead target, heading, speed and
   cross-track error. It does NOT handle unknown maps without a reference route.
   KD-tree nearest-point search in 3D is exact for the search score and was
   compared against independent full linear scans on 24 distinct maps.
   Measured on the 2,356-point reference trajectory: ~1.4–1.5 million
   lookups per second for 100k randomized queries on the current CPU.

2. Native empirical system-ID: native/src/system_id.cpp. Evaluated 11,026
   recorded 50ms state transitions from 24 public Trackmania 2020 runs:
   10,823 retained after gap/teleport/extreme discontinuity filtering and
   203 excluded, clustered into 307 (surface, controls, speed-bin) categories.
   Output local/system-id/empirical-handling.csv includes count/median/quantile
   of observed acceleration and yaw change. These are NOT magic physics
   constants: speed deltas blend inertia, road slope, jumps, boost, etc.

3. Explicitly *non-faithful* 100 Hz scaffold:
   native/include/tm2020/experimental_sim.hpp and
   native/src/experimental_sim.cpp implement a deterministic flat-plane
   0.01-second fixed-step engine with reset, snapshot/restore and large batches.
   It has no true gravity, tires, materials, Stadium collisions, boosters or
   real Trackmania dynamical parameters. 65,536 environments x 1000 steps:
   65,536,000 transitions at ~61.5 million/s on this CPU. Exact binary
   restoration and invalid-input atomicity are tested.

4. Genuine differential test: native/tests/differential.cpp starts the
   experimental sandbox from measured replay states, reconstructs input
   commands at 10 ms steps, advances five 100 Hz ticks and compares the result
   to the next 50 ms real replay observation on **7 held-out maps** (3,297
   transitions). Results:
   * Mean position error 0.95231 m / 50ms (p95 3.02653 m)
   * Mean speed error 16.8708 km/h / 50ms
   * Mean yaw error 3.01322° / 50ms
   * Simple baseline pos + measured velocity * 0.05 is much better: 0.08292m.
   **FAIL fidelity**. Report: local/system-id/differential-heldout.csv.
   This is why the toy sandbox is explicitly not RL-ready for Trackmania.

5. Velocity timestep inference: native/src/integrator_probe.cpp estimates a
   scalar effective integration dt on the 17 training maps and tests it on
   the other 7. Fitted dt=0.0498935s, nominal=0.05s.
   Heldout test position MAE (single 50ms step) with fitted dt: 0.0836962m;
   with nominal dt: 0.0829194m; with oracle average measured velocity from
   both endpoints: 0.0587361m (future state leakage, diagnostic only).
   **Not** proof of 100Hz physical integration fidelity.

6. C++ and CMake package: native libraries and new public experimental header
   compile and link into a standalone separate CMake consumer app on this PC.
   24/24 Map/Replay/RoutePlan tests pass, KD algorithm validated by brute force.

7. Openplanet passive capture plugin was extended to include map UID,
   RaceStartTime and SimulationTimeCoef in telemetry. Historical 1.29.14
   Openplanet API static checks report 0 errors/warnings. The native loopback
   collector and validator pass a synthetic 16-frame test with a mapUID,
   but no in-game runtime test has occurred. The plugin isn't installed
   to the game and is disabled by default; it doesn't steer/alter the game.

8. The full 8-stage reproducible test gate is scripts/run-framework-tests.ps1.
   Status file local/framework-capabilities.json v2 explicitly marks full
   headless Trackmania RL false.

## Known gaps

- Native Stadium block collider geometry from the game's archives;
  currently only embedded custom-item partial meshes (e.g. 43,595 triangles on
  one map) are available, and they cover almost no driving trajectory.
- A true, validated 100 Hz vehicle state measurement from the game. Replay
  vehicle states are sampled every 50ms; input events have 10ms granularity.
- Openplanet runtime/passive capture and validation on a local actual match.
- Identified steering/tire/friction/vehicle/air/reactor/booster integrators.
- Actual counterfactual (responds to arbitrary inputs) accurate Step/Reset/Rewind
  and a closed-loop high-speed training environment for unseen maps.
- An actually capable autonomous trained bot. Offline C++ BC is weaker than
  neutral steering on seven holdout maps. It needs better trajectories/models.

## Commands

From PowerShell on main Windows PC:

    & 'H:\Projects\Trackmania2020-RE\scripts\run-framework-tests.ps1'
    & 'H:\Projects\Trackmania2020-RE\scripts\status.ps1'

Individual native C++ tools:

    & 'H:\Projects\Trackmania2020-RE\native\build\tm2020_system_id.exe' 'H:\Projects\Trackmania2020-RE\local\native-datasets' 'H:\Projects\Trackmania2020-RE\local\system-id\empirical-handling.csv'
    & 'H:\Projects\Trackmania2020-RE\native\build\tm2020_differential.exe' 'H:\Projects\Trackmania2020-RE\local\native-datasets' 'H:\Projects\Trackmania2020-RE\local\system-id\differential-heldout.csv'

No automatic nightly continuation or recurring task was enabled.
