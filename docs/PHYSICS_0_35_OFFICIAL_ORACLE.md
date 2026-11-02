# Research 0.35: exact server oracle and sphere ray

The **official dedicated server** is now a local physics oracle. Its simulation
executes Nadeo's game code; it is not an independently reimplemented, complete
simulator. The independent Gearbox backend remains experimental and does not
qualify as exact across all maps, cars, contacts and states. The SDK release
remains 0.26.0, and the bot runtime does not use Openplanet.

## Official server provenance

The binary came from Nadeo's `TrackmaniaServer_2026-05-15` CDN archive, whose
archive SHA-256 is `5379519e729b882f67892b593c65bfe6ff11989e55f3ddd1ca6ab3029ca1df1a`.
The Linux `TrackmaniaServer` executable SHA-256 is
`3b6107824feea402bd32c888e994dcd6df4a10afc8676a2647ac9560ccf0d779`.
The executable matches the build identified by `vjeux/trackmania-tas`.
Neither executable nor Packs are included in our source/evidence archives.
This is a native Linux ELF executable under WSL, not a Wine process.

The clean upstream TAS checkout is pinned at
`036a65ba6aaef87b4579b8ee5a770729341dc572` in `cache/trackmania-tas-upstream-036a65b`.
The separate `cache/trackmania-tas-compat-0.35` checkout changes the
Rust 1.99 C-variadic `open` declaration and the target CPU from `znver4` to
`x86-64-v3`, and makes `fk trace` use the upstream typed validator ownership
resolver. The CPU change is necessary on this machine: the first build
contained AVX-512 instructions and failed with SIGILL. The upstream checkout
is unchanged. `scripts/prepare_tas_compat.py` applies the checked-in
patches in `integrations/tas-compat-0.35/` to a new checkout after checking
the original's revision and clean status; a separate reproduction checkout
passed this preparation check.

`scripts/run_official_server_oracle.py` checks the server hash, stages a
supplied map and ghosts, invokes `/validatepath=.`, and parses the **validated**
result separately from the replay's declaration. Its first public fixture run
is `local/recon/official-server-0.35-human-oracle.json`: two independently
validated finishes equal their declared 22,730 and 23,013 ms. This verifies
that the oracle works on those files; it does not prove the May 2026 server
is equivalent to the installed October 2026 client for every mechanic.

The TAS `tmsearch` search workspace builds on this host. All eight
`oracle_e2e` checks passed with `TM_REQUIRE_ENGINE=1`; they exercise the real
server, including acceptance of a true result and rejection of false time and
DNF claims. A fork checkpoint must be calibrated against its boundary and any
fork-derived finish must be revalidated by a whole-run server invocation.
The fork mechanism is not arbitrary-state `reset/step`, and its results can be
false when a candidate diverges from the checkpoint. `tmsearch` therefore
uses fork results as a search gradient, with the plain oracle deciding banked
results. Our direct `fk server check` control produced 20/20 fork-versus-full
matches (3 finishes, 17 DNFs), zero whole-run repeatability mismatches and a
measured 2.82x speedup for this one fixture and mutation window. The
independently captured report is
`local/recon/official-server-fork-check-0.35-v1.json`. A `tmsearch search`
smoke reached checkpoint calibration but timed out after 180 seconds while
checking the fixture's telemetry provenance through `fk regen`; that search
path is not qualified by this run.

The original `fk trace` path resolved a noncanonical address
`0x3f8000003f800538` through its default heuristic chain and produced zero
rows. Its self-check rejected that output. Our small trace patch instead
uses the existing `ValidatorCar` type: the captured validation callback's
controller, simulation, playground, sole participant and `CGameVehiclePhy`
ownership fields name the controlled car. Both fresh-process runs then
produced **1,156 byte-identical trajectory rows**, with zero clock gaps and
valid quaternion norms. Evidence is
`local/recon/official-validator-trace-0.35-v1/report.json`; the portable runner
is `scripts/run_official_trace.py`. These are resumed server trajectories,
not proof that an arbitrary fork matches a from-start run at every physical
state. The general stepping/training API remains unfinished.

To reproduce the plain oracle under Ubuntu WSL, from the project root:

```sh
python3 scripts/run_official_server_oracle.py \
  --server cache/TrackmaniaServer-official-2026-05-15 \
  --map cache/trackmania-tas-upstream-036a65b/tools/testdata/map2.Map.Gbx \
  --ghost cache/trackmania-tas-upstream-036a65b/tools/testdata/human_22730.Ghost.Gbx \
  --ghost cache/trackmania-tas-upstream-036a65b/tools/testdata/human_23013.Ghost.Gbx \
  --output local/recon/my-new-official-oracle.json
```

The output file must be new. `ValidatedResult` is the answer from the server;
`DeclaredResult` is only what the ghost claims.

`scripts/run_official_fork_check.py` repeats the real-server fork-versus-full
control and writes a non-overwriting JSON report. It requires the built TAS
`fk` and `libforkshim.so` paths; use `--help` for its exact arguments.

## Original-instruction sphere ray

The installed Windows game's sphere ray dispatch entry is RVA `0x1a5580`.
The native original-instruction oracle and the C++ SDK kernel agreed on all
20,000 generated cases, including 4,068 hits, 2,479 inside/surface starts,
and 2,657 moving-sphere hits. The separate GPL Gearbox 0.35 fork integrates
the same branch into its `CollisionWorld::raycast` sphere dispatch; its Rust
probe matched classifications and defined output bits on those same cases.
The GPL patch identity is
`639e682e32aea5ccd750343a8c8517946263e0954851f58504d6157a16de3546`.
The official server was not used as a ray oracle, so the bit agreement is
specific to the tested original Windows instruction slice and defined input
domain. The native suite passed 42/42 tests and the separately installed
research SDK's external consumer linked and executed the new public ray API.

## Boundary

An exact independent full simulator and general RL training remain unqualified.
The official server supplies authentic whole-run physics, but a fast,
generally valid arbitrary-state stepping API, version matching to the
installed client, and broad replay/state validation are still missing.
The independent backend retains unsupported surface, collision, vehicle,
wake, constraint, and scheduling paths documented in the 0.34 audit. No
measured result here implies complete equivalence of those paths.
