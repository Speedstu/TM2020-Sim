# Internal inputs and replay fidelity, 0.69

This work is incomplete. There is no new verified client arrival or verified
ordinary replay input stream from the new adapter yet. The retained client
03/06 finishes belong to 0.65b, which remains the deployed campaign runtime.

## Confirmed replay defect

`scripts/audit_replay_controls.py` decodes the original GBX bitstreams with
`tm2020-training-metadata inputs`. It compares the unchanged autosaves against
the retained physics traces using their declared clocks, with zero fitted shift.

| Map | Actual controlled ticks | Replay gas/steer active ticks | Steering-delta reversals: bot / leaderboard reference |
| --- | ---: | ---: | ---: |
| 03 | 1,892 | 0 / 0 | 173 / 49 |
| 06 | 2,600 | 0 / 0 | 135 / 80 |

Evidence: `local/recon/replay-controls-0.68/{03,06}/audit.json` and `original-inputs.json`.
The reference files are leaderboard ghosts; their human origin has not been
independently certified. These metrics do not establish human indistinguishability.
No replay has been rewritten or supplied with invented input events.

## Experimental internal recording path

`runtime.cpp` has an explicit opt-in V7 mode (`--input-recording` together with
the already authorized local writer). The regular 0.65b path stays available.

- Decoder entry: `0x12bce40`, exact 17-byte relocatable prologue.
- Sole accepted game return address: `0x12bf828`.
- Current/previous normalized player inputs: player `+0x188` / `+0x1a8`.
- Vehicle descriptor: exact class `0x0a020000` and previously qualified body/manager.
- Tick: saved caller stack slot `RSP+0x58`, or decoder entry `RSP+0x60`.
- Only the three axis values at current input `+4` are changed: steer, gas, brake.
- The original decoder still executes. The existing `0x83de60` hook checks the
  same command before cached pedal reads. A missing input tick stops actuation.
- Volatile integer/XMM inputs are preserved. The context/trampolines stay pinned.
- Map, process/build identity, heartbeat, body, reset and neutral-stop guards remain.

`audit_internal_input_entry.py` checks the pinned instructions, stack slot,
player layout and complete prologue. The initial 0.69 image is rejected because
its R14 clock assumption was not valid across every caller branch. **Use 0.69c**
for further experiments. The intermediate 0.69b is also rejected: its entry
jump destroyed incoming R11 before the callback saved it. 0.69c uses an
indirect jump with no register clobber and includes a 100-call R11 test. Its
runtime SHA256 is
`b508a1fc759000c8ce98c01ae1e9bfa0734b507f3b6d3d8ba72c45288d7bda67`.

The 0.69c owned Windows test exercised both PE detours, 100 input records and
100 physical ticks with 100 decisions, correct axis order and stop neutralization.
It also passed the existing continuous/discrete17/discrete33 policy parity tests
and the trajectory v3 asset test. Evidence:
`local/recon/internal-0.69c-owned/owned-windows-final.json`, test source and build manifest.
This is an owned process, not a claim that the client's replay recorder has
consumed the modified inputs. That requires a new client run and original GBX audit.

Observe qualifications are bound to the exact runtime hash, map, spawn, process
and input/history mode. `run_internal_trial.py --input-recording` requires actual
input-record readback, and still leaves `ordinaryReplayInputsVerified=false`.

## Why the controller also needs requalification

Normal input history activates the engine's real start adjustments. The old
campaign path left device history unchanged. A model qualified in one mode
does not establish qualification in the other. There is no velocity correction
or change to the physics library in these experiments.

On 64 predefined normal-history seeds, retained model 03 finishes 33 times and
model 06 finishes twice. Global filtering is therefore not a deployment fix.
An initial four-seed feedback search overfits: its independent 64-seed results
are 39 arrivals on 03 and one on 06. These candidates are not campaign champions.
Reevaluating the retained baseline on exactly those same validation seeds gives
41/64 on 03 and 2/64 on 06. The candidates are rejected for deployment. More
Top10 arrivals in some cases do not compensate for worse overall reliability.
All detailed cases, times and failures remain in
`local/training/input-recording-policies-0.69` and
`local/training/input-recording-feedback-0.69`.

The optional v3 controller filters feedback only. It preserves reference pedal
and steering timing and adds no random noise. Several tested filters caused
failures; none has replaced the retained policies. The phase/reference screen
is separately recorded in `local/training/input-recording-phase-0.69`.

The simulator now latches policy observation failures until reset. Previously
the batch wrapper could allow a failed tracker to reacquire later, unlike the
game controller. All 24 retained campaign nominal times remain identical with
this stricter behavior: `local/recon/campaign-latched-0.69/summary.json`.
The production campaign service now uses the frozen 0.69 wrapper/controller
from `local/training/campaign-speed-0.69/native`, with unchanged 0.58 physics.

## Actual client status and ongoing search

The user launched the client in application offline mode. Its process still
shares the host network namespace; no network-isolation proof is claimed.
The normal local-track menu displays Starter/Club Access and blocks loading
the campaign files. No access entitlement or authentication check was bypassed.
The private failed offline-launch instance was stopped; the user's original
game process was kept running.

The campaign search was stopped briefly to free RAM for validation, then resumed.
Its admission loop reserves an extra 4 GiB while Trackmania runs. There is no new
hourly AI timer. Plateau limits stop each search stage, not the whole campaign.
At this audit, 02–20 and 22–24 meet the stored nominal Top10 thresholds;
01 is the previously retained client record. **21 and 25 remain below the goal**.
19 newly finishes in 37.637 s. Simulation thresholds are not verified live ranks.

Next client acceptance test, once 03 can be loaded normally: fresh observe,
bounded V7 control, original saved replay with non-neutral recorded commands,
zero-shift agreement with the physical trace, and actual finish/respawn evidence.
Then replay the original saved inputs with normal engine history and its actual
validation seed; compare the resulting physics against the captured run.

`verify_fresh_internal_replay.py` performs the original-stream comparison and
rejects a stale PB autosave, another map, an incomplete control trace or any
input mismatch. It does not itself claim independent visual finish verification.
The launcher now records the trial's start timestamp for this freshness check.
