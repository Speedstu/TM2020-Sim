# Hardcode training: low-median human input rhythm

User steering (2026-11-01): defer injection, retain the verified 01 and train each
other map in order, with input activity slightly below its own Top100 median.

`scripts/build_human_rhythm_profiles.py` reads original decoded ghost timelines
and reports each map's steering-change and rapid-reversal count distributions.
It retains usable ranks, excluded neutral streams and whether the full Top100
cohort is present. No claim of independent human-origin certification is made.

The hardcode trainer's soft steering-change and steering-variation targets are
90% of the respective map median, clamped to the measured P25–P50 interval.
This roughly matches 01's successful activity level. Other pedal/hold/reversal
targets stay at their observed medians; the hard human action governor stays
active. This is a target in the search score, not a claim every candidate already
achieves it, nor an arbitrary low hard correction cap. Finish/target-time counts
precede rhythm preference. The 01 model/checkpoints/client replay are untouched.
Lap-long constant gas/brake channels are excluded from hold-duration penalties
when both bot and human cohort have the same constant duty and no transitions.

## Useful initialization for normal input history

On 02, preserved champions screened at 0/16 finishes. A direct human-input test
also incorrectly appeared unfinished because it stopped before the final physics
tick. A bounded tail completes the original Top1 stream in exactly 21,290 ms;
Top2, Top5 and Top10 streams also finish at their original declared times.
Top3 still diverges and is excluded as a seed.

`scripts/bootstrap_normal_hardcode.py` captures route targets from these genuine
normal-input physical rollouts. It never writes a reference into the simulator's
vehicle state. The exported candidates use live localization/feedback and the
same hard governor; human actions are initialization data rather than mandatory
per-tick optimization targets. Small feedback variants are screened before
training. This recovered a 5/16 initializer, enabling useful optimization.

`scripts/run_hardcode_human_campaign.py --bootstrap-normal-routes` now invokes
this diagnostic initialization for maps whose preserved models have no finishes.
It still stops a failed map instead of spending a full stage at zero finishes.
Each stage is bounded and stops at plateau, retaining incumbents/accepted
checkpoints. Maps advance to Top10 search only after their complete 64 normal +
64 perturbed Top100/human audit passes. No client process is used by this worker.

Active branch: `local/training/hardcode-human-0.75/`.
Status: `campaign-status.json`; per-generation evidence:
`02/campaign-search.log`, then the corresponding map folder in sequence.
Targets/cohort distributions: `rhythm-profiles/`.
Incomplete cohorts are being collected and profiles regenerated afterward.

Checks: 14 hardcode regression tests, 3 metric-comparison regression tests,
Python syntax checks, and the 02 source rollouts/screen completed. Exact current
training results belong to status/log JSON; early improvements are not final
Top100, Top10, human-style or client qualification.

## Strict map ordering update

`--stay-until-qualified --human-focus` replaces the single-pass progression.
The worker remains on 02 until its 64 normal and 64 perturbed cases all satisfy
Top10 and measured human P10–P90 criteria, then advances to 03. A plateau ends
one bounded stage, retains its checkpoints, and restarts search on the same
map with a new stage seed. A zero-finish parity diagnostic failure or execution
error stops that worker on the current map rather than silently skipping it.
Client injection remains deferred: these are simulation qualifications.

Human-focused fitness counts jointly fast and human-style arrivals first.
Before an exact style pass exists it rewards partial style-metric improvements
on target-time arrivals, so a 96-run candidate with eight wrong pedal metrics
does not permanently prevent exploration of a better pedal schedule. Stationary
or DNF episodes earn zero such credit. The accepted model remains a hardcode
tracker with live physical feedback and the original action governor.

02 diagnosis: direction already passed the common human bands, but the incumbent
used four short gas cuts while cohort medians implied about two longer cuts.
Mutation now edits/removes individual gas/brake intervals and can jointly select
an interval count and duration from the map medians. It does not copy a ghost
schedule. These proposals still pass the governor and full physics evaluations.
Additional tests check mixed time/style fitness, gas-interval edits, joint
interval-count proposals, and rejection of one failing perturbed qualification
case. 17 training + 3 comparison + 3 qualification-gate regressions pass.
