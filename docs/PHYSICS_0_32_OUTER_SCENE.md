# Research 0.32: original outer scene, synchronized source oracle

The original outer scene procedure **RVA `0x12e9ea0` now executes outside the
game from a stopped, process-bound numeric snapshot**. A 100-tick local Solo
reference agrees with the real game on every complete 88-byte rigid state and
24-byte force accumulator. This closes the previously missing outer-call
boundary for this captured scene. It does **not** complete world initialization,
all-action physics validation, or general race reinforcement learning.

SDK release remains **0.26.0**. This research uses our original-code backend and
our native PPO SDK. There is no Openplanet runtime dependency.

## Source identity and scene discovery

Pinned executable SHA256:
`3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda`.
The fresh process is PID 9696, creation FILETIME `134373027713357794`, module
base `0x7ff6abde0000`. Historical PID 424 references remain separate.

`reverse_scene_registry.py` pins the exact getter/lookup instructions and three
independent services. `tm2020_manager_discovery --discover-scene` validates the
manager/item/user/ID/configuration/registered-force links, locates the common
service registry, then verifies the scene root pointing to it. Observed indices
are dyna 12, collision 2, and force context 13. These are loaded service indices,
not guessed constant object offsets. `--rebind-scene` revalidates a known scene
in the same PID/creation/image cohort after an episode reset; it does not claim
another complete heap scan or authoritative player ownership.

Main evidence: `local/recon/scene-service-registry-instructions.json`,
`physics-scene-binding-9696-race-v1.json` and `...-race-v2.json`.

## Captured ABI, TLS and source synchronization

The observed six-argument call uses scene in RCX, the current clock word in EDX,
10 in R8D, mode 0 in R9D, null fifth argument, and sixth byte `0xfe`. The
caller is independently pinned at RVA `0x131378f`. Other input modes remain
unsupported by this snapshot format. All 16 GPRs, 16 XMM registers, MXCSR,
RFLAGS, actual source stack pointer, TEB, and initialized static TLS are
captured. The source module TLS index is 0 and template size is `0x11d8`.
The private copy replaces the stack return address with its own sentinel.

