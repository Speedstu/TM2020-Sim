# Trackmania 2020 - native read-only pose and GBX course markers

Project: H:\Projects\Trackmania2020-RE. Game unchanged on D:.
No Openplanet, remote injection, memory writes, or multiplayer bot control.

## Confirmed improvements on the live Solo session

- Native C++ tm2020_pose_reader.exe samples nine independent numeric coordinate
  copies from the RUNNING Trackmania process using ReadProcessMemory.
- Game PID 13884; 200/200 samples over ~2 seconds agreed across all nine copies.
  Stationary XYZ about (1148.68, 11.125, 1188.42), maximum measured drift
  around 0.000122 units. No physics frequency inference from idle observations.
- Versioned V3 manifest verifies canonical PID GetProcessId, process creation
  FILETIME, exact SHA-256 of installed Trackmania.exe and XYZ axis convention.
  Historical Windows OpenProcess alias issue was caught by negative tests.
- test-live-pose-reader.ps1 passes wrong PID, wrong binary hash, wrong
  process creation timestamp, and invalid axis-layout rejection tests.
- Earlier incorrect ZYX V1/V2 source files quarantined under
  local/recon/legacy-unverified; legacy generator now invokes V3.
- These are session-specific candidate copies, not yet a verified authoritative
  physical-state pointer chain or a car update callback.

## Native C++ GBX course marker extraction

Map::course_markers() now identifies start/checkpoint/finish markers from
native road blocks and anchored items, without guessing finish from block name.
On real Fall 2026 - 01 (MapID 361913, UID ypPmohQofd72MyTsIsijKfrJH98),
the test confirms exactly 1 start at XZ=(1200,1360), 3 checkpoints, and
3 anchored finish gates at X=(784,816,848), Y=30, Z=1360.
Anchored items provide known authored height; regular grid blocks do NOT
expose authoritative driving Y. Exact road connectivity remains unverified.

Run:
  & 'H:\Projects\Trackmania2020-RE\scripts\test-live-pose-reader.ps1'
  & 'H:\Projects\Trackmania2020-RE\scripts\run-framework-tests.ps1'

Still missing: stable car owner pointers across restarts, authoritative physics
state at 100Hz, true inputs/vehicle velocity/rotation/tire contacts, full
Stadium collision geometry, accurate counterfactual reset/step simulation and
high-quality autonomous game-driving bot. No faithful Trackmania RL training.
