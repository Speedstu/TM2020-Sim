# Fall campaign: measured simulator search, 31 October 2026

Objective: Fall 01 strictly below the first-place reference (19.988 s at the
recorded board fetch), maps 02–25 at or below their recorded tenth-place time.
A simulator time is a comparison with a public time threshold, not an online
rank. The user handles client trials; later the user explicitly requested the
Fall 01 internal candidate for manual repeated attempts.

## Artifacts and current work

`local/training/fall-campaign-0.52/campaign.json` identifies all 25 map files,
UIDs, content hashes, source URLs and time thresholds. Each numbered directory
contains a sanitized leaderboard snapshot, a public reference ghost, the exact
reproduction metadata, controller assets, search history and independent
`nominal64.json` / `perturbed64.json` evaluations when completed.

All 25 references reproduce exactly in the native recovered physics engine.
This is only an engine/reference test: it does not qualify the controller.
23 references use braking and 18 release the accelerator. The generic tracker
therefore follows reference pedals instead of assuming permanent full throttle.
The vector API accepts a per-map horizon; the longest reference is 68.822 s.

The controller uses reference geometry and commands with physical feedback.
This is explicit map-specific assisted tracking, not a single generalist PPO.
The search adjusts 16 smooth lateral targets, 16 steering corrections, four
feedback gains and phase alignment. Fitness first rewards arrivals, then lower
measured finish times. The target time is only a stopping/comparison threshold,
not a plateau in the reward. Four common development seeds compare candidates;
64 unseen nominal and 64 perturbed seeds are reported separately. Perturbations
are short steering disturbances during the run; do not describe them as arbitrary
spawn transformations. Failures are retained in all reports.

## Fall 01 candidate

`01/best.tmhyb` has SHA256
`f9a176d7f16279d4d43ecce16f66d30d74ded0269e0557385e58366a2bb84c05`.
Development: 4/4 arrivals below 19.988 s. Independent nominal evaluation: 56/64
arrivals, 36 below 19.988 s, best/median 19.987 s. Perturbed evaluation: 41/64
arrivals, 21 below 19.988 s. This is faster but less reliable than the retained
0.51 fixed candidate. The strict all-seed goal remains false. Keep both assets.

Actual-client trial `local/recon/campaign-fall01-user/attempt-001` used this
candidate and deployment 0.52: 6,422 exact command readbacks, no unexpected
controller faults, normal neutral shutdown. A new faster client finish has not
been independently established. The previous 19.988 s client result remains
the retained assisted client benchmark.

## Local manual attempts

The 0.53 repeat worker only rearms at a newly started race, at the qualified
spawn, with the same physical manager/body, valid state, expected map and a
healthy heartbeat. It clears its cursor and held commands on each qualified
restart. During countdown and after the trajectory budget it applies neutral.
A reference budget expiring is never reported as an arrival. No peripheral
input drives the car. Escape, STOP, map change or a failed worker ends the
session; the supervisor only renews normal bounded 120-second workers.

`repeat_internal_local.py` leaves resets to the user. The separate trial helper
uses Delete only to reset a test; neither helper drives through keyboard input.
Owned fixture results are under `local/recon/internal-0.52-owned/` and the new
repeat fixture directory when its tests have passed. The repeat deployment is
staged with immutable content-hash filenames, preserving older loaded images.

The old PPO services and hourly timer remain disabled. The campaign optimizer
is a finite local process, stopped on its development target, budget or plateau.
Do not reactivate the old monitor to continue this work.

## Commands

```sh
# Fetch public maps/references (read-only, respects rate-limit backoff).
python scripts/prepare_fall_campaign.py

# Finite full-campaign search; skips completed result files.
tools/venv-gpu/bin/python scripts/optimize_fall_campaign.py --generations 64 --plateau 24

# Print a map-specific client test command, without touching the game.
tools/venv-gpu/bin/python scripts/play_fall_candidate.py 1
```

The live Solo client may publish a personal best automatically while connected.
An injected run's ordinary replay can contain neutral recorded inputs. Never
present the replay header alone as proof that those recorded inputs reproduce
the injected run, or claim a clean official ranking from a simulated result.

## Internal actuation correction and parallel searches (0.54–0.56)

