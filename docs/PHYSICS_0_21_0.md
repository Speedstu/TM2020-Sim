# Physics reconstruction 0.21.0

The SDK now contains 66 public arithmetic operations with 20,000 original-code
cases each within documented domains. The two additions recover the complete
step-parameter constructor and its exponent approximation. The live parameter
capture now verifies the registered force callback's context through a separate
pointer chain. Captured geometry evidence remains as described in
[0.20.0](PHYSICS_0_20_0.md).

## Complete step-parameter arithmetic

Constructor `0x8020a0` produces an 11-word, 44-byte record. It stores the
interval, reciprocal, gravity magnitude, selected solver configuration fields
and two caller-supplied opaque integer words. It computes a decay multiplier
using leaf `0x7f3ec0`, an engine-specific approximation of a power of two.
The port retains the original constants and separate binary32 operations:

```
exponent = ((interval / float_bits(0x3c23d70b))
            * float_bits(0xbcb6c518)) * float_bits(0x3fb8aa3b)
```

The helper clamps its exponent from below at -126, derives a fractional term
using truncation toward zero, evaluates its rational expression, converts that
result to an integer and interprets the lower 32 bits as binary32. Substituting
`std::exp2` would change results. Constants and both complete instruction
regions are retained in the static evidence report.

The public helper accepts finite exponents in [-200,100]. The constructor
accepts intervals in [1e-6,1] and finite gravity/configuration float components
within +/-1e6. Copied integer words retain all bits. Gravity squared magnitude
is nonnegative in this domain, so the original negative-square-root fallback
is unreachable. The native oracle executes complete unmodified original
procedures in an owned image and checks all output bytes, input preservation
and output guards. Boundary cases include signed zero, subnormal exponent,
integer boundaries and the lower clamp. A separate Unicorn/NumPy development
prototype also matched 20,000 cases before the native port was integrated.

This qualifies construction of a step's parameters. The scheduler that consumes
them, contact reevaluation between fractions, and the meanings of the two
opaque words remain separate work.

## Force callback context recovered

Vehicle registration puts a context at item-record `+0x10` and the force
callback at `+0x20`, in a 56-byte item array at the dyna manager's `+0x20`.
The callback is `0x8427d0`; its context's `+0x110` points back to that same
dyna manager. Static registration and item-construction instructions establish
this layout independently of the live addresses.

The updated native read-only parameter probe checks the callback against the
loaded module base, verifies the backlink, checks the vehicle ID round trip,
and finds the selected vehicle in the context's bounded vehicle list. It
rechecks bindings after capture. The observed context manages four entries.
The retained capture still marks player ownership and internal physics clock
as unverified; a force callback context is not sufficient to prove either.
The vehicle header and the first user-data word are not used as context roots.

## Reproduce

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The installed consumer uses the new constructor directly. The release workflow
checks the complete native oracle, static instruction evidence and retained
capture bindings alongside earlier geometry/solver tests. Fresh live capture
requires a fresh process-bound manifest; prior process addresses are disposable.

Complete tire/slip and drive forces, wheel collision queries, complete map
coverage, general joint preparation, sleeping and contact-interleaved adaptive
scheduling remain unfinished. The faithful autonomous Trackmania vehicle
simulator is not ready. This release claims no stronger learned driving policy.
