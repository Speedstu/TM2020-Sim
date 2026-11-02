# Original force worker backend 0.24.0

The complete original Stadium force procedure **RVA `0x851f00`** now runs
offline in both Unicorn and an owned native Windows x64 process. Eight frozen
numeric inputs produce bit-identical complete data pages in both executors.
Each native comparison repeats the same input 10,000 times; this is **eight
independent frozen inputs**, not 80,000 independent physical situations.

The [0.23.0 report](PHYSICS_0_23_0.md) retains qualification of the **72 portable
arithmetic operations**. This release adds an original-code research backend,
not another portable physics operation and not a complete faithful simulator.

## Captured boundary and provenance

The read-only capture validates process creation time, executable path and
SHA-256, loaded PE headers, typed manager spans, item ID, registered callback
and context backlink. It executes the original enclosing callback only until
entry to `0x851f00`, then selects that complete worker as the boundary. Its
normal return goes to an owned sentinel. No original instruction is patched,
and no callee inside the selected worker is skipped. The enclosing callback
after the worker is outside this qualification.

The worker's Windows x64 arguments are a wide integer timestamp in RCX,
binary32 interval in XMM1, an 88-byte context in R8, and the captured opaque R9
value. The constructed interval is exactly `0x3c23d70b`. The context includes
the force owner, vehicle, item ID, timestamp, interval, position-related vector,
linear/angular velocities and tuning pointers. Capture retains eight inputs:
the observed state and owned-copy acceleration, left steering, braking/right
steering, reverse, sliding, idle acceleration and coasting/right steering.
Only copied numeric inputs are changed; the game is never modified by this tool.

Data reads occur while the game runs. These are **not atomic live snapshots**.
The typed object binding is checked again after capture. Player ownership and
the authoritative live physics clock remain unverified. A fixture is an
explicit frozen research input, not proof of matching a live trajectory.

## Sparse fixture and independent execution

`scripts/capture_force_worker.py` retains only source bytes actually accessed
by the complete worker, marking each with a per-byte mask. All other bytes
are zeroed. Fixtures contain code-page RVAs and the executable digest, **no
original instruction bytes or unfiltered heap pages**. Private `.tmforce`
files stay under ignored `local/` and are excluded from source/evidence ZIPs.
The evidence archives retain their SHA-256, bounds and qualification reports.

V2 starts with `TMFWFX2\0`, little-endian version 2 and the 32-byte executable
digest. Next are image base, image extent, code/data counts, context size,
worker ABI inputs, context bytes and code RVAs. Each data record holds its
page address, 4,096 mask bytes, 4,096 initial bytes and 4,096 expected bytes.
The parser rejects stale builds, invalid extents, duplicate pages, synthetic
memory collisions, invalid masks, nonzero unaccessed bytes and trailing data.

`scripts/replay_force_worker.py` opens only the executable and fixture files.
It reconstructs ordinary `.text` pages from the digest-pinned original file,
supplies synthetic stack/TLS storage and bounds every data access against the
captured masks. All complete data pages must equal expected bytes, including
zeros outside the masks. The recorded eight inputs pass this check.

`tm2020_force_worker_native.exe` independently executes the same complete
original worker. It reserves its own address ranges, maps original code RX
and numeric data RW, and refuses address collisions. Its loader-owned TLS
template provides the profiler's normal null branch; no TEB or GS-base write
is used. Each repetition restores and compares every complete captured data
page. The report measures calls per second including restoration/comparison.
The retained runs were around 100,000 calls/s on this machine. This measures
one frozen force call, **not full simulation steps or RL throughput**.

## Reproduce

The retained local qualification requires the unchanged original executable
and the eight private fixtures already captured on this workstation:

```powershell
./scripts/run-force-worker-checks.ps1
```

Capture a new versioned folder using a current manifest and independently
validated manager/module addresses. Existing captures are never overwritten:

```powershell
python scripts/capture_force_worker.py `
  --exe D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe `
  --manifest local/recon/live-cpp-26616-v3.txt `
  --base 0x7ff626360000 --manager 0x20c24d410c0 `
  --output local/recon/force-worker-fixtures-new `
  --report local/recon/force-worker-capture-new.json
```

Those addresses are specific to the retained session and must not be reused
after a process restart. A new source checkout without the private files can
build the runner and run the fixture parser CTest, but cannot reproduce the
recorded worker inputs from archive metadata alone. The native runner uses
trusted local fixtures; mask-enforced Unicorn replay precedes native calls.

## Full-step investigation

Owned-copy execution of `0x7bd0e0` reaches force calls and integration after
selecting an explicit dynamic-model input. The captured scene's normal model
is inactive/kinematic. A 16 MiB owned scratch arena supplies the ordinary
temporary-allocation path. The 88-byte island buffers are preallocated for
the 64-slot layout; original array capacity checks then need no heap growth.
Setting the owned CRT ISA-dispatch word to zero selects its original SSE
memory-copy implementation, which this emulator supports.

At the earlier allocation boundary `0x26757ba`, the containing page differs
from disk at 16 bytes; PE base relocation does not explain those differences.
A subsequent diagnostic verifies every executed instruction in nonordinary
code sections against the original file, permitting differing page data only
when it is not executed. This reaches the imported Windows function
`RtlEnterCriticalSection`. The original lock/unlock instructions also execute
under an owned synthetic thread context. The OS module has its own recorded
digest and instruction verification. An explicit syscall hook stops any
attempted OS syscall in this emulator.

With the required raw thread-context word initialized, the exploration reaches
the Windows heap allocator and its `RDPID` instruction, unsupported in this
emulator configuration. That instruction is not patched or skipped.
**No complete main-step return with active dynamics is qualified.**

Complete wheel/world collision queries, tire-force trajectory validation,
adaptive contact scheduling, wake/sleep and the authoritative player/tick
binding remain open. The offline force backend is a basis for those tasks;
the full headless Trackmania simulator and a stronger learned bot remain
unfinished.
