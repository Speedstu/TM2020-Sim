# Physics reconstruction 0.17.0

**62 public arithmetic operations pass 20,000 original-instruction cases
each within documented domains.** The four new operations recover the complete
wheel material aggregator, direction-factor update, vertical-velocity response
and engine fast sine/cosine. These supply material response inputs to vehicle
forces; they do not complete the tire-force or autonomous car model.

## Four-wheel materials and curves

The oracle executes complete `0x845b60`, including `0x845880`, native curve
interpolation, quaternion rotation, material classification, integer rounding
and rigid-state lookup. No instructions or callees are skipped or patched.
Synthetic caller-owned material records and game-context arrays supply inputs.
Every defined output byte is compared across 20,000 cases.

Each contacting wheel reads a material pointer from manager `+0x6b8` using
wheel byte `+0x40`. Runtime flag `0x1faa04c` remaps material 14 to 0 for record
lookup. Contact word `+0x34` is an integer: `0x80000000` is also active.

The aggregate holds ten floats, an integer, three more floats and flags.
Source material `+0x40` and output `+0x28` are integers, not floats. Averaging
rounds the integer to nearest with halfway cases away from zero; fewer than
three contacts with nonzero source integer force that output to zero. Source
`+0x34/+0x38` contribute only when positive, otherwise their aggregate retains
the native `-1` sentinel. Flags start at 1 and are intersected. The optional
contact kind is assigned in wheel order, so the final contacting wheel wins;
classification uses its original material ID even when lookup remaps it.

Contact normals are summed, normalized or replaced by `(0,1,0)` when degenerate,
then transformed using the original rigid-state matrix arithmetic. Aggregate
float `+4`, when above 1.5, blends from 1.5 to its material value between
90 and 120 km/h. Its speed input is the magnitude of stored velocity `+0x12fc`.

The four response lanes evaluate **independent** material curves at offsets
`+0x128`, `+0x88`, `+0x178` and `+0x1c8`, then divide by contact count. The first
two use caller vector Z times 3.6; the third uses scalar `+0x13a4`; the fourth
uses one minus the normalized velocity/rotated-forward dot product. With no
contacts the response is exactly `(1,1,1,0)`. The oracle varies all four curves
independently, including empty, linear, step, smoothstep and Hermite cases.

## Direction and vertical response

Complete `0x84f1a0` rotates stored velocity by the conjugate quaternion and
normalizes it when the native squared-length test succeeds. Vehicle scalar
`+0x98` selects a direction-derived factor or recovery using unsigned duration
`+0x324`, interval and previous `+0x14bc`. The floor comes from `+0x328`, and
the upper clamp is 1. Raw offsets remain in API names where higher-level
gameplay semantics have not been established.

Complete `0x8456b0` derives two responses from `abs(vY / length(v))`. Each
threshold pair (`+0x19e4/+0x19e8`, `+0x19ec/+0x19f0`) selects zero, one or
`1-fastCos(((ratio-begin)/(end-begin))*pi*0.5)`. Near-zero velocity retains
both responses at 1. Qualified thresholds satisfy `0<=begin<end<=1`.

The fast trigonometric leaf `0x18ce30..0x18cf62` uses binary32 turn reduction,
quadrant folding and polynomial evaluation. Its exact constants and rounding
are retained for finite arguments with absolute value at most 1,000,000. This
is a distinct implementation from the scalar runtime trigonometry used by
contact position corrections; that earlier angular-domain restriction remains.

## Validation and remaining work

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The installable header is `tm2020/recovered_wheel_material.hpp`. Native semantic
tests cover independent curve lanes, optional-field sentinels, speed blending,
integer/flag behavior, last-contact classification, remapping, signed zero and
rejected input domains. The external installed consumer calls the four APIs.
The workflow also retains all previous original-instruction differentials,
native tests, PPO/BC and Rust/ABI checks. No new in-game race is claimed.

Material IDs are qualified from 0 through 79, with explicit caller tuning and
curves. Effective race records still need capture. Complete tire/slip/drive
forces, Stadium geometry, joint construction, sleeping, adaptive contact
reevaluation and held-out full-trajectory validation remain unfinished. The
autonomous rigid mesh world from [0.16.0](PHYSICS_0_16_0.md) remains available;
the complete faithful Trackmania vehicle simulator remains unqualified.
