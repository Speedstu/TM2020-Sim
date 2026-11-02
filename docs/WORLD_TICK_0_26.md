# Scene tick schedule evidence 0.26

The pinned Trackmania executable calls scene update routine `0x12e9ea0` from
`0x1312870` along two distinct paths. On the primary path, an incoming integer
timestamp must exceed the stored timestamp at context offset `0xe30`. The first
stored value is initialized to incoming minus 10 ms; a catch-up loop advances
it by 10 ms and calls the update for each tick through the incoming time. Its
receiver is loaded from caller offset `0xd78`. Static instruction checks
establish that this path supplies the tick timestamp in `EDX` and an integer
interval of 10 ms in `R8D`. A second path calls the same update with a marker
byte of `0xfe` and an interval derived from another loop counter plus 10; it is
kept separate from the primary simulation path in the evidence.

Before the timestamp dispatch, the caller walks a pointer array at receiver
offsets `0x660` and `0x668`. For every listed child it clears bit 0 and sets bit
1 in the word at child offset `0x1030`, then zeros the word at `0x1038`. These
are verified writes from the original instructions; their relationship to
vehicle activity, visibility, or physics ownership is still unknown.

The update routine also obtains one callback object from `0x12dd6d0`, computes
two membership results with `0x12e8650` and `0x12e85e0`, and passes those values
to the three-instruction leaf `0x722d90`. The leaf writes them as 32-bit words
at callback-object offsets `0x1268` and `0x126c`. The membership lists and the
callback object's class meaning have not been recovered, so these fields remain
unnamed in the SDK.

This narrows the upper-level schedule around the already qualified physics
entry `0x7bd0e0`. It does **not** prove that the static caller is the active
player's authoritative physics tick, identify a stable player object, decode
the per-frame control mapping, or establish a resettable world. The current
main-step backend still starts at `0x7bd0e0` with explicit sparse state inputs.

`reverse_world_tick.py` verifies the instruction bytes and assembly against the
SHA-pinned executable and writes `local/recon/scene-tick-schedule-evidence.json`.
It runs in the ordinary physics research workflow. For the surrounding call
graph and decompiler view, run `./scripts/run-ghidra-physics.ps1 -ResearchSet
world`. That isolated set starts at six explicit tick and update roots and
follows one level of direct calls through the full `.text` section (190 total
functions for this executable).
Ghidra operates on the existing local project; decompilation remains static
research evidence and does not claim correct C++ semantics.

Create the bounded evidence bundle with `python
scripts/snapshot_world_tick_evidence.py`. The bundle contains source evidence,
the 190 decompiler reports and their digest manifest; it excludes the game
binary and private process snapshots.
