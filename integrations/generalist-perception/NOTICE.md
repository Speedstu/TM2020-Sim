# Generalist perception prototype

GPL-3.0-or-later. Uses Gearbox by Bagautdin Omarov and contributors at revision
`e0583ee55168e950a65a645778e591bd26b6a0f2`. Keep its license and corresponding
source with redistributions; see `../fast-training/NOTICE.md` and `LICENSE`.

This crate opens the installed map and Packs without an external replay. It
queries static collision geometry and map waypoint triggers in the vehicle's
local frame. It does not infer a complete route, train a policy, or establish
parity with live observations from the existing Windows SDK runtime.

The author ghost embedded in a GBX may still be parsed by the upstream map
loader. No expert trajectory, future control or author time enters the emitted
observation. Clone-enabled maps may legitimately use their embedded ghost as
dynamic world content; this prototype does not yet expose moving obstacles.
