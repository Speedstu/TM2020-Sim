# Trackmania 2020 SDK — verified continuation, 2026-10-20

The user's daily automatic monitor is DISABLED. This is manual development only.

## Tested in this session

* Installable C++20 SDK package: dist/sdk-windows-x64 with tm2020.hpp, libtm2020_sdk.a, native CMake Config. Independent CMake project successfully uses find_package(tm2020 0.2 CONFIG REQUIRED) and links TM2020::tm2020_sdk.
* Map/Replay dataset: 24 map+replay pairs parsed and loaded by C++; offline BC training operates on 17 training maps + 7 distinct held-out maps. This BC model does not beat neutral steering (0.431778 vs 0.423888).
* New native tm2020_capture.exe loopback-only TCP collector on 127.0.0.1:24826, reads newline JSON and records to H:, no access to game process. Synthetic test captured and validated 16/16 records, with no loss.
* Prepared read-only Openplanet/VehicleState plugin source at openplanet/TM2020PhysicsLab. Disabled by default; sends vehicle position, velocity, steering, gas, brakes, gear, RPM, wheel slip to native collector. NOT installed/loaded into Trackmania; plugin Update callback is not a guaranteed physics tick.
* Static Openplanet AngelScript check is green, 0 errors and 0 warnings against historic Openplanet type DB 1.29.14, with dependency VehicleState exports. In-game test and comparison to current game build remain outstanding.
* Added binary .tmcol geometry format with explicit magic/version/count/size and finite geometry checks. It caches triangle vertices only, NOT prebuilt BVH nodes. Native C++ and Python loaders support it. Tests with 2400 rays were identical to OBJ.
* Measured in this Windows session: 43595 triangles OBJ parse + BVH 551.86ms vs .tmcol 18.36ms, 6760 triangles OBJ 98.56ms vs .tmcol 2.50ms. These gains only apply to available embedded physical meshes, not game-native Stadium blocks.
* Original Trackmania game unchanged on D:; all development, binaries, caches, datasets, snapshots and optional tools on H:.

## Still blocked before actual Trackmania RL

* Built-in Stadium collision meshes and drivable surface material physics missing.
* No proven 100Hz game engine state snapshots, no controlled real game telemetry collected yet.
* No physically faithful counterfactual step(action)/reset/rewind/suspend or vectorized multi-map physics.
* Supervised C++ imitation baseline worse than trivial neutral-steering reference and requires oracle future replay trajectory.
* Full simulator fidelity cannot be proven by a static plugin check or synthetic 100Hz messages.
* No background task/automation monitors or develops the project.

## Commands
 & 'H:\Projects\Trackmania2020-RE\scripts\run-native-training.ps1'
 & 'H:\Projects\Trackmania2020-RE\scripts\cache-collisions.ps1'
 & 'H:\Projects\Trackmania2020-RE\scripts\test-live-capture.ps1'
 & 'H:\Projects\Trackmania2020-RE\scripts\status.ps1'

Openplanet plugin source and historical types for static checking are both stored under H:.
