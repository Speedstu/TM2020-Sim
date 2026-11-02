# PPO 0.50: measured continuation and actual-client checks

The overall top-ten goal is **not achieved**. The latest read-only leaderboard
snapshot still has a tenth-place time of **20.006 s** for Fall 2026-01,
UID `ypPmohQofd72MyTsIsijKfrJH98`.

The current principal service is `tm2020-top10-main.service`, running
`local/training/adaptive-20261031/main/`. It uses CUDA PPO and native CPU
physics. `local/training/current.json` points to its status and artifacts.
The old hourly monitor remains disabled/inactive. No LLM monitors this loop.

## Changes implemented

- Complete physics checkpoints can now be sampled from the agent's own
  full-start training laps. Sixteen time strata avoid concentrating every
  reset in the last seconds of the WR. Restoration includes session/world,
  checkpoint tracker, clock, prior commands and the actual five-frame history.
  Checkpoint collection excludes episodes that already began from a checkpoint.
  There are no expert commands or 21-second graduation gate in this pipeline.
- Production caps each time stratum at four checkpoints (64 total), rather
  than the pilots' sixteen (256 total), to bound memory. Native ABI slots are
  independently owned and freed; physical siblings do not advance on restore.
- Pedal exploration has an explicit temperature. The selected profile uses
  `.5` during training; its Bernoulli sampler and log probability agree.
  Deterministic deployment still uses the zero-logit threshold. Steering
  retains its continuous tanh/i8 contract. The reward is unchanged: successful
  full return `100 - finish_seconds`, DNF `-140`, scale .01, gamma 1, lambda .995.
- A distinct 72-feature encoder adds local angular velocity, three future
  checkpoint vectors and twelve ground probes out to 224 m. It preserves
  the qualified old 48 features and their masked contact/turbo channels.
  These are coarse geometric cues, **not a solved centerline or route graph**.
  The future-trigger heuristic can be ambiguous on branching maps.
- The 72-feature ABI and policy schema are explicit. Existing State48/API4
  layout and legacy exports stay compatible. The DLL selects the correct
  encoder/history width from the model schema and rejects incompatible shapes.
  New columns initialize to zero, preserving the original policy function.

The principal selected profile currently consumes the legacy 48 features.
The new encoder was not forced into deployment merely because it was added.

## Matched experiments

Six profiles ran at seeds 99701/99702: **16 updates × 16 worlds × 512
decisions = 131,072 transitions per run**, with identical source weights,
physics, 50 ms cadence, development cases and initial sampling seed.
The observation expansion explicitly resets the sampling RNG after initialization.
There were twelve runs in total. Full-case development and pilot comparison
sets include nominal, early-disturbed and midrace-disturbed starts.

The following are averages across the two selected checkpoints on the shared
32-case pilot comparison set. Failures count as 40 s. This set helped choose
the profile, so it is **not the final independent qualification**.

| Profile | Mean penalized time | Mean arrivals / 32 | Pilot gates passed |
|---|---:|---:|---:|
| Control continuation | 24.434 s | 31.5 | 1/2 |
| Own-state checkpoints | 24.078 s | 32 | 2/2 |
| Pedal temperature .5 | **23.925 s** | **32** | **2/2** |
| Own checkpoints + pedals .5 | 24.243 s | 31.5 | 1/2 |
| New preview + own checkpoints + pedals .5 | 24.288 s | 31.5 | 1/2 |
| Preview with larger steering noise | 24.551 s | 31.5 | 1/2 |

A separate full-gas specialization was motivated by both public fast ghosts
having no brake/gas-off ticks. Its larger-noise/higher-LR pilot failed its
qualification and was not selected. It used a different 32-update budget and
is not included as a matched row above.

The selected pedal-profile checkpoint then faced a **new 64-case suite**,
seed 99931, against the unmodified frozen source: **64/64 vs 62/64 arrivals**;
penalized means **24.315375 vs 24.402578 s**. It passed completion, mean and
worst-decile gates. This is primarily evidence of a reliability improvement,
not a top-ten line or a guaranteed improvement in nominal client time.
Its exported controls match CUDA bitwise on 256 probe observations.

Evidence: `local/training/adaptive-20261031/pilot-comparison.json`,
`comparison-summary.json`, individual protocols, and
`final-pedals-seed99701/report.json`. The exact pilot code is archived under
`pilot-code/`; production code/native binaries are separately frozen under
`frozen/` with hashes in its manifest. Do not overwrite a mapped shared library
or edit the code copies used by a running job.