The older simulator passed changing commands into device input history. The
physical-consumer DLL leaves that history neutral. The engine can apply
seed-dependent start adjustments after input changes at 5/10/15 seconds. The
new explicit optional control-mode ABI freezes device history while applying
physical commands. Legacy behavior stays the default for frozen experiments.
`test_internal_control_mode.py` verifies one adjustment on the legacy trace,
zero in internal mode, rejection of midrace mode changes, and mode retention
across resets. No engine perturbation code or actual-client physics is patched.

Recorded real commands replayed without state correction are closer to the
client trace with this mode, but still diverge: the model is **not physically
exact**. At 1 s the position discrepancy is about 1 cm; wall contact later
amplifies it. The full report is `local/recon/internal-actuation-0.54.json`.
This audit is neither a policy evaluation nor a verified client finish.

The corrected-mode Fall 01 candidate in
`local/training/fall-campaign-internal-0.54/01/` achieves 19.987 s in nominal
simulation. 64 nominal seeds represent **one distinct physical condition**
because the device history no longer generates seed-dependent input changes.
The meaningful separate disturbance suite has 50/64 arrivals, including 31
below 19.988 s. These are assisted simulator results requiring game validation.
The source trajectory is the saved actual-client 19.988 s physical trace,
not the ordinary replay's neutral inputs.

Two finite searches now run independently: `tm2020-fall01-sim.service` targets
19.986 s or faster under `local/training/fall01-record-0.56/`; the other,
`tm2020-fall-campaign-sim.service`, processes 02–25 under
`local/training/fall-campaign-internal-0.55/`. Official millisecond finish times
remain the main objective; continuous terminal forward phase only breaks ties
between equal-time finishes. That proxy is never published as a lap time.
Each search has its own lock and result file, immutable native libraries,
source snapshot and plateau/budget stop. The old hourly monitor stays disabled.

The 0.53b owned repeat fixture passes two identical command sequences separated
by a verified reset and a neutral countdown. The actual client then logs three
consecutive manual attempts under one worker and another two under its renewal.
Escape/menu subsequently ended the session; it has not been silently restarted.
The manual-only unit is installed without login autostart. For the still-running
qualified client, the user can restart it with:

```sh
systemctl --user start tm2020-fall01-play.service
```

Then Delete starts an attempt, Escape ends the session. A new client process
requires fresh physical qualification; the launcher refuses stale process data.
The live model was kept unchanged when the user requested keeping the current
behavior; new simulator models are not silently substituted into the client.

## Top 1 goal on every remaining map (0.57)

The user changed the objective: Top 10 is now a milestone, not a completion
condition. `tm2020-campaign-world-records.service` replaces the old finite
campaign service and runs two native simulator searches in parallel. Maps 02
and 03 resume from their retained Top-10 models and pursue a time strictly
below first place. Other maps likewise continue after crossing Top 10.
The client candidate and runtime are untouched.

`local/training/fall-campaign-world-records-0.57/` contains refreshed sanitized
leaderboard snapshots, separate reproduction/reference metadata, immutable
incumbent assets, per-stage results and per-map `pursuit.json`. The reference
replay's declared time is never substituted for the fresh board's target.
`targetMs = first_place_ms - 1`; an equal-time finish does not complete Top 1.
Older Top-10 result flags cannot satisfy the new target. These comparisons
establish simulator time goals, not actual online ranks.

Each map's bounded stage stops at a plateau, keeps its incumbent, and a later
stage changes candidate RNG, trajectory basis width and exploration spread.
Common development departures remain fixed for comparison. Stage selection
uses the nominal development time, then development reliability; the separate
perturbation suite is reported rather than used to select between stages.
Fair passes let other maps progress before retries. The scheduler continues
changed stages until the time goals or an explicit stop; no hourly timer or
LLM monitor is involved. An abnormal stage exit stops the scheduler rather than
silently restarting the same failed stage.

`test_campaign_targets.py` includes a two-generation search regression: the
first generation reaches Top 10, the next reaches strictly below first place;
the search must continue to the second generation. Other tests reject an
old Top-10 cache as Top 1, reject a WR tie, and validate map/board identity.

## Native throughput optimization (0.58)

