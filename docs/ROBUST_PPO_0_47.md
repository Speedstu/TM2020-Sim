# Robust PPO continuation

This runner continues single-map learning from retained checkpoints. It neither
launches Trackmania nor touches the hourly monitor. Simulation results do not
replace the real-game validation of the older deployment candidate.

## Objective and selection

`scripts/robust_ppo.py` reuses the matched experiment's continuous steering,
binary pedals, CUDA float64 PPO and unchanged native CPU physics. Reward remains
the simple minimum-time reward v3: finish `100 - seconds`, failure `-140` over
the 40-second horizon, scaled by .01. There is no expert route, progress bonus
or best-lap reward that could reward failure.

Model selection forbids regression in nominal arrival count, then maximizes
total arrivals on a fixed development suite. Among equal completion counts, it minimizes penalized mean time plus
15% of the penalized 90th percentile. DNFs count as 40 seconds in both metrics.
The mean of nominal arrivals has a fixed regression ceiling relative to
the starting checkpoint (`--nominal-slack-ms`, default 100 ms). A 250 ms ceiling
is also tested to prioritize a higher arrival rate over a small nominal slowdown.
A gain under 25 ms in that combined score does not
reset plateau patience. The fastest isolated finish never selects a model.

The current 128-case development suite consists of 16 nominal departures with
different physics seeds, 56 early steering disturbances and 56 smaller midrace
disturbances. At 256 cases those counts become 32/112/112. Perturbation
seeds differ from training and from the final evaluation. During training,
40% of episodes receive a short steering disturbance, half early and half
midrace; the remaining 60% run normally. This trains recovery without requiring
artificially corrected actions at inference.

Candidate learning rates are measured from the same checkpoint, seed,
disturbances, budget and evaluation cases. `conservative` uses actor/logstd LR
1e-6; `balanced` uses 3e-6; `precision` uses 3e-7. All use critic LR 3e-5. No name establishes
optimality: inspect the pilot reports before selecting one. The starting
checkpoint is always retained if the pilots fail to beat it.

## Checkpoints and stopping

`best.pt`, `best.tmppo` and `best-score.json` identify the selected model.
`last.pt` atomically saves model, optimizer, CPU/CUDA RNG and completed update
number after every update, including updates without an evaluation. `status.json`
reports both compute SPS and wall SPS including evaluation/save overhead.

The output directory is locked against concurrent writers. Resume requires an
identical protocol (source hashes, native physics, profile, seeds and geometry).
Simulator episodes restart from the next saved episode seed counters; this is
not an exact restore of in-flight physical worlds. The maximum update budget
can be increased without changing the protocol. Existing plateau patience is
honored on resume; a plateau is not automatically reset to restart training.

Create `STOP` in the output directory or send SIGTERM to stop at the next update
boundary. A STOP before the first update saves update zero, never a fictitious
update one. The old continuation script remains historical; use this runner's
tested lifecycle for the new profile.

At the budget or plateau limit, the selected model is evaluated once on a
separate final suite, saved in `holdout.json`. Development pilots use
`--skip-final-holdout`; their outcomes are used for profile selection, not
presented as final held-out results. No finite suite proves zero errors.

## Checks and execution

### Run started on 30 October 2026

This run is now historical and stopped. See `TIME_CREDIT_0_48.md` for the new
main run and its tested decisions. The original code was saved under
`backups/time-credit-20261030-215257/` before the protocol changed.

`tm2020-robust-ppo.service` ran `local/training/robust-main-20261030/` with
profile `precision`: actor/logstd LR 3e-7, critic LR 3e-5, 32 environments,
512 decisions per rollout, eight CPU workers and CUDA float64 optimization.
It evaluates 256 development cases every four updates, stops after 16 such
evaluations without improvement, and has an absolute budget of 2,048 updates.
There is no automatic service restart or hourly monitor.

The source is a frozen copy of the precision pilot's update-32 checkpoint,
with a fresh optimizer and training seed 85601. Pilot training used the same
524,288-transition budget and seed 85101 for all three learning rates. On the
expanded development suite, selected after those pilots:

| Checkpoint | Arrivals | Nominal arrivals | Finish mean | Penalized mean |
|---|---:|---:|---:|---:|
| Previous best-tuned source | 253/256 | 31/32 | 24.087 s | 24.273 s |
| Precision pilot, update 32 | 254/256 | 31/32 | 24.125 s | 24.249 s |
| Conservative pilot, update 32 | 250/256 | 32/32 | 24.194 s | 24.564 s |
| Balanced pilot, update 32 | 251/256 | 32/32 | 24.135 s | 24.445 s |

These are development results and a small difference; they do not establish
general superiority. The starting model still fails two cases, including one
nominal seed. The selection protects nominal finish count; it does not claim
that all nominal seeds already finish. The absolute nominal mean ceiling is
24,177.4516 ms, 250 ms above the previous best-tuned source. Relative to the
selected source this leaves 74.1290 ms of allowed nominal-mean regression.
The untouched final suite uses seed 87400; development uses seed 85200.

`selection.json` contains exact provenance and hashes. `protocol.json` also
pins runner/update/history code, map, native libraries and parameters. The
previous real-game validated export is retained unchanged in
`local/recon/deployment-0.46/candidate.tmppo`. New models require a fresh real
client qualification before any claim of a real-game improvement.

```sh
systemctl --user status tm2020-robust-ppo.service
journalctl --user -u tm2020-robust-ppo.service -n 15 --no-pager
cat local/training/robust-main-20261030/status.json
```

For graceful stopping, create `local/training/robust-main-20261030/STOP` or stop
the service. The old hourly timer remains disabled. The service definition is
retained in `config/systemd/tm2020-robust-ppo.service`; it is not enabled at boot.

### Checks and reproduction

The initial three pilots used an earlier suite with one nominal departure,
63 early disturbances and 64 midrace disturbances. Their logs are retained,
including a 128/128 development result that fell to 121/128 on a second suite
versus 125/128 for its source. That candidate was rejected. Protocol version 2
adds multiple nominal seeds and retains separate final cases; it must not be
compared as though it used the exact same cases as those first pilots.

```sh
tools/venv-gpu/bin/python scripts/test_robust_ppo.py
tools/venv-gpu/bin/python scripts/test_cuda_history.py
```

The first test covers failure-first selection, nominal guard, disturbance
schedule, empty budgets, immediate STOP, and resumed completed-update counts.
Its lifecycle tests use owned doubles, without simulator or GPU work. The
second checks real native simulator/CUDA history parity at 75 steps × 16 worlds.

Example bounded run in a fresh directory:

```sh
TM2020_PHYSICS_WORKERS=8 tools/venv-gpu/bin/python scripts/robust_ppo.py \
  --source local/training/best-tuned-20261030/best.pt \
  --output local/training/my-robust-run --profile balanced \
  --max-updates 512 --eval-every 8 --patience 10 --nominal-slack-ms 250
```

Default collection is 32 environments × 512 decisions = 16,384 transitions per
update. Physics runs on eight CPU workers in the example; policy/history and
optimization run on CUDA. No timer or automatic restart is installed. Any later
client qualification must check the selected export's hash and actual arrival,
separately from these simulator metrics.