The bounded observer holds the entry debug event while the recorder copies
source pages. Windows suspends the debuggee's threads until
`ContinueDebugEvent`; see [Microsoft's debugger event loop documentation](https://learn.microsoft.com/en-us/windows/win32/debug/writing-the-debugger-s-main-loop).
Every source read verifies the observer lifetime, unsignaled release event and
lease deadline. Expired leases have no live-read fallback. Release or a maximum
60-second timeout resumes the game; debug registers are restored and the
debugger detaches. This freezes game private memory, not the entire OS or its
shared clock data. Discovery by itself is still a non-atomic read-only scan.

The default CMake build keeps live debugging **OFF**. Owned child-process tests
exercise observed arguments, platform entry/return, unchanged state during the
lease, external release, timeout and deliberate-abort cleanup. A separate
explicit research executable was used for the actual local Solo captures.
No executable instructions were patched and there were no explicit source
process memory writes. OS debugging state and hardware debug registers are
temporarily changed.

## Independent live physics comparison

`local/recon/outer-scene-9696-native-100-v1/result.json` records **100/100** live
rigid-state and force matches, consecutive 10-ms source clocks, no lease timeout
and clean detach. The coast vehicle is almost stationary but its rigid state
changes; this is not a repeated constant pose comparison. This is one Stadium
vehicle at the campaign start, not a validation of all driving/surface histories.
The offline strict replay also reproduces all captured pages and all 100 typed
frames from the numeric archive, without a game process.

`outer-scene-9696-native-gas-100-v1` additionally captures and strictly replays
100 privately accelerated ticks. Its real-game oracle remained on the source
coast controls, so the reported live state/force comparisons are **false** for
that counterfactual; it is not promoted as live action equivalence.

Platform timing is explicit: original execution reaches Windows
`QueryPerformanceCounter`. The observer records actual return values and call
ABI, but private discovery/replay currently uses the declared exploratory
counter seed. The real scheduler makes an additional clock call absent from the
serialized private runtime. The private runtime also sets worker count/foreign
waiters to zero, constructs owned job slots and selects supported platform
memory paths. Therefore the complete platform trace is not equivalent, even
where the independent physical result matches. No game physics callee is
replaced with a fabricated force or contact result.

## Original scene input decoder and guarded PPO

The scene overwrites direct writes to vehicle `+0x98/+0x9c/+0xa0`. Instruction
observations and the new 43-function bounded Ghidra slice identify the actual
scene decoder at **`0x12bce40`**. Its fifth stack argument is a typed object
descriptor (`0x0a020000`, selected vehicle pointer), RDX is previous input and
R8 is current input. Both observed records have low-nibble type 2. In the
current record, binary32 offsets **4, 8, 12** feed steering, drive and brake.
The original decoder performs its own clamping, flags and subsequent updates.

The owned action adapter validates that descriptor and record pair, writes
only those three fields in private emulated memory, and requires exactly one
selected decoder invocation per tick. Pedals are in [0,1], steering in [-1,1].
Unknown reads still stop execution. This is a recovered normalized scene-input
boundary; keyboard/gamepad decoding, authoritative player ownership and live
action equivalence are not established by it.

`outer-scene-9696-cohort-50-v2` captures coast, gas and a pedal/steering sweep
from the **same stopped initial state**. The contributor fixtures retain the
coast seed digest and snapshot cohort digest. Their input union adds 3,728
observed bytes; all three 50-tick references replay with every captured page
bit exact. No cross-process or unrelated-initial-state numeric merge is used.

The existing native PPO trainer now accepts this outer-scene backend with a
separate action-schema suffix, so old checkpoints cannot silently change input
boundaries. `outer-scene-ppo-v1` accepted 19 decisions / 95 original outer-scene
ticks, including one complete 50-tick episode. A second episode was truncated
when tuning field configuration `+0x1e08` was not captured at tick 50. That
decision was canceled, not learned from. Independent original-code replay
audits all 19 rewards, observations, trace hashes and bootstrap values.
The subsequent `outer-scene-9696-ppo-50-v1` cohort adds 1,880 observed bytes
for two PPO action histories from the same frozen coast state. In
`outer-scene-ppo-v2`, **20 decisions / 100 original outer-scene ticks** complete
two 50-tick episodes; native PPO performs one update / eight optimizer steps.
Independent replay audits every accepted state, reward and successor value.
Its merged fixture SHA-256 is
`679fb77df40fc61859862f96aca0f4d06a128f05f9d0718a931b51fda2cc99ed`.

Deterministic before/after evaluation reaches uncaptured geometry on different
ticks (47 and 46 accepted frames). The resulting unequal incomplete histories
cannot establish a policy improvement. Neutral controls complete their finite
reference; full throttle also reaches an uncaptured frontier. These explicit
failures remain in `local/recon/outer-scene-ppo-v2/evaluation.json`.

## Faster discovery, unchanged offline guard

`libtm2020_owned_unicorn_capture.dll` is a separate ephemeral discovery API.
It records exact read/write/executed-byte masks in C++ and validates executed
instructions against pinned code pages. It opens no game process itself.
The Python frozen-source reader remains the only source-page provider.
It is deliberately separate from `libtm2020_owned_unicorn_guard.dll`, which
continues to deny uncaptured offline inputs. Six owned microprogram tests
cover masks, page crossings, changed/unknown code, scratch exclusions and
callback lifetime cleanup. Discovery mode is never enabled in the replay guard.

The 100-tick coast capture executes 49,310,525 emulated instructions and
24,817,353 memory accesses in 27.01 seconds, versus roughly 4.5 seconds per
tick with the earlier Python discovery callbacks. Offline strict replay takes
17.44 seconds in this measured run. These are measurements from this host,
not a claim that the framework is the fastest available simulator.

## Remaining completion criteria

This original-code backend still starts from a captured world, needs the pinned local game and
OS images, and has a finite observed input working set. Complete cold map/world
initialization, arbitrary surfaces/vehicles/contacts/actions, the full scheduler
and platform environment, long episodes, checkpoints/finish race rewards,
held-out maps and general RL qualification remain unfinished for this backend.
Research 0.33 adds a distinct external engine with cold asset/map loading;
see [its evidence and limits](PHYSICS_0_33_HEADLESS_BACKEND.md). The existing live
SDK follower uses a different 8-observation/1-action interface; these
13-observation/3-action experimental policies are not deployed into it.

Negative experiments are retained: the first denied external clock boundary,
the initial serialization/index error, and an episode-reset binding failure.
None is counted as a passing simulation reference. Existing unrelated work and
the tracked deletion of `docs/VEHICLE_CONTROL_FIELDS_0_27.md` are preserved.