The same search resumes from its saved 0.57 stages with optional
`--fast-evaluation`. The frozen Rust physics library is unchanged (SHA256
`607f1b5ec71cc26a1ded307b955c410567aa1408ccb41ccd4546b3e531f2118d`).
The C++ wrapper assigns an entire independent race to one persistent worker,
using a shared work queue for load balancing. This removes the policy/physics
barriers at every macro tick. The old evaluator remains available for matched
comparisons. Both retain 100 Hz control, the same cases, full observations,
reward, finish logic, perturbations and all physics steps.

The asset checksum now has an optional native FNV64 implementation with the
same binary format, validation and Python fallback. New libraries are frozen
under a content-hash directory; mapped DLL/library files are never overwritten.
The actual-client runtime/model is untouched by this performance change.

Matched tests use 64 cases with multiple assets, early/midrace disturbances,
one warmup and three paired timed repeats, reversing evaluation order. Entire
output state bytes, including observations, rewards, controls and rigid state,
must match. Results under `local/recon/hybrid-speed-0.58/`:

| Map | Original median | Optimized median | Speedup | Optimized macro steps/s |
|---|---:|---:|---:|---:|
| 02 | 2.748 s | 1.890 s | 1.45x | 73,067 |
| 03 | 3.569 s | 2.522 s | 1.42x | 53,322 |

These are rates for each matched evaluation batch, not GPU PPO training SPS.
Map 02 was measured with other searches running; map 03 with the campaign
briefly stopped for its upgrade. Each paired baseline/optimized comparison
used the same concurrent load. Checksum time fell from 30–37 ms to about
0.4 ms for the measured asset sizes. The production generation status now
reports preparation time, native evaluation time and total generation rate.
The coordinator resumed two maps with verified fast-mode protocols and
preserved the Top-1 objective and plateau rules.

A 30.006-second production window counted 3,280,198 completed simulated macro
steps across both active searches: **109,318 steps/s combined**. This counts
completed generation batches and is not a per-search or GPU learner rate.
Evidence: `local/recon/hybrid-speed-0.58/production-throughput.json`.

## Overnight execution and memory-aware concurrency (0.59)

The installed user service permits up to four simultaneous map stages with
four native physics workers each, admitting each new stage only when available
RAM covers a 4 GiB reservation plus a 6 GiB host reserve and unallocated memory
reserved by other starting stages. Three active maps were verified after the
upgrade; the fourth waits for memory when necessary. Twenty-four independent
map worlds would exceed this machine's 31 GiB RAM with the current architecture.
All maps remain queued in fair passes, including changed retries after plateau.

`systemd-inhibit --what=idle:sleep` is held for the service lifetime and was
verified in logind's inhibitor list. The service survives this conversation,
uses the lingering user manager, and restarts after abnormal coordinator exits
with a delay and bounded restart frequency. Stage progress has a 15-minute
watchdog. A failed map is retained for inspection while other maps continue.
An interrupted stage checkpoint can initialize a changed next stage without
being mislabeled as a qualified result. Tests cover memory admission and this
checkpoint recovery, plus the existing goal/qualification regressions.

The service has MemoryHigh=14G, MemoryMax=18G and MemorySwapMax=2G limits.
The computer still needs power and a running OS; inhibitor protection does not
promise survival of shutdown, power loss or forced suspend. Nothing enables the
old hourly monitor, writes leaderboard scores or starts actual-client trials.
Current overnight verification is recorded in `overnight-verified.json`.

## Prepared campaign client tests (0.60)

The user explicitly requested the models that already met the Top-10 simulator
threshold. `local/recon/campaign-play-0.60/bundle/manifest.json` freezes models
for 02, 03, 06, 08, 09, 12, 13, 15 and 17. It records the exact model/map hashes,
original spawn, nominal threshold result and independent disturbance results.
The bundle does not change while the user tests it; new search candidates are
not hot-swapped silently. These remain simulator qualifications, not game ranks.

`tm2020-campaign-play.service` replaces the single-map play service and uses a
separate read-only helper for the game's official `ManiaPlanet_Telemetry`
shared memory. The helper never opens game process memory; its self-test checks
header, state and UID rejection. A stable prepared UID selects the model.
Unsupported maps and menus receive no controller. Fresh observation qualifies
the physical manager/vehicle/body and spawn for every map load. A single Delete
menu reset starts this observation; driving commands always come from the
existing 0.53b DLL. The client build/owner guards, neutral stop and detach checks
remain in place. The game process is rechecked against its start timestamp.

