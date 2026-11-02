# TrackVis — native aerial simulator viewer

GTK4/Cairo desktop app. **No Zen, no localhost web server, no Codex interaction.**
Lightweight CPU policy inference (NumPy) with the simulator's real native physics.
The 16 independent spectator environments are separate from the PPO learner's private training instances.

## Commands

- `trackvis`: launch a native window (16 spectators)
- `trackvis --cars 32`: launch a native window (32 spectators; more CPU use)
- `trackstat`: interactive terminal statistics; **auto-follows the preferred active training session (PPO or hybrid campaign)**; exits with Ctrl+C or Q
- `trackstat --list`: list **all** known training runs (active and historical)
- `trackstat --run fall-campaign-internal-0.55`: follow the active 25-map campaign optimization
- `trackstat --run fall01-record-0.56`: inspect the Fall 01 dedicated record search
- `trackstat --run fall-campaign-internal-0.55/05`: inspect one specific map
- `trackstat --run ppo20`: view historical PPO statistics
- `trackstat --run top10-20261030/ppo20`: lock to a full run path if names conflict
- `trackstat --select`: open the interactive run picker on launch
- `trackstat --once`: one-line-per-metric snapshot
- `trackstat --json`: machine-readable snapshot

Inside **trackstat**: press **S** for the run selector; **Up/Down** then **Enter** to choose, or type part of the run name to filter. **TAB** switches active sessions; **A** switches back to automatic live-run detection; **R** refreshes; **Q** or **Ctrl+C** exits without ever terminating the training.

`trackvis` controls:
- **Wheel:** zoom
- **Drag:** pan
- **Click a car:** select
- **F / Home:** fit race track
- **M:** full-map overview
- **Space:** pause spectator simulations
- **R:** reset spectator simulations
- **Escape / Q / Ctrl+C in the launching terminal:** close window and shut down spectator worker thread.

## What the viewer shows
The **real map block data** from `local/campaign-2026-autumn/Autumn-2026-01.Map.json` and
the actual physical car position/heading per spectator simulation step.
The road decks are *stylized footprints of the original blocks*, not detailed
pixel-exact collision mesh surfaces. Some curved/tilted blocks are approximated
visually for readability and do not alter native physics.

The model is read from the latest known best PPO checkpoint at spectator startup,
and is then applied independently to 16 cloned environments. Nothing is written
to training directories, no locks attached and no training workers inspected or modified.
This is **not** an in-game spectator, not online multiplayer, and not the exact
positions of the current training workers. Live training SPS / scores / thermal stats
are shown in parallel from their read-only status files.

## Files
- `app.py`: GTK4 native GUI and 60Hz draw timer; cached map atlas
- `scene.py`: real map block painter
- `simulator.py`: independently cloned native-physics car runs
- `common.py`: read-only current PPO run discovery
- `stats.py`: terminal live statistics

No external pip or npm install required: uses already installed system GTK4
and the project Python environment. `trackstat` uses only system Python.

## Current training format (31 October 2026)

The project now has two workflows. `trackstat` detects both automatically:

- **Legacy PPO**: updates, transitions, SPS, phases, best simulated lap.
- **Hybrid campaign optimizer** (`optimize_fall_campaign.py`): generation, plateau age,
  16 candidates × 4 development cases, candidate evaluation throughput (SIM EVAL/S),
  per-map target, best/mean simulation time, target hits, maps completed,
  nominal/perturbed holdout results for completed runs, and campaign milestones.

**SIM EVAL/S is not SPS**. One evaluation is one native simulation trial
of a candidate policy; there are 64 evaluations in a 16×4 generation.
No physics-tick count is recorded by the new optimizer status files, so
TrackStat never invents one. New hybrid models are `.tmhyb`, not `.pt`.
The training is reference-assisted and **not game verified**; a best simulated
lap or map target cannot be represented as an official in-game record.

Discovery is automatic from `local/training/**/status.json` and read-only
optimizer process paths. Both active campaign sessions and individual map
folders appear in the run picker; stopped runs remain viewable. The helper
never sends a signal to Codex or any training process. Ctrl+C closes only
this monitoring terminal.

## Staged world-record campaign (0.57, 31 October 2026)

`trackstat` now auto-discovers the orchestrator
`local/training/fall-campaign-world-records-0.57/status.json` and every
`stages/*/NN/status.json` with its latest physical throughput.
The root **orchestrator is not PPO** and should not be displayed as a single
map's generation result. It records its own target rank, active maps and
24-map progress. Individual stage runs provide:
- Native physics steps/s (SPS), simulated ticks/generation, 16×4 candidate trials
- Generation number, plateau counter, target gap, world-best reference time
- Explicit absent best time (—) when no candidates have completed
- Read-only CPU/GPU temperatures and load

`trackstat` displays a global campaign dashboard by default, including
aggregate SPS across its simultaneously active maps. Live examples:

```bash
trackstat
trackstat --map 21
trackstat --map 22
trackstat --run fall-campaign-world-records-0.57
trackstat --run fall-campaign-world-records-0.57/stages/000/21
trackstat --list
```

Interactive: **Tab** cycles campaign + active individual maps; **S** searches
all runs including historical; **A** resumes the automatic global dashboard;
**J/K** or Up/Down scroll; **Ctrl+C/Q** closes only TrackStat.

A simulated threshold meeting the Top 1 time is not a confirmed online
world record. The monitor never writes scores or controls the learner.
