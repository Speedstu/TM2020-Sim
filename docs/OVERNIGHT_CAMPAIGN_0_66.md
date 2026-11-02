# Overnight campaign search, 2026-10-31

The user requested continuous search until they return. The campaign service
resumes its saved 02–25 queue with `--rounds 0` and
`RuntimeMaxSec=infinity`: no scheduled end time. Individual plateau stages
still rotate their basis, spread and RNG; saved candidates are retained.

Two maps run in parallel with eight native workers each, an 8 GiB reservation
per map and 6 GiB host reserve. This replaces the underestimated 4 GiB/map
reservation that admitted several large worlds into swap. The distribution's
timeout-abort override is superseded by the installed `90-runtime.conf`;
stopping cannot produce large training core dumps. Sleep/idle inhibition is
active while the service runs. The old hourly monitor remains disabled.

The progress-capable vector wrapper retains the unchanged 0.58 native physics
and zero launch correction. Full physical output bytes match the old wrapper
on common perturbed cases for maps 02 and 03. For unfinished candidates,
checkpoint count and then maximum reference progress now break ties, and
stage selection retains those improvements instead of treating every DNF as
equal. Complete arrivals and measured finish times outrank that proxy.
The simulator no longer imports Torch/CUDA merely to save JSON.

Startup evidence:
`local/training/campaign-speed-0.66/overnight-start.json`.
Live status:
`local/training/fall-campaign-world-records-0.57/status.json`.
Service:
`tm2020-campaign-world-records.service`.

At restart, nine of maps 02–25 meet their recorded Top-10 thresholds in
nominal simulation; 12 meets its recorded Top-1 time goal. These are simulator
milestones, not a claim that all campaign maps are client-verified or will
finish by morning. Live candidates remain frozen during the search.

Restart verification observed continuing generations on 02 and 25, followed
by automatic rotation from plateaued 02 to 03. Memory swap usage for the
service was zero. Eleven scheduler/target regression tests and the native
output parity checks passed before the restart.

The user also requested bounded checkpoint storage. The companion service
`tm2020-campaign-retention.service` checks every five minutes without restarting
the running search. It retains three recent completed stages and three recent
top-level model snapshots per map, plus every referenced incumbent/resume
model and the active stage. Only finalized stages acknowledged by the parent
are eligible. Superseded generated model files are pruned with SHA manifests;
identical historical reference copies share the canonical map reference.
Reports, client evidence, native binaries and source assets are preserved.
Five retention regression tests cover active/unacknowledged/incomplete stages,
incumbent preservation, recent history, references and external symlinks.
Status is stored in `retention-status.json` beside the campaign status.

The user subsequently clarified a strict campaign-wide priority: **all maps
Top 10 first, then all maps Top 1**. The scheduler now excludes already
Top-10-qualified maps while any remaining map lacks a complete nominal
qualification at its Top-10 threshold. Once all maps pass, it automatically
targets rank 1 and preserves any already achieved rank-1 results. A failed
map cannot silently unlock the second phase. Six phase-order regression
tests cover this barrier, incomplete holdouts, existing champions and
retaining qualified incumbents over unstable development improvements.

The active queue covers 02–25; 01 retains its previously completed,
user-confirmed record. Live candidate models are still separate from this
simulator scheduling and require client testing for actual race claims.
