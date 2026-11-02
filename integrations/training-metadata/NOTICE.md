This integration is licensed under GPL-3.0-or-later. It uses Gearbox revision
 e0583ee55168e950a65a645778e591bd26b6a0f2, with the Linux dependency preparation
documented in ../fast-training/NOTICE.md and scripts/prepare_fast_training.py.
The Gearbox engine physics source files are unchanged. This is not a claim to
have independently reverse engineered every Trackmania mechanic.

The native PPO and Windows SDK adapters are built from the corresponding sources
in this repository. Map/game assets remain in the user's installed game and are
not redistributed. The runtime includes no automatic DllMain worker or hooks;
it runs only after an explicit loader call.
