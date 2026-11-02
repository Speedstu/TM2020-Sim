# Fall 2026-01 champions

These are **map-specific hardcoded controller assets**, not general policies or
standalone executables. Each `.tmhyb` stores a reference trajectory, controller
parameters and any optional correction weights. The human controller also
includes its contextual action governor. Original bytes are preserved.

| Artifact | Control path | Preserved result |
|---|---|---|
| `human.tmhyb` | Normal 100 Hz input history; human-style constraints | Client finish **19.995 s**, zero respawns; 2,000 replay inputs decoded and matched in simulation |
| `legacy-record.tmhyb` | Historical direct physical controls, frozen device history | **19.986 s** on 64/64 nominal simulation cases; historical record controller used in the user's client session |

The legacy model belongs to the earlier record-seeking branch. The user reported
a world record during that period, but the retained search report does not
independently certify an official leaderboard record. This repository makes no
claim about a current online rank. Its 64 nominal seeds share one physical start
condition in the historical input mode; the separate perturbation suite finished
60/64. It has no normal-replay/human-input qualification and must not be described
as the humanized champion.

The human model's command metrics passed the observed and P10–P90 ranges of the
retained Top-100 cohort. This is a statistical proxy, not proof of human origin
or visual indistinguishability. A runtime cleanup failure after the successful
client finish prevented a complete live CSV dump; exact replay/simulation parity
is documented separately in `human-validation.json`.

## Run in the simulator

Build from the repository root and install the Python analysis dependencies:

```sh
python3 scripts/build_source_checkout.py --jobs 4
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/run_bundled_champion.py \
  --champion human01 \
  --map /path/to/Autumn-2026-01.Map.Gbx \
  --packs /path/to/Trackmania/Packs

.venv/bin/python scripts/run_bundled_champion.py \
  --champion legacy-record01 \
  --map /path/to/Autumn-2026-01.Map.Gbx \
  --packs /path/to/Trackmania/Packs
```

The runner selects the artifact's declared control mode and original evaluation
seed, verifies model and map hashes, and prints the simulated result. It never
attaches to the client or starts training. Add `--seed NUMBER` for another seed
or `--output new-report.json` to save a result.

Supply the exact map yourself: UID `ypPmohQofd72MyTsIsijKfrJH98`, SHA-256
`15eee4adcb2e726a336897a46f852632e8699586da4e3447ae21481d07142f08`.
Map files, Packs and replays containing embedded maps are not bundled.

`manifest.json` records SHA-256 checksums, schema versions, seeds and modes.
The adjacent validation summaries omit private process paths and network details.
