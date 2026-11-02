# Internal pedal order and client transfer, 2026-10-31

The 03 wall collision and 06 checkpoint collision were caused by an actuation
stage mismatch. The old hook at RVA `0x841500` applied controls at wheel
spin/steering update. Sport preparation had already cached gas/brake booleans
at `0x851fa3` and `0x851fbb`. The simulator received the pedals before those
reads. Exact command readback at the old hook did not prove equivalent forces.

The runtime now applies commands at `input_overrides(ForceCtx*)`, RVA
`0x83de60`, before those cached reads. Engine input overrides still execute.
The 18 copied bytes consist of whole, independently relocatable instructions;
the executable SHA and exact entry bytes remain mandatory. Physics state,
gas/brake/steer, owner, race clock, map UID, heartbeat and stop guards remain
internal. No driving through a keyboard or controller is used.

The first early-hook build, `deployment-0.65`, completed 03 but crashed on 06.
It is explicitly rejected for subsequent deployment. Its C++ detour could
clobber volatile registers which this internal leaf's callers keep live:
Sport sets R10 before the call and uses it afterward. **Use 0.65b**. Its assembly
entry preserves the incoming volatile GPRs and XMM0..5 around the before
callback, restores them, and tail-calls the original trampoline. This preserves
the original function's register and memory effects. The owned PE test checks
R10/XMM2..5 preservation, command consumption, reset, invalid body neutralization
and shutdown while physics is paused. The original function runs once.

Controls in the new trace are read back after the before callback, before the
game's input overrides; a trace does not claim those overrides are bypassed.

## Actual client evidence

| Map | Runtime | Client finish | Respawns | Compared macro states | Maximum position error |
|---|---|---:|---:|---:|---:|
| 03 | initial early hook 0.65 | 18,915 ms | 0 | 1,893 | 0 m |
| 06 | register-preserving 0.65b | 25,997 ms | 0 | 2,601 | 0 m |

03 displayed TOP 2 WORLD. Both client times equal their original candidates'
nominal simulator times. The comparison replays recorded controls from a full
reset with frozen device-input history: **no launch velocity correction,
teleport, or midrace state alignment**. Position and velocity errors are zero
at the compared 100 Hz samples. This is evidence for these runs, not universal
accuracy across the campaign or a guarantee of every future attempt.

The separate launch uncertainty experiment from 0.63 remains an opt-in,
simulation-only diagnostic. It was not used to produce these client results.
The 0.62 steering experiments and failed 0.63/0.64 transfer searches have not
replaced the original candidates.

Evidence:

- `local/recon/internal-0.65/pedal-order-audit.json`
- `local/recon/internal-0.65/live03-original/verified-client.json`
- `local/recon/internal-0.65/live06-registers/verified-client.json`
- Each run retains `result.png`, the original trace, a copied autosave replay,
  replay metadata and its separate actuation audit.
- `local/recon/internal-0.65b-owned/owned-windows-final.json`: continuous,
  discrete17, discrete33 and hybrid pipeline parity; reset/stop tests.

Ordinary replays may record neutral device inputs under internal actuation.
Their header verifies map, declared time and zero respawns; their input stream
is not claimed to independently reproduce the internal bot's driving.

## User tests

`tm2020-campaign-play.service` now uses `deployment-0.65b` and a fresh session
directory, `local/recon/campaign-play-0.65/session`. Its prepared maps are
02, 03, 06, 08, 09, 12, 13, 15 and 17. On a prepared map it obtains a fresh
physical binding, then Delete starts another attempt; Escape stops that
map's bot. The bundle pins the corrected DLL hash. An observation from a
different DLL, map content or spawn cannot arm control.

The remaining prepared maps await the user's actual client trials. The user
asked to test them personally after the 06 fix. No whole-campaign client pass
or perfect reliability is claimed. Campaign search was paused for these tests
and subsequently resumed under [the 0.66 overnight configuration](OVERNIGHT_CAMPAIGN_0_66.md).
The old hourly monitor and old PPO services remain disabled.
