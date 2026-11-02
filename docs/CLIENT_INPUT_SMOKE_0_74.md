# Client replay input diagnostic, 2026-11-01

The user loaded Fall **2025**-01 instead of the Fall 2026-01 specialist map.
An initial observe-only run refused that map without applying driving commands.
A separate bounded diagnostic was then bound to the actual map UID
`oxH3JSoGHpDRAFLXaKq0BSRWHP6` and observed spawn (1296, 42.0043, 1168).

The diagnostic exercised the normal decoder with gas, brake and signed steering
at 100 Hz, then neutralized and detached. No trajectory champion drove this map.
300 consecutive input ticks at race times 0–2990 ms were verified at the paired
physical consumer. No non-neutral physical overwrite masked decoder output.

The client saved an original unfinished `.Replay.Gbx` through its own Save Replay
dialog. The independent Rust GBX reader found four attempts and exactly one
matching attempt. All 300 source commands, physical consumer commands and decoded
replay commands match bit for bit after float32 conversion and i8 decoding. The
comparison uses each group's declared time offset; no temporal shift was fitted.

| Race time | Gas | Brake | Signed i8 steer |
|---:|---:|---:|---:|
| 0 ms | 1 | 0 | +13 |
| 400 ms | 0 | 1 | -13 |
| 800 ms | 1 | 0 | -13 |
| 1200 ms | 0 | 1 | +13 |
| 2000 ms | 0 | 0 | 0 |

Replay SHA256:
`a7a00f62149eb7ec72f33a19a6a97c2c8f36d880508726c6e91f95623663a702`.
Runtime SHA256:
`f622e0de5782109e7a5f4bb136d8513695524792e3d9751ac776627ee26b2533`.

Evidence is in `local/recon/offline-human01-20261101/recording-smoke/`:
`client-original.Replay.Gbx`, `client-inputs.json`, `control/physics.csv`,
`client-replay-input-proof.json`, and `original-file-provenance.json`.
`scripts/verify_client_input_smoke.py` reproduces the checks without modifying
the replay. The saved replay is an unfinished diagnostic and includes other
attempts. This proves recording of the specified 3-second input window; it does
not prove a finish, human-like driving, full-run recorder parity, or performance
of the Fall 2026-01 champion in the client.

Ubisoft window recognition now verifies the live Trackmania process/title and
uses its window address instead of Steam's hardcoded window class. Proton SDK
staging resolves paths through the live process mount root when Flatpak-only
paths are not visible at the corresponding host location. Original game
identity, map and observed physical-owner checks remain active.

## Full Fall 2026-01 run

`local/recon/offline-human01-20261101/champion-trial-02/client-run-proof.json`
records a real client arrival in 19,995 ms, zero respawns, and checkpoints
5,345 / 11,758 / 15,238 / 19,995 ms. The original fresh client replay contains
2,000 input ticks. Normal-history simulation with its original seed 26769133
reaches the same 19,995 ms, with zero differences between every recorded action
and the retained hardcode's decision on that simulated state. The original
replay's input metrics pass both observed human ranges and common P10–P90 bands.
This does not prove visual indistinguishability or a current online rank.

The first full-run attempt uncovered a reset identity expiry at 3 seconds.
The corrected runtime commits the verified replacement vehicle when it binds,
while retaining physical-body and late-replacement checks. Native regressions
cover accepted identity at 25 seconds and refusal of a later foreign vehicle.

**Unresolved client cleanup:** the successful run's runtime could not acknowledge
neutralization after finish, because the physical tick/owner was gone. Its
stopped context and hook remain pinned. No further actuation should be started
in this client process; restart it before another test. This also prevented the
normal end-of-run CSV dump. The report therefore distinguishes original replay
and exact simulation/model parity from a complete live physical trace, which
is unavailable for this arrival. No cleanup-success or full live-trace claim is
made, and the retained production champion has not been replaced.
