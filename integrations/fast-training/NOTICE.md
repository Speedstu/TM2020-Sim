# Headless training integration

This integration uses Gearbox by Bagautdin Omarov and contributors,
https://github.com/Mergemat/gearbox at revision
`e0583ee55168e950a65a645778e591bd26b6a0f2`, licensed GPL-3.0-or-later.
Its engine and asset decoding are upstream reverse engineering work.
This project does not claim to have independently recovered that engine.

The Rust adapter, Linux LZO adapter, native vector collector and imitation
initializer in this directory are GPL-3.0-or-later. Retain upstream copyright
notices, the license and corresponding sources when redistributing builds.
The bundled upstream sources are in `third_party/gearbox`; the portability
change inventory is `third_party/gearbox/portability.json`. The historical
preparation script is retained in `scripts/prepare_fast_training.py`.

The 121 upstream engine source files are copied unchanged. Portability changes
affect dependency versions, cache serialization, the safe system LZO decoder
and omission of image exporters. There is no replacement vehicle physics.
Game Packs, maps and replays are read from the local installation/research
corpus; proprietary Packs are not part of the source distribution.

The policy receives route geometry and current simulated vehicle state.
Demonstration inputs construct complete reset snapshots and optional offline
imitation targets. Future demonstration controls are not policy observations.
Evaluations start from race time zero. A route-assisted policy on one course
does not establish performance on unseen maps or global physics equivalence.