After qualification, Delete starts each attempt. Escape stops the current
controller. Selecting a different prepared map starts a new observation and
selects its own model. Returning to the same map after an Escape-only stop
requires a map change or explicit session restart. A map switch waits for the
old controller to detach before activating another. An abnormal worker exit
stops the selector, rather than layering hooks. The repeat launcher now passes
the actual map file instead of the old Fall 01 default.

Client session status: `local/recon/campaign-play-0.60/session/status.json`.
To stop the full selector, stop `tm2020-campaign-play.service` or create its
session `STOP` file. Neither selector nor helper has login autostart. The
campaign search service continues independently, including its sleep inhibitor.
Three tests cover frozen bundle integrity, incomplete/slow result rejection,
and stale/different process/map/spawn qualification rejection. This selector
is for the user's explicitly authorized local Solo tests; it does not prove a
new client arrival and does not attempt to alter score submission behavior.

## Map-switch observation order fix (0.61)

The first 02→03 switch failed safely: the observer bound a spawn instance,
then the automatic Delete reset retired that instance. The trace retained only
42 bound ticks and another 105 unbound ticks, so the existing qualification
checks refused activation. The selector now sends its one reset **before**
installing the observer. It still requires a full fresh physical qualification.
An otherwise normal detached observation with insufficient ticks is retried at
most three times per map; it no longer kills the selector for other maps.
Other-map/process/hash failures or abnormal detachment remain fatal. No owner,
map, clock, or command validity guard was loosened.

Regression tests assert the reset precedes observer creation and an unstable
but normally detached trace is retryable. All five campaign client gate tests
pass. Actual Fall 03 observation then qualified its exact manager/vehicle/body
and the correct immutable 03 model was installed; this verifies activation,
not a new finish. Evidence: `local/recon/campaign-play-0.60/map03-transition-fix.json`.

## Actual-client Fall 03 failure and handoff to 06 (0.62)

The 03 model did not finish in the actual client: two repeat trials hit the
same wall at about 12.960 s. Native controller replay on captured rigid states
matches the written commands. The autonomous simulator finishes at 18.915 s,
but closed-loop trajectories diverge before the collision. Replaying the
actual commands with frozen device history shows the first velocity mismatch
at 20 ms: vx=-0.119960621 in the game versus -0.129960611 in the simulator,
about 0.01 m/s. Position and rotation still match at that instant. The cause
of that mismatch is not established; it is not evidence of a bad map file.

A broad feedback grid, a local feedforward margin, global saturation priority,
and brake-initiated drift saturation were explored. The tested live variants
still fail to finish. None is promoted into the user's live bundle. Version 2
hybrid assets opt into the experimental drift saturation behavior in isolated
0.62/0.62b DLL builds; existing version-1 assets keep their original law.
Native drift tests and owned DLL parity/reset tests pass, but those tests do
not establish a successful actual-client race. Detailed failed traces and
comparisons remain in `local/recon/map03-wall-0.62/`; its status explicitly
records unresolved simulator/client divergence.

At the user's request, map 03 was removed from the prepared live manifest,
while original model 06 (e955240496e98322b1e8...) uses unchanged deployment
0.53b. The selector freshly qualified the actual 06 spawn, loaded the correct
map/model hashes, and recorded manual episodes. No further actual 03 test is
started while the user tests 06. The other simulator searches continue.


## 0.65b: 03/06 actual transfer fix supersedes the 0.62 diagnosis

The old late wheel hook missed Sport's cached pedal reads. Controls now enter
before those reads through a register-preserving wrapper. Actual 03 finished
in 18.915 s; actual 06 finished in 25.997 s, both with zero respawns and exact
position/velocity correspondence at compared simulator ticks, without launch
compensation. The first early-hook build crashed on 06 and is rejected; use
deployment-0.65b. Full evidence and limits: [INTERNAL_PEDAL_ORDER_0_65.md](INTERNAL_PEDAL_ORDER_0_65.md).

The live campaign selector uses 0.65b. Other prepared maps await user tests;
no whole-campaign actual pass is claimed. Campaign optimization was paused
during debugging and has now resumed without a time limit; see
[OVERNIGHT_CAMPAIGN_0_66.md](OVERNIGHT_CAMPAIGN_0_66.md).
The old hourly monitor remains disabled.
