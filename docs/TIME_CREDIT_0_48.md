# Time objective, speed-loss audit and PPO credit

The user observed speed lost through impacts and requested faster, clean driving.
The prior 0.47 run was stopped gracefully after freezing its best model in
`local/training/time-credit-20261030/source.pt`. The selected checkpoint was
update 120: 256/256 development arrivals, 23.959 s mean, but a 30.507 s slowest
nominal race. Completing the map is not enough to establish a clean fast line.

## Reward audit

The native reward is already finite minimum time, gamma 1:

- Successful complete return: `100 - finish_seconds`.
- Failure, timeout or a retired/stuck car: `-140` over the 40-second horizon,
  including the compensating cost of the remaining horizon on an early failure.
- Training uses a .01 scale. Earlier finish gains exactly the saved time;
  failing early or waiting cannot avoid the complete failure cost.

`scripts/audit_time_credit.py` runs actual native physics, accumulates rewards
only while the episode is active, and checks these identities at termination.
On 32 nominal physics seeds, idle and straight-only control each finish 0/32
and return -140. The frozen policy finishes 32/32 with mean return 75.8598125.

That policy also has 40 abrupt losses exceeding 4 m/s within 50 ms without a
commanded brake. One seed drops from 86.80 to 25.75 m/s near 23 seconds. These
are kinematic impact candidates, not verified collision events: landings,
surface transitions and other causes must not silently become wall penalties.
The diagnostic does not add penalties or alter native physics.

An enormous penalty against the previous model is not used. It would change the
training target at each model update and strengthen failure avoidance without
providing a trajectory or better observations. The previous model instead
serves as a protected checkpoint and evaluation reference. A slower or less
reliable candidate must earn promotion through measured comparisons.

## Credit ablation

Historical PPO uses gamma 1 and GAE lambda .995. The coefficient carrying a
terminal advantage 479 decisions back within a rollout is `.995**479`, about .091. This is an
estimator property, not a proof that the reward is incorrect. Lambda 1 carries
that terminal signal fully but can have higher variance; it must be tested.

The optional intermediate shaping uses only the existing observable local
checkpoint-goal vector:

`phi(s) = -2 * norm(observation[6:9])`

At every step, add `.01 * (phi(next) - phi(current))`, with next potential forced
to zero on every terminal transition, including auto-reset. Thus over a complete
episode `sum(shaped) + .01*phi(initial) = sum(raw)`. Standing still, reversing,
looping, and early failure cannot earn an extra complete-episode return.
There is no expert line, future replay command, or hidden checkpoint ordinal in
this potential. The simulator, action contract and deployment observations stay
unchanged. No reward-shaping component is needed inside the game.

Three development pilots start from identical frozen weights and use training
seed 85701, 32 environments × 512 steps, actor LR 3e-7, critic LR 3e-5,
24 updates (393,216 transitions) and the same 256 development cases:

| Pilot | GAE lambda | Shaping |
|---|---:|---|
| control | .995 | none |
| full | 1 | none |
| full-potential | 1 | observable potential |

No pilot runs final holdout selection. Seeds, native/map/code hashes and full
parameters are recorded per output directory. Keep the incumbent when a pilot
does not improve; do not assume longer credit or shaping is better.

A fourth pilot keeps the control reward/credit and replays 25% of its own slow
training cases. Only successful training episodes taking at least 26 seconds
enter a bounded 128-case seed/disturbance bank. Fast repeats graduate out;
failed repeats stay difficult. Every repeat resets the complete world and all
observation history. The bank is saved with the optimizer checkpoint, and it
has no interface to evaluation case lists or expert replays.

All four pilots ran 24 updates, 393,216 transitions per arm, at the same seed and
budget. None produced a checkpoint that improved on the frozen incumbent under
the safety/time/tail gates. Consequently **none of these optional changes is
enabled in the new main run**. This is evidence for this short experiment,
not a claim that these methods can never help. Reducing latent steering noise
from .02513 to .0125 also did not help a small paired 32-race audit (30/32 vs
29/32 stochastic arrivals); exploration noise is retained.

## Current continuation and final qualification

`tm2020-time-ppo.service` runs `local/training/time-main-20261030/`: continuous
PPO, actor/logstd LR 3e-7, critic LR 3e-5, gamma 1, lambda .995, no shaping,
no slow-case replay, 32 environments × 512 steps, eight native CPU workers and
CUDA optimization/history. Source: frozen best update 120 of the prior run.
Training seed 86001 differs from all development pilots. The nominal mean
ceiling remains 24,177.4516 ms across continuations; the new run's slack is
37.2641 ms above its source, rather than accumulating allowed regressions.

It evaluates 256 development cases every four updates, stops at 24 evaluations
without improvement, and has a maximum budget of 1,024 updates. It never
automatically restarts. The old main service and hourly timer remain stopped.

After budget or plateau, compare the selected model and frozen source on the
same separate 256-case suite (seed 87500). `trial-qualification.json` permits a
new game trial only with no total/nominal finish-count regression, at least
25 ms improvement in penalized mean and at most 25 ms worse mean among the
slowest 10%. Otherwise retain the source as the reference. No automatic game
deployment occurs. Further training after final cases have been consumed
requires a new output and fresh final seed.

```sh
systemctl --user status tm2020-time-ppo.service
cat local/training/time-main-20261030/status.json
journalctl --user -u tm2020-time-ppo.service -n 10 --no-pager
```

`STOP` in that output directory or SIGTERM requests a checkpointed stop.
`local/training/current.json` points to the current run; `comparison.json` in
the experiment directory records the four rejected ablations. A separate
zero-update smoke run exercises final candidate/reference qualification on
different seeds, without consuming the production final suite.

## Tail selection and tests

Protocol version 3 retains nominal finish-count protection, total arrivals
first, and a fixed nominal mean ceiling. Among equal completion counts, it
uses penalized mean plus .15 times the **mean of the worst 10%** of trials,
rather than only the 90th percentile. DNFs count as 40 seconds. This makes very
slow recovery races visible even when they are above the 90th percentile.
This tail term selects checkpoints; it is not an invented contact reward.

`scripts/ppo_time_credit.py` implements configurable GAE and shaping helpers.
`scripts/test_time_credit.py` checks shaping telescoping, loop/failure ordering,
full-return terminal boundaries, and a bit-identical CUDA optimizer update
against the historical implementation at lambda .995. `test_robust_ppo.py`
still checks safe stopping, resumed completed-update counts and selection.
All eight native minimum-time Rust reward tests also pass.

```sh
tools/venv-gpu/bin/python scripts/test_time_credit.py
tools/venv-gpu/bin/python scripts/test_robust_ppo.py
```

Evidence is under `local/training/time-credit-20261030/`, including
`audit-v3/report.json`, pilot protocols, evaluations and source provenance.
The older runtime/DLL, real-game validated candidate, Steam prefix, and hourly
timer are unchanged. These experiments still concern one map; generalization
requires training and testing on disjoint whole maps, not merely new seeds.
