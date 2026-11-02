# Research 0.34: geometry and wake handling

The simulator is **not complete or established as exact for all game states**.
This research extends the separately licensed Gearbox backend from 0.33. It
does not change the native SDK release number (0.26.0), and no Openplanet
runtime is needed for the bot. The Gearbox integration and changes are
GPL-3.0-or-later; see `integrations/gearbox-extensions/NOTICE` and `LICENSE`.

`scripts/prepare_gearbox_extensions.py` creates a separate source checkout
from upstream revision `e0583ee55168e950a65a645778e591bd26b6a0f2`, verifies
the upstream checkout is clean and validates each patch. Its identity is
`79a48d74d1a43c4998f5248a640bf5546392c6fd07d55ca7156cabb1ed27a419`.
The headless Python client requires the caller to explicitly acknowledge this
identity before accepting that patched engine. The changes implement two-sided
triangle raycasts and sphere/sphere contact dispatch. They retain the upstream
engine's remaining unsupported operations and explicit failures.

The original code was tested on owned synthetic memory using a SHA-pinned game
executable, with no running game process. The triangle ray, sphere pair, and
three-triangle mesh tests each contain 20,000 generated inputs. C++ and the
patched Rust engine match the tested defined output bits and hit decisions.
The mesh cases cover transforms, material skips, closest hits and equal-hit
ties. This establishes only those tested domains, not all collision shapes.

The original wake enqueue path and the SDK implementation match across
640,000 requests, including reverse handle mapping and duplicate suppression.
The active-list insertion instruction slice matches 20,000 synthetic cases:
the surrounding synchronization and wake consumer are not qualified.
The patched engine therefore still explicitly stops on pending wakes rather
than silently pretending they have been processed.

The extended engine deterministically resets and restores all four installed
Sport, Snow, Rally and Desert cars, and each finishes the test map. These runs
are engine integrity checks, not independent game-state bit-oracles for each
car. On the existing corpus, 21 eligible replays have exact recorded finish
times. Two additional examples remain ineligible due to an unsupported BayCar
and a partial input history. A timestamp hypothesis yields sub-millimetre
quantized visual residuals on the eligible data; it does not prove exact
physical state evolution.

Reproduce the bounded integration checks from the project root in PowerShell:

```powershell
./scripts/run-physics-extension-checks.ps1 -Output local/recon/my-extension-run
```

The output directory must be new. The runner builds the pinned Rust backend and
native SDK, executes the native suite and original-instruction geometry and
wake oracles, and checks reset, four cars, Gym and patch identity. The active
list slice is also runnable independently with `scripts/test_active_slot_slice.py`
and the installed original executable; invoke it with `--help` for arguments.
The test artifacts contain synthetic numeric values; installed game assets and
the executable are kept local.

Primary evidence is in `local/recon/physics-extension-final-v2/`,
`local/recon/extended-game-replays-v2/report.json`, and
`local/recon/physics-extensions-milestone-0.34-v2.json`. The audit identifies 88
remaining upstream `todo!` or `unimplemented!` sites; that count is not an
exhaustive specification of missing behavior. Full surface, collision,
vehicle, wake, constraint, scheduling and multi-map game-state equivalence,
and race-effective general RL, remain to be established independently.
