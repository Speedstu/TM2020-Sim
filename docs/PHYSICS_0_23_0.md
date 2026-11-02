# Physics reconstruction 0.23.0

Four complete procedures add engine inverse sine/cosine, speed-dependent
steering angle and a surface-response scalar update. The SDK now qualifies 72
public arithmetic operations with 20,000 original-code cases each within
documented domains. Earlier activation, timing and gravity evidence is retained
in [0.22.0](PHYSICS_0_22_0.md).

## Inverse trigonometry and steering

Procedures `0x18d150` and `0x18d230` evaluate the engine's inverse-sine and
inverse-cosine approximations. Both use a degree-seven binary32 polynomial in
the absolute argument, multiplied by `sqrt(max(1-abs(x),0))`, followed by
different signed combinations with the stored half-pi/pi constants. The port
retains separate operations and exact constant bits. It does not substitute
the standard library's inverse-trig functions.

The qualified absolute argument limit is 100,000; the mathematical inverse-trig
domain is [-1,1]. Outside that mathematical domain, the original square-root
clamp and polynomial can produce signed zero. This behavior is preserved.
Native inverse sine of negative zero returns positive zero; inverse cosine at
the tested large positive boundary returns negative zero. Complete original
procedures, including all reachable branches in this domain, are executed in
an owned image without patching instructions or skipping callees.

Complete steering procedure `0x841b40` computes a denominator from the absolute
third velocity component, tuning `+0x180c` and tuning `+0x1808`. At or above
the native 1e-5 threshold, it evaluates the engine inverse sine of the
reciprocal. The output multiplies this angle by sign-flipped raw steering
`+0x1430`, unless bit 3 in either status word `+0x176c` or `+0x1370` disables
the output. The native order computes the angle before that status gate.

## Complete surface scalar update

Procedure `0x8465e0` changes only vehicle float `+0x13a4`. The code uses this
field in resistance and material-response curves elsewhere, but its precise
physical interpretation is not independently established. The API retains its
offset label.

The procedure returns without mutation if all four wheel contact words are
zero or vehicle word `+0x138c` is nonzero. Otherwise, it forms a decrement from
the material's integer duration, interval and an optional control/direction
term. A speed-dependent curve at configuration `+0x638` scales the decrement.
It subtracts the result from the old scalar, then clamps to [0,1]. Full native
curve interpolation executes in the oracle, including empty, step, smooth and
Hermite curves. This does not reconstruct the complete lateral/longitudinal
tire-force generator.

The native differential covers both complete inverse-trig procedures, steering
and scalar update on 20,000 cases each. It checks complete vehicle buffers,
read-only context/configuration buffers, steering output guards, status gates,
velocity thresholds, unsigned duration extremes, curve modes and signed zero.
Semantic tests verify endpoints, gates, recovery duration and transactional
rejection. The installed independent consumer calls all four public operations.

The read-only parameter probe also captures the two steering tuning words and
the recovery curve, increasing the retained configuration/material curve count
from 411 to 412. These records remain separate from synthetic oracle inputs
and from complete trajectory validation.

## Reproduce and remaining work

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The workflow rebuilds the SDK and runs native regression, full original-code
oracles, retained parameter/geometry audits and standalone snapshot replay.
The complete tire-force model, wheel collision queries, all map shapes and
placements, general joint preparation, wake/sleep processing and adaptive
contact reevaluation remain unfinished. The faithful autonomous Trackmania
vehicle simulator is not ready. No stronger learned driving policy is claimed.
