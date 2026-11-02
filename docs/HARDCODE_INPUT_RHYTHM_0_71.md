# Hardcoded controller with recorded input rhythm, 0.72 Top 10 phase

The deterministic map-specific hybrid controller remains the search engine. It computes steering from live position, velocity, heading and yaw errors, uses map references as feedforward, and emits binary pedals and signed i8 steering at 100 Hz. TMHYB v5 adds a causal C++ action governor with a per-map hard envelope derived from the user-confirmed human ghost input timelines. It applies maximum per-tick steering step, rolling one-second direction-change and rapid-reversal budgets, minimum steering hold, pedal transition budgets, and minimum gas/brake holds to every final command. Candidate references and mutations are projected through the same limits before evaluation, so optimization cannot produce an out-of-envelope action and receive only a score penalty for it. The governor changes the actual controls consumed by the simulator; it does not rewrite a replay afterward.

## Input and physics evidence

The owned Windows fixture sends all three command channels through the game's original input decoder and checks the resulting controls at the paired physical consumer. It exercised 100 consecutive 100 Hz ticks, verified exact command equality, observed zero non-neutral writes to physical controls, and independently decoded the captured owned bitstream with exact gas/brake/steer equality. That is an isolated runtime test, not a client replay. `local/training/human-rework-0.70/owned-causal-proof/proof.json` records the result and states `clientReplayVerified: false`.

Native rollouts report actual issued-command steering changes and variation per second, i8 step quantiles, sign reversals, pedal changes and duty, plus exact 10ms steering, gas-press/release and brake-press/release duration quantiles. The native observer does not alter commands. Original rank-1 ghost inputs on 01/03/06 decode as contiguous 100 Hz streams. Their steering changes per second are 16.51, 28.47 and 27.47; steering hold P10/P50/P90 are 10/10/80 ms, 10/10/30 ms and 10/10/40 ms. On 03, brake press P10/P50/P90 is 60/90/134 ms. On 06, gas press is 3,944/3,960/14,168 ms and brake press is 170/170/554 ms. The user confirms leaderboard ghosts are verified human runs.

## Baselines and current search

Before the search, normal-history A/B on the same 64 seeds and perturbations gave:

| Map | Normal-history finishes | Perturbed finishes | Mean finish time, normal |
|---|---:|---:|---:|
| 01 | 46/64 | 47/64 | 19,986.4 ms |
| 03 | 38/64 | 36/64 | 19,828.7 ms |
| 06 | 0/64 | 0/64 | — |

The old direct physical path is separately recorded as a diagnostic. For map 06 it finishes 64/64 nominal and 32/64 perturbed, while the normal-history path finishes 0/64 in this suite. Those results do not represent an apples-to-apples promotion test: the former bypasses the original input history, the latter must preserve it. The discrepancy is a remaining simulator/runtime parity problem.

The persistent service `tm2020-hardcode-inputs.service` now cycles through all 25 campaign maps in order `01, 03, 06, 02, 04–05, 07–25`, for 64 generations or 12 stale generations per stage, indefinitely. It is capped at 600% CPU and 4 GiB memory, runs one map at a time, and writes only to `local/training/hardcode-inputs-0.71`; preserved champions remain read-only. The separate campaign record search stays inactive with its checkpoints preserved. Existing maps 01, 03, and 06 have qualification artifacts; other maps stay pending until they receive the same-seed A/B comparison.

Latest same-seed 64-case A/B (`human-sim-comparison.json`): map 01 changes from 46 to 47 Top 10 normal, and 46 to 46 perturbed; finishes change 46→47 normal and 47→46 perturbed. Its input-style proxy passes both arms, but it fails the overall robustness gate because it regresses a perturbed finish and does not improve both Top 10 arms. Map 03 changes from 16 to 46 Top 10 normal and 16 to 50 perturbed; finishes change 38→54 normal and 36→57 perturbed. It substantially improves Top 10 and finishes, but fails the human-style proxy, chiefly due to excessive steering reversals and raw steering steps. Neither candidate is promoted.

## Human input comparison

`scripts/compare_human_sim_inputs.py` compares commands on the same 64-seed A/B and includes only simulator finishes at or under the cached Top 10 time. It reads the user-confirmed human leaderboard ghosts and each simulator trial's issued-input statistics. Current result (`local/training/hardcode-inputs-0.71/human-sim-comparison.json`):

