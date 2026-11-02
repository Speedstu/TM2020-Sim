# Hardcode human-input qualification 0.74

The active controller is the retained deterministic trajectory tracker with
physical feedback, normal 100 Hz inputs, binary pedals and signed i8/127 steer.
The BC/v8 experiments are not the campaign controller.

## Verified local result: Fall 01

Frozen leaderboard thresholds: Top 100 = 20,032 ms; Top 10 = 20,006 ms.

| Matched test | Finishes | Top 10 | Human metric P10–P90 passes | Median | Best |
|---|---:|---:|---:|---:|---:|
| Normal 64 | 64 | 64 | 64 | 19,995 ms | 19,994 ms |
| Perturbed 64 | 64 | 64 | 64 | 19,995 ms | 19,994 ms |

Each run is compared with the decoded Top-100 cohort, not just an aggregate.
Four paired full-race traces show 174–323 changed controller ticks after a short
physical steering disturbance. The executed commands are not identical to the
Top-1 input stream (53–60% exact all-channel ticks). Feedforward and spatial
targets remain human-derived priors: this is map-specific, reference-assisted
feedback control, not a proven generalist agent.

All traced commands are legal binary/i8 normal inputs; the simulator's normal
input acknowledgement matches every command at the corresponding tick. This
does not prove client recording or visual indistinguishability from a human.
No client replay or deployment is certified.

Candidate and hashes:
`local/training/hardcode-human-0.74/sim-candidates/01/MANIFEST.json`.
Complete benchmark, source cohort and traces are in that directory.

## Measurement repairs

`compare_human_sim_inputs.py` now actually reads each duration metric's own
observed extrema. Previously it accidentally reused the last scalar metric's
extrema. Run-level metric summaries now use medians as advertised.

An input held for the whole lap is right-censored at the finish: full-gas or
no-brake lap duration is excluded from hold-duration comparisons only when both
the bot and human cohort have the same constant duty and zero transitions.
Otherwise press/release duration ranges remain checked. This prevents penalizing
a faster full-gas finish merely for shortening the recorded gas hold.

## Active optimization

`run_hardcode_human_campaign.py` screens 16 starts on each selected map. A map
without any finish is sent to parity diagnosis rather than a long zero-finish
training. Feasible maps use the existing `train_hardcode_recorded_inputs.py`,
with bounded stages and plateau stops, then an immutable checkpoint is audited.
The Top-10 stage requires all 64 normal and 64 perturbed runs to meet Top 100
and pass the common human P10–P90 metrics first. This is one campaign pass, with
no hourly monitor and no automatic champion replacement.

In addition to controls/gains, route search tests smooth lateral spatial target
changes with corresponding target velocities. Actual simulator states are never
written: every evaluation starts from the map reset and evolves through physics.
Route/input changes are evaluated with matched incumbent feedback gains. The
failure focus precedes the lower quartile of the last localized failure progress
by 80 ticks, rather than editing only after the failed section.

Logs and current map: `local/training/hardcode-human-0.74/campaign-status.json`.
The separate record search, champions and client are untouched.

## Checks

13 hardcode training regressions, 3 human-comparison regressions, Python syntax,
and the frozen native internal tick, input-statistics and trajectory tests pass.
New path-target mutation checks include bounded smooth offsets, unchanged start
and finish targets, unchanged controls and unchanged target orientation matrices.
