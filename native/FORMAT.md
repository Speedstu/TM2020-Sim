# Trackmania2020 native SDK binary format v1

All binary files are **little-endian**. Floats/doubles are IEEE754 and checked
for finiteness when loaded. Strings are uint16 length followed by UTF-8 bytes.
The files encode **observations**, not an exact or interactive game simulation.

## .tmreplay (TMRDSV1\0)

- uint8[8] magic = \`TMRDSV1\0\`
- uint32 version=1, uint32 n_frames, uint32 n_input_events
- int32 finish_ms, int32 sample_interval_ms (50 for current TM2020 replay states)
- string map_uid, string map_name
- For each vehicle state:
  - int32 time_ms
  - double position_xyz[3], quaternion_xyzw[4], velocity_xyz[3]
  - double speed_kmh, yaw_rad, recorded_steer, recorded_gas, recorded_brake, side_speed
  - uint8 wheel_contact_material_id[4] (unknown=255)
  - uint8 is_ground_contact
- For each input change:
  - int32 time_ms
  - int16 steer_raw (signed 8-bit range or -32768 for unchanged)
  - int8 gas, brake, respawn (-1=unchanged, 0=false, 1=true)

The input event timeline records game input changes, potentially at 10ms ticks.
The vehicle state is **still only sampled every 50ms**. The SDK's
\`Replay::input_at(t)\` applies ordered changes (zero-order hold);
\`recorded_at(t)\` returns the last RECORDED state <= t and refuses queries
outside the available recording. Neither function predicts the real game.

## .tmmap (TMRMAP1\0)

- uint8[8] magic = \`TMRMAP1\0\`
- uint32 version=1, uint32 n_blocks, uint32 n_items
- string map_uid, string map_name
- Each block:
  - string name
  - int32 grid_coord[3]
  - string direction
  - uint8 flags (bit0 ground, bit1 free)
  - uint8 has_position, uint8 has_rotation
  - optional double absolute_position[3]
  - optional double yaw_pitch_roll[3]
- Each anchored item:
  - string model identifier
  - double absolute_position[3]
  - double yaw_pitch_roll[3]

Map metadata is **not enough to infer native Stadium 3D collision meshes**.

## .tmbc (TMBC001\0)

- uint8[8] magic = \`TMBC001\0\`
- double train_feature_mean[24], feature_std[24]
- double weights[24][3] (steering, throttle, brake; ridge regression)

Trained with replay-supplied +250ms future target point ("oracle waypoint").
A real bot would require a planner to provide desired future positions.

## Trust boundary and validation

- All sizes, version bytes, finite numerical values, monotonic timestamps, map UID,
  and trailing bytes are checked by the native reader.
- Player replays and TMX custom items remain in \`local/\` (not in source backup).
- Native geometric BVH is separate: **only embedded custom physical mesh colliders**
  are currently supported and their yaw/pitch/roll transforms are not proven exact.
- Game physics, causal \`step(action)\`, reset/rewind, validated tire forces and native
  full-map collisions are **not implemented**.
- For the user-selected fastest/precise implementation: C++20 runtime does improve
  data and geometry throughput; **it does not improve physics fidelity by itself**.

## Build and run

\`\`\`powershell
& 'H:\Projects\Trackmania2020-RE\scripts\run-native-training.ps1'
\`\`\`

All files are on H:, Trackmania game is unchanged on D:. Reuses system CMake
and MinGW g++, .NET GBX.NET parser remains ingestion-only.
