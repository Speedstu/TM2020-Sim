# Physics reconstruction 0.15.0

**52 public arithmetic operations pass 20,000 original-instruction cases
each, within documented domains.** This release adds the complete physical
wheel update at `0x844130` and spin update at `0x843190`. They connect wheel
rotation, angle/material curves and suspension state to the previously
recovered mode-2 spring force/torque helper. The autonomous rigid collision
world from [0.14.0](PHYSICS_0_14_0.md) remains available.

The full faithful Trackmania car world is still unfinished. These methods do
not perform the wheel collision query or reconstruct every tire/drive force,
effective race curve, Stadium asset or adaptive contact-interleaved pose step.
No new in-game training/strength result is claimed.

## Wheel phase, angle and suspension state

The entire original `0x844130` executes in an owned process. Its curve helper,
finite float remainder helper and identity-matrix stores execute normally.
The executable remains unchanged, pinned to SHA-256
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.
The oracle compares every byte of the 184-byte native wheel record and the
48-byte pose, including preservation of fields that are not updated. It also
checks 10,000 native rendering-cache copies. SDK callers own that cache;
`update_wheel_kinematics` returns its physical state and pose directly.

Recovered wheel offsets are length at 0, speed at 4, pending compression at 8,
spin rate at `0x1c`, integer contact word at `0x34`, material byte at `0x40`,
normal at `0x44`, phase at `0x78`, angle at `0x7c` and target angle at `0x80`.
The phase period is **1608.4954833984375 in the stored units**, not `2*pi`.
Wrapping preserves the native remainder/addition order and signed-zero cases.
The normal is normalized only above the native approximately `1e-10` squared
threshold and below `FLT_MAX`; otherwise it remains unchanged.

Angle calculation uses the verified model word at `+4`, caller speed, raw
vehicle steering/blend values and explicit global/per-material curves.
Configuration `+0x1a08` is **the point count of the curve starting at
`+0x19f8`**, not an independent enable flag. Airborne material angle lookup is
gated by that global count, while the contact/material branch calls its
material curve unconditionally. The material-14-to-0 runtime remap is covered.
The current angle slews toward the target using the original branch-specific
rate and operation order.

Suspension mode 2, after subtracting pending compression, uses:

```text
adjusted = oldLength - pendingCompression
length = adjusted + ((restLength - adjusted) * dt) * relaxation
speed = (length - oldLength) / dt
poseY = modelPointY + (poseOffset - length)
```

Mode 3 clamps adjusted length nonnegative, clamps its ratio to rest length
into `[0,1]`, updates speed using `restLength * dt`, then adds its relaxation
term. Its pose evaluation is `(-length) + (poseOffset + modelPointY)`.
Reassociating those additions changes a bit in some cases; the port retains
the original order. Modes 2/3 reset pose rotation to identity. Other modes keep
the existing pose, while phase, normal and angle processing still occurs.
Pending compression is consumed by modes 2/3.

The oracle covers modes 0 through 4, empty/linear/step/smoothstep/Hermite
curves, material selection, zero and near-threshold normals, negative/positive
wrapping, exact-period boundaries, signed zeros and integer contact words.
Intervals must be positive and at most one second. Mode 3 requires positive
rest length; an active angle-blend denominator must be nonzero. Invalid late
inputs leave both caller state and pose intact.

## Wheel spin

The entire chained-unwind body of `0x843190` also passes 20,000 cases. It updates
only native wheel field `+0x1c`; the oracle checks preservation of the full
vehicle buffer around the selected wheel. The engine calls this before
`0x844130` in its wheel update sequence.

The port retains unsigned timer comparison and the `0xffffffff` sentinel,
airborne scalar gates and idle decay `0.9950000047683716`, special material IDs
74/3/21, raw lower-two-bit state checks, radius division, rate/target clamping,
and contact idle relaxation `0.949999988079071`. The contact blend denominator
base is **1.0000100135803223**. Sign-bit decisions preserve negative zero.
Field names keep verified offsets when full gameplay meaning is not established.

Caller tuning and current scalar/state values are explicit. Radius must be
positive and an active blend denominator nonzero. This operation does not
create a longitudinal tire-force model by itself.

## Reproduce and use

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy
```

The installed C++ consumer calls both wheel updates, alongside the recovered
collision world. Native semantic tests check the global-count/material-curve
distinction, mode-2 spring force/torque composition, mode-3 compression/speed,
phase wrapping, angle slew, timer/state branches and transactional errors.
Previous original-instruction, native PPO/BC, C/Rust ABI, reflection/atlas and
installation checks remain in the release workflow. Omit `-SkipLegacy` to
include the unchanged .NET suite. The new public header is
`native/include/tm2020/recovered_wheel.hpp`.
