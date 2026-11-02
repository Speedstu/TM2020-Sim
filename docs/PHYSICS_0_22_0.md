# Physics reconstruction 0.22.0

The SDK adds complete body-activation preparation and its model/flag predicate,
bringing the qualified public arithmetic count to 68. Each operation retains
20,000 original-code differential cases within documented domains. The release
also identifies the exact constructed vehicle interval and the correct
persistent-manager gravity field. Earlier step and context evidence remains in
[0.21.0](PHYSICS_0_21_0.md).

## Body flags and inverse mass

Complete `0x800c00` iterates 56-byte item records, looks up related item IDs,
updates selected bits in the low flag byte and writes only lane 3 of the
16-byte velocity coefficients. All other flag bits, record bytes and coefficient
lanes are preserved. Its complete callees are the fixed-model predicate
`0x7f4760` and mass sum `0x7f5130`.

The predicate reads model `+0x50` and source flag bit 3. The preparation stage
combines this result with source flag bits 0, 1 and 2, shape presence, the raw
shape tag byte at `+0x11`, and sleep word `+4`. Tag 7 selects a special branch;
this byte is distinct from the geometry shape-type enum. Inverse mass starts
as `1 / (model[+0x18] + item[+8])`, then native flag/tag branches can set it to
zero. The complete code clears item flag bit 3 and updates bits 0 through 5
according to the original branches.

The public API uses typed owned inputs and an explicit ID map. It validates
the whole batch, computes into staging storage and commits after success.
Mass components must be finite within +/-1e6 and their binary32 sum at least
1e-6. Zero/negative mass arithmetic outside that domain remains unsupported.
This stage does not execute later wake/sleep processing or guarantee that its
coefficients remain unchanged during the rest of a game step.

The native oracle executes all three complete original procedures with no
patches, skipped callees or game process access. Tests cover all 256 source
flag bytes, body counts zero through eight, both shape-tag branches, null
shapes, sleeping sentinels, arbitrary ID-map results, raw preserved coefficient
lanes, every item byte and immutable input arrays. Semantic tests check awake
and disabled cases, the tag-7 exception and rejection of a late invalid body
without partially changing earlier bodies.

## Exact constructed interval and gravity layout

Procedure `0x12e9ea0` explicitly constructs a three-word step descriptor:
an incoming integer timestamp, integer duration 10, and binary32 interval
`0x3c23d70b`, approximately 0.010000000707805157 seconds. The C++ literal `.01f`
has bits `0x3c23d70a`. The SDK exposes the exact recovered interval separately;
the standalone rigid-mesh demo now uses it and reports its bits.

Static instructions trace this descriptor through `0x7bd0e0`, `0x803920` and
`0x8025a0`. The force callback receives the float interval in its fourth argument
and the integer timestamp in its fifth. A parallel wide timestamp multiplies
the integer timestamp by 1,000,000. This establishes argument flow, not a stable
live address for an authoritative physics clock.

The persistent dyna manager and the core step's temporary stack view have
different layouts. Gravity at persistent `+0x25c` is copied into temporary
`+0x100`, then passed to the already recovered force/velocity kernel. Reading
persistent `+0x100` as gravity would be incorrect. The retained Solo capture
reads gravity `(0,-10,0)`, model mass coefficient 1500, item mass offset 0 and
gravity multiplier 3. These observations remain separate from a prediction of
the entire vehicle's acceleration.

The read-only probe checks live array counts and retains raw activation
inputs/outputs alongside parameter curves. It explicitly marks the snapshot
as not atomic with respect to a physics stage; later stages or observation
timing can explain differences from an isolated preparation call. Player
ownership and internal live clock remain unverified.

## Reproduction and limits

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The workflow runs native semantic tests, full original-code activation and step
oracles, static interval/layout evidence, prior physics and geometry checks,
standalone snapshot replay and the installed independent C++ consumer.

Complete wheel/drive/slip forces, wheel collision queries, all map shapes and
placements, general joint preparation, the sleep/wake scheduler and adaptive
contact reevaluation remain unfinished. The faithful autonomous Trackmania
vehicle simulator is not ready. No new learned driving improvement is claimed.
