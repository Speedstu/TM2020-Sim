# Physics reconstruction 0.16.0

**58 public arithmetic operations pass 20,000 original-instruction cases
each within documented domains.** Six new operations recover four complete
joint-position primitives, the eight-pass position-island loop and the
model-center frame shift. The autonomous rigid world now handles a nonzero
model center. The complete Trackmania vehicle simulator remains unfinished.

## Position constraints and scheduling

Complete original procedures `0x1955c0`, `0x7f63f0`, `0x7f6590` and
`0x7f6a50` execute unmodified in an owned process. Their ports respectively
rotate a vector by a quaternion, correct negative projection errors, correct
anchored projections and project relative orientation onto a quaternion axis.
Every byte of the rigid states is compared, including untouched fields.

Projection constraints split dynamic corrections equally. Anchored constraints
multiply A's local anchor by `0.949999988079071` before transforming it, and
multiply two-body correction by `0.1`. Fixed B receives the full correction.
These factors and evaluation order are retained rather than replaced by a
generic joint formula. The quaternion constraint preserves the rotation matrix
even when it changes the quaternion, matching the original procedure. Its
normalization fallback and sign selection are included.

The original loop `0x8033b2..0x80359a`, inside `0x8025a0`, runs all eight
passes for one island before advancing to the next island:

1. Dynamic quaternion-axis constraints, then static ones.
2. Dynamic anchored constraints, then static ones.
3. Dynamic projection constraints, then static ones.
4. Dynamic contact position constraints, then static ones.

An instruction emulator executes this bounded loop and all original callees
for 20,000 cases. Every call trace, full state array and prepared constraint
buffer is compared. Inputs cover zero through three islands, zero through four
iterations and populated/empty spans of every kind. The complete enclosing
step is **not** thereby qualified. Contact rotation retains the existing
scalar math dispatch and angular correction norm limit `1.57079625`.
Joint asset construction and preparation remain unfinished.

## Model origin versus center frame

Complete `0x7f8db0` adds or subtracts the rotated model center. The main step
integrates forces in the model-origin frame, adds `R * modelCenter`, runs
collision/velocity/pose/position solving, then subtracts the center transformed
by the **new** rotation. The collision reevaluation helper derives shape origin
from center-frame position using the same subtraction.

The original unrolled and tail paths pass 20,000 cases each in both sign modes,
with counts zero through twelve. Sign changes precede matrix multiplication;
reassociation or subtracting the final sum changes some results. Inverse shifts
need not cancel bit for bit because each stage rounds to binary32.

`RigidMeshWorld` now accepts an explicit `model_center`. Exposed states and
snapshots use the model-origin frame, while solvers use the center frame.
A free-spinning body with an offset center keeps that center stationary as
its model origin moves. Position solving uses the qualified pass order.
Geometry, force integration, snapshot replay and transactional rejection tests
also remain in the workflow. Tuning and geometry are caller supplied.

## Reproduce and limitations

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The installed C++ consumer calls all new APIs. Headers are
`recovered_joint_position.hpp` and `recovered_frames.hpp`. The workflow checks
native tests, original-instruction differentials, source/evidence hashes,
native PPO/BC, Rust bindings and independent SDK installation. Omit
`-SkipLegacy` to include the unchanged .NET suite.

The complete tire/slip/drive model, effective race curves, Stadium collision
assets, joint construction, sleeping and contact-interleaved adaptive stepping
still require work. The scalar math qualification does not cover the AVX math
path. No additional game race, improved learned policy or full original-step
fidelity is claimed. Earlier wheel and geometry evidence is retained in
[0.15.0](PHYSICS_0_15_0.md) and its linked reports.