## Actual client: two completed races, no speed upgrade

After the user reopened the client in its working race state, the qualified
candidate completed Fall 2026-01 **twice at 23.875 s**. First proof: actual
client result shows PB 23.366 s and current-run delta +0.509 s. Second proof:
the finish arch and race timer directly show 23.875 s.

Both runs read physical state and apply all driving commands inside the
physical consumer. Consumer readback is exact, no unexpected faults occurred,
and workers returned normally. The second run records **zero gas/brake/steer
after worker return, before any post-trial UI action**, and the original 13
consumer bytes were restored. Fault 6 means `stopped`; it can result from
normal shutdown or the retired-body stop path, and does not prove a finish.

This candidate is **509 ms slower** than the retained real-game champion.
The old `deployment-0.46/candidate.tmppo` remains the game reference. The
simulation qualification did not grant a speed promotion in the client.
No official replay for the new runs was verified; these are fresh screenshot
and internal-trace-qualified arrivals. No zero-respawn replay or top-ten claim
is made. The proof files intentionally do not satisfy the stricter goal gate.

Evidence:

- `local/recon/internal-0.50/verified-live-result.json`
- `live-user-ready/control/finish-proof.png` and its `game-result.json`
- `live-user-repeat/control/finish-proof.png`, `game-result.json`,
  `post-stop-proof.json`, `trial.json` and the control trace/report

Earlier attempts in the initially launched client did not observe a real
reset and were rejected before driving. Their failed qualification reports
are retained. The ownership/start safeguards were not relaxed. Game-only
screenshots now wait for the foreground window and use its bounds; menu/reset
keys use the compositor, while mouse positioning uses logical compositor
coordinates. These UI operations are separate from DLL driving commands.

## Current continuation and bounded preview research

The main service starts from the independently qualified pedal-profile weights:
32 worlds, 1024 decisions/update, eight CPU workers, actor LR 3e-7, critic LR
3e-5, 64 development trials every four updates. It keeps the strongest selected
checkpoint, including nominal-completion protection and a fixed initial nominal
mean ceiling. At plateau it restores that checkpoint and varies reset coverage
and steering exploration. It has no overall update cap; STOP, signal, failure,
or a separately verified real-client top-ten result can end it.

The 64 current development cases are used for selection, not held-out proof.
The main's later best checkpoint is not the same artifact as the source tested
in the two client races; it does not inherit that qualification.

`tm2020-preview-adapter.service` is a separate **bounded** experiment, up to 64
updates or its plateau cutoff. It trains only the newly added actor input
columns, preserving original actor coefficients/head, while training its critic.
It is not auto-enabled at login and does not automatically promote or inject
a model. Its status/qualification are under `preview-adapter/`.

The main service is enabled at user login and restarts only on failure, at most
three times per ten minutes. Checkpoints retain optimizer/RNG/counters; resume
creates fresh episodes and regenerates the bounded physical checkpoint banks.
It does not claim a bit-identical physical-world resume. Current code and native
binaries are frozen; imported fixed project assets and source/map hashes are
recorded in each protocol.

The terminal goal check requires a fresh leaderboard snapshot, exact model and
replay hashes, native replay metadata with zero respawns, matching client-control
evidence and a target-beating time. A simulator time or screenshot alone cannot
end it as a verified top-ten result. It does not automatically launch future
client trials or submit leaderboard results.

```sh
systemctl --user status tm2020-top10-main.service
cat local/training/adaptive-20261031/main/status.json
journalctl --user -u tm2020-top10-main.service -n 6 --no-pager
```

## Verification

- 764 tested transitions: new backend rigid words/rewards match the frozen old
  backend exactly.
- Four new tests: checkpoint future/sibling isolation, 48-feature prefix parity,
  complete-lap compatibility of zero-column transfer, CPU/CUDA history on resets.
- Owned Windows fixture: all **five** policy/head/cadence variants pass, including
  the new encoder; 256 observation rows have zero Linux/Windows error.
  Maximum measured perception time in that fixture: 489.9 microseconds.
- Existing three GAE/PPO identity tests and seven guarded-runner tests pass;
  four synthetic evidence-gate tests reject simulation/stale/mismatched results.
- Internal tick and hybrid-action native tests pass. Actual-client evidence is
  recorded separately above and is not inferred from these fixture tests.

Artifacts remain specific to this map. Unseen-map competence is unproven.
