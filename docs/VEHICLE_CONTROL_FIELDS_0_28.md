# Internal vehicle control fields 0.28

The SHA-pinned instructions now expose context-specific uses of four
binary32 values. In the wheel-spin input to `0x843190`, `+0x98` gates and
scales a drive-like target through tuning value `+0xd90`; `+0x9c` enters a
separate brake-like branch through tuning value `+0xd94`. The force helper
`0x850e50` also evaluates a response curve from `+0x98 - +0x9c`.

In the force input to `0x850e50`, `+0x1430` is sign adjusted and scaled into the
quaternion helper that rotates a local wheel direction; its magnitude also
selects an angle-curve response. In `0x841500`, the `+0x98` / `+0x9c` selection
feeds `0x8447b0` at `0x8416b7`; the later steering branch reads **vehicle
`+0xa0`** at `0x8416da` and slews `+0x1430` toward that command. The previous
interpretation of `+0x98` / `+0x9c` as steering targets was incorrect. Their
uses in these routines are consistent with the same vehicle record.

Offsets must still be interpreted against each function's actual argument type.
The SDK keeps raw offset names where physical interpretation is unproven.
Raw game controls have not yet been traced into the pedal
scalars or steering target. Replay input quantization, pedal normalization,
controller sign conventions, and valid race configuration domains remain
open. The findings do not establish a complete tire-force model or general
simulator.

The steering update at `0x841500` is called by three SHA-pinned vehicle-update
variants (`0x869cd0`, `0x86b060`, and `0x86bc50`) and the force callback
`0x851f00`. They pass vehicle state into the steering slew path; this confirms
multiple internal update paths, not the public keyboard/gamepad event path.
The wheel-spin update `0x843190` is called from `0x841500` at `0x8415b2`.
Exact call instructions are in the evidence JSON. These callers still do not
establish raw control mapping.

The candidate writer `0x8295c0` is also reached from `0x829950` while that
routine converts a configuration descriptor into an internal array. The two
verified calls are at `0x829a53` and `0x829aaa`. This candidate is therefore
not evidence of a live keyboard/gamepad event decoder.

The other candidate `0x819ff0` copies a 0x58-byte body-interaction record into
an internal registry. Its verified callers `0x80f5f0` and `0x81a820` process
interaction/force data; they do not reveal writes from a raw input event.

`reverse_vehicle_control_fields.py` checks the relevant instruction bytes
against the pinned executable and emits
`local/recon/vehicle-control-fields-evidence.json`.
For the bounded decompiler slice around these branches, run
`./scripts/run-ghidra-physics.ps1 -ResearchSet controls`. It starts from five
force/steering functions, three candidate scalar writers, three steering
update callers, the per-vehicle simulation snapshot builder, controller binding
helpers, and nested action-record helpers, then follows one level of direct calls (115 functions for the
pinned build). Reviewed leaves have explicit bounded ranges in the manifest.
Generate the compact review bundle with `python
scripts/snapshot_vehicle_control_evidence.py`; it includes the relevant
decompilations and digest manifest, without the game executable or private
process inputs.

## Nested action-record path

The expanded Ghidra slice clarifies how one nested record feeds the force
callback:

- `0x83de60` reads the record at vehicle `+0x1280`. Its signed 16-bit field at
  subrecord `+0x4e8` takes priority over the binary32 value at subrecord
  `+0xf4`; either nonzero value activates the drive conversion.
- `0x83dd90` transforms the record through `0x1955c0`, compares the result
  against subrecord `+0x84`, and writes vehicle `+0x98` as exactly `0.0` or
  `1.0`. The comparison uses the third component **after** rotation by the
  conjugated quaternion at `+0x60`, not the untransformed `+0x84` value.
  Brake clearing depends on flags at subrecord `+0x4ec` / `+0xf0`.
  These checks establish internal state transitions, not the meaning of a key,
  gamepad axis, or replay action.
- The higher-level scene update `0x7cfce0` calls `0x7d1fa0` at `0x7cfda8`.
  That routine builds a per-vehicle state block at vehicle `+0x4e8` through
  `0x7d1380`. The bounded path does not identify the raw input event source.
- The same scene update calls `0x7cfac0` at `0x7cfd4e` to select and associate
  a state-record pointer with each vehicle. It performs a binding-table lookup
  (`0x1467ca0`) and checks a record identity byte (`0x7c7c70`), then stores
  the binding mode/pointer at vehicle `+0x1c90` / `+0x1c98`. This narrows the
  dispatcher path but does not decode keyboard, button, or axis mappings.
- When that mode equals `1`, the scene copies `0x878` bytes from vehicle
  `+0x1c98` into its action record at `+0x1280` (`0x7cfe71`, overlap-safe copy
  helper `0x18d7510`). The physics updater then reads fields from that record.
  This establishes a pointer-and-copy path to the physics-facing record.
  Additional callers use the same lookup to copy other object-state records;
  this is not evidence that its source is a keyboard/gamepad controller.

The nested record aliases vehicle fields: `+0x1280 + 0x4ea = +0x176a`
(signed-short limit), and `+0x1280 + 0x4ec = +0x176c` (flags). Modeling these
as independent inputs fails the complete-procedure differential. The portable
[0.29 control guard](PHYSICS_0_29_CONTROL_GUARD.md) preserves the aliasing and
matches three original operations on 20,000 generated cases each.

The snapshot route independently pins the command offsets: `0x7d1fa0` passes
vehicle `+0x90` to `0x7d1380`; that routine copies argument `+0x10`, `+8`, and
`+0xc` to snapshot steering `+0x10`, gas `+0x14`, and brake `+0x18` on its
default path. Thus the source vehicle fields are `+0xa0`, `+0x98`, and `+0x9c`.
Special vehicle variants and steering-disable gates can override these outputs.

Holding vehicle `+0x1374` at `0.5` in the frozen 100-tick fixture changed that
stored byte in the trace, while rigid-state and force outputs remained
unchanged. The fixture does not retain vehicle `+0x1c90` / `+0x1c98`, so it
does not establish that the controller-copy branch was active. This experiment
does not validate `+0x1374` as a physical action input. Raw action-event
decoding, action thresholds, and their mapping to the nested control record
remain open.
