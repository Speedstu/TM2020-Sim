# Fall 2026-01: pursuing the top-ten time

The target has **not** been achieved. The best verified actual-client time
remains **23.366 s**, twice, with the retained 0.46 policy and runtime.
The world personal-best leaderboard's tenth time was **20.006 s** and first
time **19.988 s** at 2026-10-30 22:23:25 UTC. Fetching this leaderboard and
downloading public ghosts are read-only operations; no scores are submitted.
The map UID is `ypPmohQofd72MyTsIsijKfrJH98`.

## Running continuation

`tm2020-top10-main.service` trains continuous PPO on CUDA using native CPU
physics, from the preserved reliable checkpoint. Run directory:
`local/training/top10-20261030/ppo20/`. This is the current training run,
not the stopped `tm2020-time-ppo.service` or the experimental 100 Hz branch.

The selected source SHA256 is
`a1b6803ff21a1b895d6f19c8d3c07bcc6411df723604ffe71cb15fad13e42dd3`.
Actor and critic have 240 inputs, 512 tanh units and separate output heads.
Gas/brake are binary; steering is continuous and quantized to signed i8.
Five observation frames span 200 ms; decisions are every 50 ms. Game driving
remains internal, synchronized to the physical consumer; there is no driving
through a virtual controller or SendInput. Contact/turbo channels stay masked.

The reward remains pure minimum time: a completed race returns
`100 - finish_seconds`, failure returns `-140` over the 40 s horizon, with
the remaining-time cost compensated on an early failure. Training scales it
by .01, gamma is 1 and GAE lambda .995. There is no target-time plateau in
the reward: every millisecond gained improves the successful return.

32 worlds × 1024 decisions per update, eight native physics workers, actor
LR 3e-7 and critic LR 3e-5 initially. 80% of training resets use complete
physics snapshots from the last five seconds of the public WR run; the
remaining resets start at tick zero. A snapshot restores the complete world,
not only position/speed. Four real decision periods warm its observation
history, advancing only the reset clone. Expert commands are used in this
reset warmup only. They are absent from policy observations, normal rollout
actions, full-race evaluations and the deployment runtime.

Each four updates, evaluate **41 complete races** with distinct fixed seeds:
11 nominal and 30 with early steering disturbances lasting 50–250 ms.
These are development cases, used for selection, **not held-out proof**.
More finishes always win selection; among equal finish counts choose the
lower penalized mean, with DNFs charged 40 s. Initial source evaluation:
41/41 finishes, mean 23.957 s, median 23.404 s, best 23.308 s.
First four-update candidate: 41/41, mean 23.870 s, best 23.293 s.
Both are simulator results. Later live metrics are in `status.json`.

After 12 evaluations without improvement, restore the best weights and
change the exploration/curriculum mixture. Individual phases stop at plateau;
the overall pursuit has no fixed update limit. Checkpoints include optimizer,
RNG states, counters and curriculum settings. Restart creates fresh physical
episodes and does not claim bit-identical world continuation. Frozen source
copies and their hashes live in `ppo20/code/` and `frozen-manifest.json`.
Do not edit these copies or overwrite any loaded native library.

The user service survives closing this Codex conversation. It is enabled for
the next user login and makes at most three failure restarts per ten minutes;
normal STOP/goal exits do not restart. It cannot train while the PC is shut
down or suspended. The former hourly monitor remains disabled/inactive;
this training loop uses no LLM and does not switch Codex accounts.

```sh
systemctl --user status tm2020-top10-main.service
journalctl --user -u tm2020-top10-main.service -n 8 --no-pager
cat local/training/top10-20261030/ppo20/status.json
```

`STOP` in the run directory or SIGTERM requests a checkpointed stop. Model
exports do not inherit the old model's actual-client finish qualification.
The trainer can recognize a separately verified client result through
`verified-game.json`: exact map, model/replay hashes, normal worker return,
native replay metadata, zero respawns and a target-beating finish time.
**It does not automatically launch the game, collect that proof, or establish
top ten from a simulated time.** Before declaring top ten, refresh the public
threshold, use separate perturbed holdout cases and verify the candidate
finishes in the actual local client. The deployed model/runtime and replay
must be retained. Generalization to other maps is unproven.

## 100 Hz research and checks

The tenth-place and WR ghosts reproduce exactly at 10 ms in the frozen
native backend: 20.006 s and 19.988 s. Sampling those commands at 50 ms
fails the map. This shows that holding *these particular* demonstrations
changes their outcome; it does not prove that a good 20 Hz policy is impossible.
A 2001-state bitwise test also matches the scalar backend at 100 Hz.

The new vector ABI supports 10/50 ms decisions, bank resets and a single-world
microstep. Its frozen shared object is under `top10-20261030/native/`.
100 Hz exports carry an explicit distinct perception schema, so an older
runtime rejects them instead of silently running at the wrong cadence.
The new runtime uses the exact already-qualified physical owner to infer on
the first 100 Hz tick; discovery still requires its ordinary qualification.
Adaptive substeps continue to hold commands until the next macro tick.

Both behavior-cloning experiments and the subsequent 100 Hz PPO branch were
weaker than the reliable model. The latter stopped at update 97 / 6,356,992
transitions, retaining all checkpoints: its selected model finished 4/8
nominal races with a 35.953 s mean. It was not deployed or promoted.
Its stop and the reliable continuation are different services/directories.

Owned Windows tests for the new deployment passed all four variants:
continuous, discrete-17, discrete-33 at 20 Hz, and continuous at 100 Hz.
Observation parity: 256 rows, zero error. Consumer commands match CUDA
bitwise; shutdown, missing-body neutralization and hook restoration pass.
The original test rejected a fourth policy after successfully running it
because of a hardcoded three-variant assertion. The assertion now verifies
the complete set of heads/cadences; loader errors identify the failing export.
A subsequent audit caught a false-positive path: the fixture child expired
after 30 s with exit code 1, also the SDK probe's success value, and the Python
test could reuse old CSVs. Its timeout is now 180 s, longer than the bounded
120 s remote selftest, and timeout returns 125. Python deletes stale outputs
and requires fresh traces for every variant plus the final `fixture_complete`
marker, emitted only after the paused-physics shutdown test succeeds.
The corrected run must satisfy all of these checks before publishing a report.
These tests use an owned fixture process, **not the actual game**.

Evidence: `local/recon/internal-0.49/owned-windows-final.json`, deployment
manifest `local/recon/deployment-0.49/build.json`, and
`local/training/top10-20261030/{cadence-tests.log,100hz-physics-check.json,owned-windows-deadline.log}`.
The current training candidate's CUDA-to-native export also matches all 256
test rows in `local/recon/internal-0.49/export-current/report.json`.
`scripts/test_top10.py` verifies evaluator compatibility (including applying
disturbances before the one final i8 quantization), reliability-first selection
and real-history warmup without advancing sibling environments at both rates.
The two native executables `tm2020_internal_tick_test` and
`tm2020_hybrid_actions_test` also pass. This build directory does not register
CTest tests; execute those binaries directly.
