# Trackmania 2020 – real solo-game memory experiments (21 October 2026)

Everything in this experiment is on H:\Projects\Trackmania2020-RE.
Trackmania.exe stays unmodified on D: and is running in Solo,
Autumn 2026 - Track 01. User reached the start; speed display=000.

## Verified genuine-game results

1. Game launched via Steam after Ubisoft sign-in, exact binary:
   Trackmania.exe v2026.2.2.1751. Its SHA-256 fingerprint is saved in
   local/recon/real-game-session-20261021.json.
2. Native tm2020_game_probe.exe --probe: read-only ReadProcessMemory
   verifies loaded PE header and strings while the car is visible at race
   start. This does NOT expose physics vectors or 100Hz tick callbacks.
3. Historical Polybagel/TM2020-TAS (MIT) car location chain:
   root RVA 0x1E340F8, offsets [0x2A8,0x1C0,0x30,0x160,0x198,0xD20,0x2C].
   Its first pointer read resolves to 0x1E340C80156484E, which is invalid
   in this 2026 build. REJECTED. No pointer gets used by the live bot SDK.
4. Static xrefs to engine strings were verified with locally installed
   Capstone x86-64: scripts/analyze_vehicle_xrefs.py found 86 verified
   references, including 4 for CSceneVehicleVis, 18 for CPlugVehicle,
   2 for InputSteer, 1 for GroundContact and 2 for ReactorBoost.
   File: local/recon/disassembled-string-xrefs.json.
   These are instruction references to class names, not vehicle pointers.
5. Native tm2020_live_vector_probe.exe --capture scans bounded private
   readable/writable regions and saves only float3 numeric candidates.
   Scan budget 768 MiB. Initial stationary capture: 943,342 plausible
   triples. Second stationary capture: 943,554 triples. Of these, 709
   changed while the car stayed still, indicating background noise.
   Only numeric triplets were preserved; no raw process pages/credentials.
6. The three-snapshot candidate ranker has a passing synthetic unit test
   (scripts/rank_live_motion_candidates.py --selftest).
   No candidate is yet independently validated as vehicle telemetry.
7. A standard Windows 650ms Up-arrow SendInput was issued to the focused
   window but in-game speed remained 000; synthetic acceleration not
   confirmed. No further input injection attempts.
8. No native C++ bot DLL has been injected into Trackmania, and exact
   vehicle pointers / 100Hz game physics are NOT reconstructed.

## Next physical step (needs user physical keyboard action)

In SAME Trackmania session, press and hold the physical Up arrow for about
two seconds in the local Solo race. Release and do not reset/relaunch.
Say "j'ai avancé". Then run:

    & 'H:\Projects\Trackmania2020-RE\scripts\finish_live_motion_probe.ps1'

This captures another read-only 768 MiB candidate snapshot and selects
fields stable across baseline samples but changed after genuine car
movement. Results are hypotheses, not yet verified offsets; independent
visual/replay and repeated reset/motion checks must follow.

The existing experimental sandbox is NOT faithful Trackmania physics.
Future successful motion-vector correlation must not be mistaken for
full 100Hz game state or a ready headless RL training environment.

Source for historic pointer chain (read-only reference):
https://github.com/Polybagel/TM2020-TAS
Cloned on H:\Projects\Trackmania2020-RE\references\TM2020-TAS.
