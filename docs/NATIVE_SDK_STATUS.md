# Trackmania 2020 - C++20 Native SDK status

Game: D:\SteamLibrary\steamapps\common\Trackmania (untouched)
All source code, datasets, model checkpoints and temporary caches: H:\Projects\Trackmania2020-RE
No Python venv or system dependency installation. Python/.NET used only for one-time GBX conversion; the SDK and BC model training/inference are C++20.

## Confirmed working

* CMake builds native tm2020_sdk static library using C++20 and the existing g++.
* Native SDK structs: Map, Block, Item, State, InputEvent, Replay, Dataset, CollisionWorld.
* Replay::recorded_at(time_ms): binary search over OBSERVED 50ms snapshots. Replay::input_at(time_ms): 10ms input event changes using zero-order hold. Neither is a physics simulation.
* Native C++ BVH surface batch raycasts from embedded custom physical meshes (still partial).
* 24 distinct map/replay pairs processed and validated by the native C++ parser. All map UIDs match their replay UIDs.
* Binary dataset format v1: native/FORMAT.md. Source binary files from verified public TMX/TMTAS replays on H: only.
* Reusable native C++ offline imitation trainer: 17 training maps, 7 held-out test maps. 7655 train samples, 3269 test samples.
* Native BC inference loader reads .tmbc checkpoint, expects oracle future waypoint 250ms ahead. This would require a separately developed planner in an autonomous bot.
* Steer MAE 0.431778 vs baseline neutral steering 0.423888 (model WORSE). Gas and brake accuracy equal trivial always-gas/never-brake baselines. Do not call this a good policy.
* Test intentionally corrupting the replay header confirms C++ reader rejects invalid data.

Native executable command on PC:
  & 'H:\Projects\Trackmania2020-RE\scripts\run-native-training.ps1'

Status:
  & 'H:\Projects\Trackmania2020-RE\scripts\status.ps1'

Native readiness file:
  H:\Projects\Trackmania2020-RE\local\native-datasets\native-training-readiness.json

## NOT ready

Full native Stadium built-in collision geometry (native NadeoPak archives are protected), tire/friction constants, exact 100Hz causal physics, state save/restore/rewind, full accurate headless batched simulation and strong autonomous agent. Replay visual state snapshots are at 50ms (20Hz), even though input events are more frequent. Openplanet is not installed due to user's constraint against writing new files to C:.

The project deliberately does not expose physics.step(action) until real-game differential tests demonstrate reliable state transitions. Do not start massive RL with the current surrogate. Native BC learning works technically, but its policy is not game-ready.

Next priorities: authorized native collision source or supported Openplanet offline telemetry in a setup honoring H:/D: only; controlled real vs simulated vehicle tests; accurate physics; genuine counterfactual reset/step and high-speed batches.

Useful references:
  https://github.com/trackmania-rl/tmrl
  https://tm.achepta.com/trackmania-trainer
  https://wiki.trackmania.io/en/third-party-tools/openplanet
  https://github.com/BigBang1112/gbx-net
