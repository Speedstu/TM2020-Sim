# Counterfactual original-step replay 0.28

The offline engine and the owned native runner can now replay a bounded 100-tick
counterfactual with three **internal vehicle-record scalars** held before every
10 ms original-game step. This tests branch-level consequences of the decoded
record fields; these values are not a recovered keyboard/gamepad action API.

For `owned_throttle_straight.tmstep`, the captured override was drive `0.5`,
brake `0.0`, steering `0.15`. The emulator regenerated the typed trace and
final owned pages from the pinned executable. The native runner then applied
the same schedule while calling the original `0x7bd0e0` procedure and matched
all 100 frames bit-for-bit across rigid state, vehicle state, and force output.
Compared with the source trace, 18 typed vehicle-record bytes changed on each
sampled frame (including frames 1, 2, 3, 11, 21, 51, and 100). A subsequent
per-record audit found **zero changed rigid-state bytes and zero changed force
accumulator bytes**. Thus the earlier statement that this demonstrated a
responsive trajectory was incorrect: it demonstrates internal-record changes
and emulator/native agreement, without proving physical action response.

The native fixture format is version 4 for scheduled controls; version 3
baseline fixtures remain readable. Version 5 also accepts a per-tick sequence
of `[drive, brake, steering]` scalars. A test that held `[0.5, 0, 0]` for 50
steps and then changed steering to `0.15` for 50 steps matched all 100 emulator
frames in the native runner; the output trace changed at the action boundary
between ticks 50 and 51. The varying case likewise changed only the vehicle
record (2 bytes before the boundary, 18 after), while the rigid trajectory and
retained force accumulator matched baseline throughout. Both modes are bounded to the captured
memory pages, pinned game/OS module cohort, and captured 100-tick horizon.
This is an original-code executable oracle, not a reconstructed complete
physics simulator. It does not cover arbitrary track states, the public input
path, general action sequences, suspension/tire parameter identification, or
RL policy validation. The produced `.tmstep` and native input contain private
captured process state and stay under `local/recon/`.

Reproduce the emulator capture with:

```powershell
python scripts/replay_original_step.py `
  --exe 'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe' `
  --fixtures local/recon/main-step-fixtures-v5/owned_throttle_straight.tmstep `
  --report local/recon/counterfactual-control-050-000-015.json `
  --scenario-controls 0.5 0 0.15 `
  --scenario-output-dir local/recon/main-step-control-scenarios/drive050-brake000-steer015
```

Compile the resulting fixture with `scripts/compile_original_step_fixture.py`,
then run `native/build/tm2020_original_step_native.exe` on the generated
`.tmstepnative` file and the pinned executable. The native report must show
`allTypedPhysicalFramesBitExact: true` and `completeMainProcedureReturnedEveryFrame: true`.
For a varying sequence, pass `--scenario-control-schedule schedule.json`, where
the JSON array contains one `[drive, brake, steering]` triple per captured tick.

The later [0.29 result](PHYSICS_0_29_CONTROL_GUARD.md) adds
`--scenario-steering-command` and native format 6 to apply steering at `+0xa0`.
That trial does produce a small rigid trajectory response from tick 51 while
matching all 100 native/emulator frames. It remains a frozen bounded scenario.
