# Portable nested-record control guard 0.29

Three complete original procedures now have portable C++ counterparts:
`0x83dd60` selects a nested record value, `0x83dd90` computes a binary gate,
and `0x83de60` updates vehicle scalars `+0x98` / `+0x9c`.
The native differential executes the unchanged original instructions and their
quaternion-transform callee `0x1955c0` in an owned process. All three operations
match bit-for-bit on **20,000 generated cases each**. Every byte of the
`0x1e00`-byte vehicle buffer and `0x80`-byte context is checked after the full
update, including unrelated randomized bytes. No game process is opened.

The selected value is the signed short at record `+0x4e8` when nonzero,
otherwise binary32 `+0xf4`. The gate compares that value against the third
component of vector `+0x7c` rotated by the conjugate of the scalar-first
quaternion at `+0x60`; the output is exactly positive zero or one.

The complete update preserves scalar `+0x98` if both candidate values are zero.
It clears `+0x9c` when either record flag word at `+0xf0` / `+0x4ec` has bit 2
set, unless either word's low two bits equal 2. Flag bit `0x400` additionally
clears the relevant pedal scalar outside the signed-short limit.

The crucial layout alias is **record `+0x4ec` = vehicle `+0x176c`**;
record `+0x4ea` is vehicle `+0x176a`. The guard and nested flags cannot be
independent fields. The signed-short minimum `-32768` widens before absolute
value, yielding the exactly representable bound 32768.

The generated domain includes all 64 low flag-pair combinations, signed-short
extrema, zero/nonzero priority selection, positive/negative zero, subnormals,
quaternion transforms and exact threshold equality. Used floats must be finite
within +/-10000; quaternion normalization is not imposed because the original
routine does not normalize. Invalid portable inputs throw before state changes.
No claim is made for NaN/infinite inputs or larger floating-point domains.

## Corrected steering source

Instruction-level review corrects the earlier 0.28 interpretation:
`0x841500` passes `+0x98` / `+0x9c` to `0x8447b0`, then reads **vehicle `+0xa0`**
at `0x8416da` for the steering slew into `+0x1430`. This does not show two
different vehicle layouts. The default snapshot path confirms the same three
command fields: vehicle `+0xa0`, `+0x98`, `+0x9c` feed snapshot steering, gas,
and brake respectively. Special vehicle variants can override the snapshot.

The additional `inputsource` Ghidra slice contains 56 bounded decompilations.
Callers `0x71f8c0`, `0x12e8a80` and `0x13205e0` use lookup `0x1467ca0` for
different record sizes and object-state destinations. Its vehicle binding and
`0x878`-byte copy are therefore documented as a **generic state-record path**;
they do not establish the raw keyboard/gamepad source.

## Reproduce and remaining scope

```powershell
./scripts/run-control-guard-checks.ps1
./scripts/run-ghidra-physics.ps1 -ResearchSet inputsource
```

Sources: `native/include/tm2020/recovered_control_guard.hpp`,
`native/src/recovered_control_guard.cpp`, `native/tests/control_guard_oracle.cpp`.
Report: `local/recon/control-guard-oracle.json`. The SDK header is installed by
CMake. These operations can run without the game executable after compilation;
the independent original-instruction differential requires the pinned file.

This closes one complete internal guard branch. Raw action-event decoding,
general initialization/reset, track-wide collision coverage, long trajectories
and end-to-end RL fidelity remain unqualified. The 100-tick original-code
counterfactual is documented separately in `PHYSICS_0_28_COUNTERFACTUAL.md`.

## Physical response through the steering command

`replay_original_step.py --scenario-steering-command` now writes `+0xa0`,
letting the original procedure compute its own `+0x1430` steering state.
The native format version 6 carries this command offset explicitly; versions
3/4/5 remain readable and were checked again against their retained traces.
The runner rejects other version-6 offsets and overrides outside owned pages.

With `[0.5,0,0]` for 50 ticks, followed by `[0.5,0,0.15]` for 50 ticks,
the original rigid trajectory first changes at **tick 51**. All 100 frames
match between Unicorn and native execution. The rigid record differs on the
last 50 frames (2,223 changed bytes across those frames); maximum positional
separation from baseline is **0.000771145 m**, and maximum linear-velocity
separation is **0.00333604** in the game's state units. This is a small but
measured physical response in this frozen scenario, not general driving
qualification. The retained accumulator is unchanged at the end-of-step
observation boundary; that does not measure all intermediate applied forces.

`audit_original_step_control_response.py` now checks rigid and internal records
separately. It rejects a required physical-response claim when only control
bytes change. The historical `+0x1430` override produced no rigid divergence;
that earlier interpretation is corrected in the 0.28 report.

A pedal pulse trial (`[1,0,0]`, `[0,1,0]`, `[0,0,0]`, `[1,0,0]`, 25 ticks each)
exposed missing working-set data. The first missing byte was a file-backed
binary32 `-100` constant at RVA `0x1d1fec0`. An explicit four-byte `.rdata`
extension, verified against the pinned image, advanced the trial to a missing
dynamic tuning read in `0x8447b0`. **The pedal trial failed and has no native
qualification.** Unknown heap values were not supplied. A fresh source capture
covering those branches is required to extend that domain.

The constant-extension tool records file provenance separately from live
capture. The shared verifier rejects writable/executable sections, changed
constant values, unobserved masks, altered expected values and overlaps.
No new source game process was available during this continuation.