| Map | Source | Top 10 finishes | Steering changes/s | Reversals/lap | Small reversals/lap |
|---|---|---:|---:|---:|---:|
| 01 | Human cohort median (ranks 1, 3) | — | 21.50 | 44 | 25.5 |
| 01 | Previous controller | 46/64 normal; 46/64 perturbed | 24.82 | 188 | 142 |
| 01 | Latest candidate | 47/64 normal; 46/64 perturbed | 21.23 normal; 21.32 perturbed | 59.7 normal; 61.4 perturbed | 23.1 normal; 23.9 perturbed |
| 03 | Human cohort median (ranks 1–3) | — | 30.27 | 54 | 32 |
| 03 | Previous controller | 16/64 | 37.17 | 164 | 147 |
| 03 | Latest candidate | 46/64 normal; 50/64 perturbed | 33.42 normal; 33.50 perturbed | 117.2 normal; 118.5 perturbed | 80.6 normal; 81.1 perturbed |

On 01 the rank-2 ghost decodes to neutral gas and steering throughout, so it is omitted from the command-rhythm cohort; ranks 1 and 3 are used. Map 03 uses ranks 1–3. The optimizer uses these per-map cohort medians rather than fitting only rank 1. The report's proxy uses steering rates ±20%, reversals ±50%, i8-step and hold quantiles, and pedal duties ±0.03. This is command-stat screening, not proof that an actual replay is indistinguishable from a person. Client replay validation remains unperformed.

Candidate qualification reports finish rate, best/mean/median/worst times, checkpoints, and command-rhythm metrics on the same 64 seed families. Optimizer revision 0.74 keeps Top 10 count and finish count as the first two lexicographic goals. When both counts tie, it minimizes measured command-rhythm distance to the per-map median of up to three user-confirmed human leaderboard ghosts before using lap time as a tie-break. The prior 12 ms cap flattened the score for large differences and gave a twitchy candidate too little gradient toward natural inputs; it is removed. The candidate search now also tests whole-reference median filters at 30–90 ms to directly suppress isolated steering taps, retaining the same physics and command path. Candidates never write to preserved champions or deploy automatically. Promotion also requires a fresh client replay.

## Hard human action-space revision (TMHYB v5)

`local/training/hardcode-inputs-0.71/human-action-envelope.json` stores the exact limits and source ghost hashes for all 25 maps. Limits use the median across usable verified human ranks: steering step P99 ×1.2, steering change rate ×1.2, fast and small reversal rates ×1.25, pedal transition rate ×1.5, and observed minimum holds. The signed direction remains quantized to the client's i8/127 representation. The same map limits are serialized in every v5 asset and enforced at the native action output. Training mutations are projected before serialization as well.

The full v5 rollout smoke test loaded the asset in the rebuilt vector simulator and measured 8 Fall 01 trials. The action-envelope assertions passed, but **0/8 finished**. This is an early constrained baseline, not a successful model; the trajectory and control strategy need to be re-optimized within the restricted space. All legacy A/B qualifications are now marked pending because they predate the v5 hard constraints. The new comparator requires a fresh same-seed 64-case constrained baseline/candidate A/B and both human-style and Top 10 gates. At the current status snapshot, no campaign map has completed this v5 qualification, and no Trackmania client replay has been validated.

The indefinitely running `tm2020-hardcode-inputs.service` has been restarted with its saved map incumbents and cycles maps 01, 03, 06, 02, 04–05, and 07–25. The live map and stage are recorded in `local/training/hardcode-inputs-0.71/human-campaign-status.json`. The old champion files remain read-only; there is no automatic deployment.

## Limits

No new replay from Trackmania has been independently decoded. The runtime's owned decoder test is not evidence that a game-produced replay has non-neutral inputs. Ubisoft Connect shows Trackmania in its library, and the executable at the shared path matches the audited build hash, but the Play action did not start a visible game process during the latest attempt. Client recording remains unverified until an ordinary offline map session yields a fresh `.Replay.Gbx` whose commands decode and match physical consumption tick for tick.

Run the isolated optimizer with:

```sh
systemctl --user status tm2020-hardcode-inputs.service
tail -f local/training/hardcode-inputs-0.71/training.log
```

The original record search is currently inactive; its service configuration and checkpoints are preserved. Ubisoft Connect and the game files are in the same shared install directory, and `Stadium.pak` is readable by the simulator. At the latest process check no Trackmania client process was running; the Ubisoft launcher log shows an earlier brief game-session connect/disconnect, not a completed local replay test.
