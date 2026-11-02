# Physics reconstruction 0.18.0

**64 public arithmetic operations pass 20,000 original-instruction cases
each within documented domains.** This release adds complete `0x846010`
vehicle resistance and complete `0x7bdf40` local torque application. Their
original callees execute normally in the differential oracle, including the
native force accumulator and wake helper with wake queue disabled.

## Resistance, braking and air damping

The recovered routine contains three sequential contributions. Its initial
gate skips variants 4/5 when raw vehicle word `+0x138c` is nonzero and all
four contact words are zero. The contact test uses integer wheel `+0x34`.

Constant and linear resistance depend on the raw status words at vehicle
`+0x176c` and `+0x1370`, scalar `+0x98` or `+0x9c` selected by `+0x1600`,
and the supplied velocity. **The status object's base word at `+0x1280`
does not supply those state bits.** Normalized constant resistance uses config
`+0x17a8`; the linear term uses `+0x17ac` and is omitted in state 1. Their
combined force is multiplied by curve `+0x9f8`, clamped manager `+0xa5c`
times vehicle `+0x1760`, vehicle `+0x1c44` and one minus the caller blend.

The next contribution depends on a **signed** variant comparison against 4.
Below 4, raw vehicle word `+0x1408` enables braking with a step-only evaluator
of curve `+0x17b8`, independently of that curve's interpolation flags. For
other variants, this word writes the current uint32 tick into `+0x1410`;
subsequent calls use unsigned timer comparisons and duration `+0x1bdc`.
That branch uses normalized velocity and the ordinary curve evaluator.
The oracle includes future timer values and ticks at 0, 1, `0x7fffffff`,
`0xfffffffe` and `0xffffffff`.

With no wheel contact, the routine also damps stored angular velocity
`+0x1308`. It evaluates curve `+0x2060` at squared angular speed, builds the
native negative scaled vector, rotates it by conjugate quaternion `+0x12e0`,
then applies the body's matrix through `0x7bdf40`. Both rotations and their
rounding remain in the port. The torque helper has row-specific addition order
and changes only the angular force accumulator.

## Validation and scope

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The oracle compares all 7,424 bytes of the native vehicle fixture, including
preservation of every field except the timer, and the selected force/torque
accumulator. It tests variant selectors -1 through 7, both status words,
integer contacts including `0x80000000`, airborne and grounded cases,
independent curves, near-zero and signed-zero velocities and timer boundaries.
Native semantic tests verify force magnitudes, angular damping, early skip,
dual status selection and rejection after a timer update without caller mutation.
The external installed C++ consumer calls both new APIs.

The public header is `tm2020/recovered_resistance.hpp`. Inputs and outputs
must remain finite within the documented bounded domain; quaternion components
are bounded by 16. Tuning is explicit. These operations add no sleeping or wake
queue implementation and do not complete tire traction, wheel collision queries,
effective race records, Stadium geometry or adaptive contact reevaluation.
The complete faithful Trackmania vehicle simulator remains unfinished.
See [0.17.0](PHYSICS_0_17_0.md) for material response and preceding evidence.
