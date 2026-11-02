# Trackmania 2020 SDK — 20 October 2026, continuation

The goal of a faithful, fully counterfactual 100Hz offline Trackmania 2020 physics engine is NOT yet achieved.
Project stays on H:\Projects\Trackmania2020-RE, game untouched on D:\SteamLibrary\steamapps\common\Trackmania.
Reused existing .NET 9, Python 3.11, NumPy, PyTorch CPU, and MinGW. No venv or global dependency install.

## Verified progress
- 20 extra public TM2020 map/replay pairs from TMTAS/Trackmania Exchange, verified by MapUID. Total 24 distinct maps, 12,430 50ms vehicle observations; 11,024 in-race 50ms transitions.
- Source corpus manifest: local/corpus/manifest.json; first four original replays in local/dataset-manifest.json.
- Cross-map ridge benchmark 24 maps: speed MAE 4.532 km/h vs naive 3.587; yaw MAE 2.037 deg vs naive 2.020. NOT suitable as simulator.
- CPU PyTorch MLP surrogate with grouped 5-fold test: speed 3.482 vs naive 3.587 km/h, yaw 2.271 vs naive 2.020 degrees. Candidate checkpoint in local/surrogate_v1; NOT simulator-grade.
- Held-out 17 train / 7 test map input timing calibration: no extra shift, steering float approximately (2*raw-1)/255. On 3,304 held-out 50ms recorded vehicle frames: 91.2% steer errors within 1/255, 0 gas mismatches and 23 brake mismatches. Not proof of exact 100Hz game input timing.
- Built self-contained C++ BVH DLL with stable C ABI, supports batched native rays from Python via NumPy+ctypes without process launch overhead. SDK: sdk/trackmania2020/geometry.py.
- Python read-only SDK: ReplayCorpus, MapLayout, ReplayTrajectory, PartialCollisionWorld. Validates unique map UIDs, no crossmap leakage, data frame timestamps, and colliders. Source: sdk/trackmania2020.
- Fixed possible collision-object alias bug by matching nested model item paths instead of basename only.
- Test script extended to rebuild DLL, exercise SDK and input calibration.
- Native collider inventory is still PARTIAL: 43,595 triangles on map 365553, 6,760 on map 364956. Geometry world transforms require independent verification; native Stadium block meshes absent.
- Collision coverage on map 365553: downward rays intersected known embedded meshes at only 3/562 replay positions. This does not mean player is airborne; most native track geom is unavailable.

## Not complete / must not claim
1. Native Stadium collision/terrain/block assets inside the 21 installed NadeoPak v18 game archives.
2. Verified 100Hz differential state snapshots, tire contact forces, steering and reactor physics, material friction.
3. A counterfactual time-stepping physics model reproducing arbitrary action changes.
4. Deterministic exact physics rewind/restore and GPU/CPU vectorized full simulation.
5. Live offline Trackmania 2020 telemetry via Openplanet (not installed on this PC).
6. A bot trained in a proven faithful simulator. This project explicitly does not start full RL training from a known-inaccurate surrogate.

## Commands
PowerShell:
  & 'H:\Projects\Trackmania2020-RE\scripts\run-all-tests.ps1'
  & 'H:\Projects\Trackmania2020-RE\scripts\status.ps1'

Future research: authorized native block geometry, Openplanet offline experimental instrumentation and genuine game-vs-sim validation; then train/reinforcement learning. Avoid bypassing any anti-cheat/DRM or automating public matches.

## References
https://tmtas.exchange/docs
https://github.com/trackmania-rl/tmrl
https://github.com/openplanet-nl/vehiclestate
https://www.trackmania.wiki/wiki/Tick
https://github.com/BigBang1112/gbx-net
