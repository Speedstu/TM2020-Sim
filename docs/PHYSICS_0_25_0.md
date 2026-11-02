# Original main-step backend 0.25.0

The complete original main procedure **RVA `0x7bd0e0`** now runs outside the
game on **100 consecutive active steps**, plus a separate 100-step inactive
reference. Emulation and native execution agree at **every retained frame**.
The active reference checks the entire 88-byte rigid state and **1,211 observed
bytes per frame** across rigid, vehicle and force records. This includes the
vehicle fields accessed or updated by the recorded computation; it is not a
claim that every byte of the vehicle class has been decoded.

These are two frozen initial inputs with successive states, not 200 independent
randomized cases. The native tool requires neither a running game nor Python.
It requires the original executable, private numeric inputs and the captured
Windows module cohort. The **72 portable arithmetic operations** retain their
earlier 20,000-case qualifications. No additional portable physics operation is
claimed by executing the original program.

## Original physics and owned platform

The main call reaches the original force callback, wheel/vehicle computations,
collision queries, integration and constraint scheduling. Physics callees are
not replaced with approximations. The original ordinary `.text` instructions
come from the SHA-pinned file. Import-resolver sections also come from the file,
with the captured numeric cache slots they read. The emulated reference checks
every executed instruction against the file; a captured cache overlay must not
overlap any executed instruction byte.

The runtime uses explicit constructed inputs:

- Timing starts at integer 10,000 ms and advances by 10 ms. The binary32
  interval remains exactly `0x3c23d70b`; MXCSR is `0x1f80`.
- The active case clears model word `+0x50` and sets source flag bit 3 on the
  selected copied body, with initial world velocity `(0,0,30)`. The normal
  captured model is inactive/kinematic.
- Vehicle scalars `+0x98=1`, `+0x9c=0` and `+0x1430=0` are explicit raw input
  overrides. Their historical fixture name contains “throttle”; complete
  high-level pedal/controller mapping is not established by this reference.
- Original worker-count global RVA `0x2096af8` is zero. The condition-variable
  state at RVA `0x2096b08` starts empty. The original task machinery executes
  its callbacks with this serial runtime, without waking the source game's
  threads.
- Owned TLS supplies the raw thread context at `+0x148`, scratch arena at
  `+0x160`, and profiler null branch at `+0x1b8`. The 16 MiB scratch arena and
  64-slot 88-byte island-buffer layout are preallocated in owned storage.

The emulated platform adapter supplies allocation, reallocation, release,
allocation size and byte-copy/fill contracts. The normal Windows lock/unlock
instructions execute in the emulator; unexpected syscalls stop execution.
`kernel32!HeapFree` is a separately pinned import boundary.

The native adapter binds four allocation API entries with hardware execution
breakpoints on a **new thread in its own helper process**. It does not attach
to, patch or set breakpoints in Trackmania. The allocator uses bounded owned
storage; platform byte operations use the normal OS implementations. The
loader initializes its own TLS template and refuses address collisions. It
does not modify a TEB, GS base, Windows DLL instructions or the original game
file. The existing unqualified live-game debugger remains disabled.

Allocation addresses and platform state are outside the portable physics
claim. The report therefore keeps `wholeStepInstructionOracleQualified=false`,
while separately qualifying the complete observed physical traces.

## Private inputs and checks

`capture_original_step.py` validates source PID creation time, executable path,
digest, loaded headers, typed spans, item/callback binding and the binding again
after capture. It holds a read-only source handle and executes no code in the
game. Reads are demand-paged while the game runs: **this is not an atomic
application snapshot** and not a captured authoritative game tick.

The `.tmstep` archive contains page masks, only accessed/selected numeric bytes,
code-page RVAs, nonexecuted cache data and a masked physical output trace. It
contains no original executable instruction payload or unfiltered heap dump.
The codec checks digests, extents, masks, archive members, source/output
ownership and reference timing. Corruption tests run without a game install.
Private fixture files remain under ignored `local/`; release archives retain
their metadata and digests, not the input blobs.

`replay_original_step.py` reconstructs the input without opening a process. It
checks all captured accesses, every physical reference frame and every complete
final captured data page. `compile_original_step_fixture.py` produces the
bounded native input. `tm2020_original_step_native` independently checks every
observed byte of every frame, including all 88 rigid-state bytes. The active
car moves roughly 26 metres during the one-second reference.

The recorded native validation ran above 30,000 active steps/s on this machine,
including trace comparison and progress output. This short, single-body
reference excludes image loading and does not measure general RL throughput.

Entry observations also recover the schedule for this reference: 100 force
callbacks, 100 force/velocity integrations and 100 pose integrations, each
using interval bits `0x3c23d70b`. General linear/angular position passes each
enter 800 times; dynamic/static position passes each enter 400 times. These
are procedure-entry counts, which can include empty constraint spans. They
do not establish that every collision situation uses a single integration
interval or exercise every adaptive scheduling branch.

## Reproduce

```powershell
./scripts/run-original-step-checks.ps1
```

The command expects the retained private fixture cohort on this workstation.
A fresh source checkout can build the tools and run codec tests, but cannot
reconstruct private reference inputs from archive metadata. Capture a new
versioned cohort with a current manifest and independently checked addresses;
stale process identities and existing destinations are rejected. Native replay
also checks current OS DLL digests and captured import bases, so a changed OS
cohort or reboot can require recapture.

The complete release workflow defaults to rerunning the original differentials.
An optional fast path reuses 0.24.0 arithmetic evidence only after checking the
qualified archive digests, 124 unchanged implementation/test sources, 36
unchanged original-instruction reports and the **identical SDK library bytes**:

```powershell
./scripts/run-release-checks.ps1 -SkipLegacy -ReuseQualifiedPhysics
```

New main-step/native checks and native regression still run. The reuse flag and
source release are explicit in the resulting evidence; this does not relabel
the retained arithmetic tests as newly executed.

## Remaining scope

The sparse working set is qualified for these recorded inputs and horizon.
It does not establish arbitrary control changes, every map shape or complete
world coverage. Higher vehicle/controller phases, complete initialization,
long episodes, the authoritative player/tick binding and a general resettable
training environment remain open. The main-step tool is a reference backend;
**the full faithful headless Trackmania simulator is still unqualified**.

The injected bot's prior 24.114 s gold finish and two real PPO updates remain
historical results. This release does not claim a stronger learned policy.
