# TM2020-Sim

**Headless Trackmania simulation, a native C++/Rust SDK, and driving-controller research.**

[![Source checks](https://github.com/Speedstu/TM2020-Sim/actions/workflows/source-checks.yml/badge.svg)](https://github.com/Speedstu/TM2020-Sim/actions/workflows/source-checks.yml)
[![License: GPL v3+](https://img.shields.io/badge/License-GPLv3%2B-blue.svg)](LICENSE)

Run physics without opening the game, evaluate controllers in parallel, and
inspect steering, throttle and brake commands at **100 Hz**. Includes two
preserved Fall 2026-01 champions and tools for human-style input analysis.

The simulator's physics and asset loading come from **[Gearbox](https://github.com/Mergemat/gearbox)**,
by Bagautdin Omarov and contributors, pinned to
`e0583ee55168e950a65a645778e591bd26b6a0f2`. This project adds the Linux port,
vectorized environments, native SDK, controllers, optimization and validation
tools. It does not claim an independently reverse-engineered complete game.

## What's included

- **Headless physics:** native 10 ms ticks, full resets, checkpoints and finish events.
- **Parallel environments:** a C++ batch API over the Rust physics backend.
- **Native SDK:** C++20 interfaces, C ABI, Rust bindings and autonomous regression tests.
- **Driving controllers:** trajectory tracking with physical-state feedback and optional learned corrections.
- **Human-style controls:** binary pedals, quantized steering, input-history handling and contextual action constraints.
- **Research tools:** hardcoded-controller search, historical PPO experiments, replay decoding and matched-seed evaluation.

Physics runs on the **CPU**. Optional PPO branches can use CUDA for neural-network
optimization. The current champion branch uses map-specific hardcoded tracking;
it is not a universal policy that discovers an unseen track from scratch.

## Included champions

| Fall 2026-01 model | Preserved result | Input mode |
|---|---|---|
| [Human-style champion](models/fall-2026-01/) | **19.995 s** in the client, zero respawns; replay inputs matched in simulation | Normal recorded inputs at 100 Hz |
| [Legacy record champion](models/fall-2026-01/) | **19.986 s**, 64/64 nominal simulation finishes | Historical direct physical controls |

Both original `.tmhyb` artifacts are included with checksums, evaluation seeds,
mode information and validation summaries. The legacy model is the retained
controller from the earlier user-reported world-record session. The stored
search evidence does not independently certify an official record or current
online rank. It does not carry the human model's input qualification.

The human model's measured input statistics fell within the retained Top-100
cohort's P10–P90 ranges. This does not establish human origin or visual
indistinguishability. See [champion details and reproduction](models/fall-2026-01/README.md).

## Quick start — Linux x86-64

Requirements: Python 3.10+, CMake 3.21+, a C++20 compiler, Rust/Cargo 1.98+,
and `liblzo2.so.2`. Cargo downloads the locked dependencies on the first build.

```sh
git clone https://github.com/Speedstu/TM2020-Sim.git
cd TM2020-Sim

# Debian/Ubuntu system dependencies
sudo apt install build-essential cmake pkg-config liblzo2-dev

# Build the SDK, simulator, controller and decoding tools; run native tests
python3 scripts/build_source_checkout.py --jobs 4

# Python controller/analysis helpers
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The build does not start training, launch the game or modify a game installation.
Use `--native-only` for the C++ subset, or `--offline` when Cargo dependencies
are already cached. Build products are stored under `build/` and `cache/`.

### Run a champion in the simulator

Provide your own exact Fall 2026-01 map and your installed game's `Packs` folder:

```sh
.venv/bin/python scripts/run_bundled_champion.py \
  --champion human01 \
  --map /path/to/Autumn-2026-01.Map.Gbx \
  --packs /path/to/Trackmania/Packs
```

Use `--champion legacy-record01` for the historical record controller. The runner
selects the correct input mode and original seed, validates the map/model hashes,
and reports finish time and checkpoints. It runs in the simulator only.

### Load a different map and benchmark physics

```sh
cache/source-fast-target/release/tm2020-fast-probe \
  /path/to/map.Map.Gbx /path/to/Trackmania/Packs
```

This probe applies full throttle and measures physics throughput; it is not a
trained driving policy. The local source-build check measured about **51k physics
ticks/s** for this probe on the research PC. That is not end-to-end PPO training SPS.

## What are game assets?

The simulator reads external files from a legitimate Trackmania installation:

- **`Packs/*.pak`:** proprietary block geometry, collision shapes, vehicle tuning
  and other game resources. The `Packs` folder must include `Stadium.pak`.
- **`.Map.Gbx` tracks:** the map layout and referenced blocks/objects.
- **Optional `.Replay.Gbx` / `.Ghost.Gbx` files:** recorded runs used for analysis
  and validation. Some replay files also embed the map.

These game files and game executables are **not distributed here**. Install the
game and supply your own map path. The bundled champion files are controller
parameters/reference data; they do not contain the game's Packs or a map file.
Gearbox's open-source code is included separately under `third_party/`.

## Repository layout

| Path | Purpose |
|---|---|
| `third_party/gearbox/` | Pinned GPL physics and asset-loader sources, with Linux portability edits |
| `integrations/` | Rust environments, C++ vectorization, training and client adapters |
| `native/include/`, `native/src/`, `native/tests/` | Native SDK, controllers and tests |
| `sdk/`, `rust/`, `src/` | Additional SDK interfaces, Rust binding and GBX tools |
| `models/fall-2026-01/` | Human-style and legacy-record champions, checksums and summaries |
| `scripts/` | Builds, controller search, replay analysis and audits |
| `docs/` | Architecture, methods, validation and historical research notes |
| `config/` | Experiment configurations and historical service examples |

## Training and validation

The current research optimizes reference trajectories, feedback gains and pedal
rhythms while constraining actual applied actions. Human ghosts provide
initialization data and statistical references, not a mandatory replay tape.
Evaluation compares fixed normal and perturbed seeds before promoting a model.

Start with [the hardcoded training method](docs/HUMAN_HARDCODE_0_75.md) and
[the source-build validation](docs/SOURCE_VALIDATION.md). Full campaign searches
require additional local maps, ghost cohorts and experiment metadata; the two
bundled controllers do not replace that training corpus. Historical scripts and
systemd examples are preserved for research, not enabled automatically.

Client integration is experimental and intended for local/offline tests. A known
post-finish detachment fault still requires a client restart before another
injection. Compilation and simulator tests do not certify arbitrary client
versions or all game mechanics. Dated research notes may reference private local
evidence that is not part of this repository.

## Contributing

Useful contributions include reproducible physics comparisons, controller
robustness, input-history parity, performance measurements and portable builds.
For a discrepancy, include the build/revision, map UID, seed, input mode and a
minimal reproducer. Separate simulator results from actual client observations.

## License and credits

Distributed under **GPL-3.0-or-later**, with third-party notices preserved.
See [LICENSE](LICENSE), [THIRD_PARTY.md](THIRD_PARTY.md), and
[the Gearbox integration notice](integrations/fast-training/NOTICE.md).
The vendored `lzokay-native` decoder retains its MIT license. Trackmania and its
proprietary assets belong to their respective owners.
