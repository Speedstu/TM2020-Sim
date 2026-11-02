# Trackmania 2020: replay observations + inputs

## What is actually decoded

GBX.NET 2.4.5 decodes `CGameCtnGhost.RecordData` with `CPlugEntRecordData.EntList`.
The vehicle visual replay state objects are
`CSceneVehicleVis.EntRecordDelta`.

Each vehicle observation includes:
- **Time**, position (XYZ), orientation (quaternion + pitch/yaw/roll)
- velocity XYZ, game speed (km/h), gear and raw RPM
- recorded steer, gas and brake
- ground contact and roof contact, lateral speed
- for each wheel: ground surface material, icing, dirt, dampener length, slip, wheel rotation
- wetness, turbo, reactor mode, reactor boost level/type and air controls.

`CGameCtnGhost.PlayerInputs` provides event-based inputs:
- an `InputChanges` list of `TrackmaniaInputChange` entries
- `Time`, `StartOffset`, nullable steer/gas/brake/respawn
- state of buttons/steer must be propagated (zero-order hold) between changes.

We compute `tMs = change.Time + group.StartOffset`, sort by time and apply input events
through each recorded vehicle sample timestamp. Each vehicle row preserves **both**
the recorded controls and the inferred event-based controls.

## What is NOT decoded

- This is replay/visual telemetry at **50 ms per vehicle sample** (~20 Hz), 
  not Trackmania's full internal simulation state or per-physics-tick rollback state.
- Physics collision meshes are not decoded, NadeoPak v18 asset content is not extracted.
- Input event timestamps are more frequent but do not imply per-tick physical-state accuracy.
- Car internal tire forces, suspension impulses, hidden integrator state are not guaranteed exposed.
- Replay data includes a trailing segment past the winning time. It must be separated from training data.
- Offline state transitions cannot be regenerated faithfully with an independent physics model yet.
- Difference between event-based and replay-recorded inputs is measured, not ignored.

## Reproducible data and tests

The portable native dataset uses its own material codes: None=0, Asphalt=1,
Concrete=2, Dirt=3, Grass=4, Ice=5, Metal=6, Plastic=7, Rubber=8, Sand=9,
Wood=10, Water=11, unknown=255. These are not the game's physical surface IDs.
The independently recovered 80-entry physical name table has Asphalt=16 and
Concrete=0. Use `tm2020/surface_materials.hpp` to convert; unmapped physical
names return 255 and must not count as verified material matches.

Source: TMTAS Exchange public replay GBX:
`https://tmtas.exchange/api/replay?id=5006` and other public IDs.

Dataset output:
`local/replays/dataset-5006.json` (and 4988, 4992, 5009)

Quality checks (local, Python stdlib only):
`python scripts/validate_dataset.py local/replays/dataset-5006.json`

Reference IDs | vehicle samples | input events | material examples:
- 5006 | 562 | 1138 | Asphalt, Metal, Grass, Wood, Rubber
- 4988 | 929 | 691 | Dirt, Sand
- 4992 | 1071 | 1838 | Dirt, Asphalt, Sand
- 5009 | 323 | 529 | Plastic, Asphalt

Total: **2885** visual vehicle samples and **4196** input events across four different replays.
All four replay IDs are linked to their exact TMX maps by verified MapUIDs in `local/dataset-manifest.json`. Across eight map tests there are 28,712 blocks and 11,893 anchored objects.

All samples within each replay have exactly 50ms intervals, no non-finite values,
and speed agrees with 3.6 * ||velocity|| to within 0.00011 km/h in observed data.
This proves internal consistency of the export, NOT correctness of a reconstructed engine.

Input alignment is not perfect: gas differs on 60/1071 vehicle samples in
replay 4992 (late in replay, around 50.56s onward);
brake differs on 7 samples across replays 5006 and 4988.
Do not blindly treat inferred player inputs as ground truth:
use recorded controls or remove mismatched and post-race samples.

## Next fidelity requirements

1. Validate states on a broad, held-out replay set, across map types and car variants.
2. Obtain the exact geometry and collision material properties (from allowed local sources).
3. Offline controlled experiments: change one input at a time and re-record replays.
4. Reconstruct a minimal dynamical system and compare predicted vs replayed vehicle state.
5. Build rewind/reset/batched simulation after differential validation.
6. Add RL/control with a closed-loop real-game test in an offline setting.
