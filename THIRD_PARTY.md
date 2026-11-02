# Third-party sources

## Gearbox

- Project: https://github.com/Mergemat/gearbox
- Authors: Bagautdin Omarov and contributors
- Revision: `e0583ee55168e950a65a645778e591bd26b6a0f2`
- License: GPL-3.0-or-later; original text in `third_party/gearbox/LICENSE`
- Bundled location: `third_party/gearbox/`
- Portability edits: `third_party/gearbox/portability.json`

The Linux port retains upstream engine source. Changes concern headless asset
loading/dependencies and the Linux decompression adapter. The SDK and research
adapters do not claim authorship of Gearbox's reverse engineering.

## lzokay-native

- Project: https://github.com/arma-tools/lzokay-native-rs/
- Version: 0.1.0
- License: MIT; see `third_party/lzokay-native/LICENSE`
- Bundled location: `third_party/lzokay-native/`

This Rust decoder is used by the Windows perception adapter. Linux adapters
link the system LZO library; its implementation is not copied into this repo.

## Trackmania TAS compatibility tools

`integrations/tas-compat-0.35/` contains compatibility patches and attribution
for vjeux/trackmania-tas, MIT, revision
`036a65ba6aaef87b4579b8ee5a770729341dc572`. Its checkout and the official dedicated
server are not bundled. These historical oracle experiments need separate
preparation; they are not dependencies of the main Linux source build.

Other Cargo dependencies are declared and locked per adapter. Their licenses
remain their authors' licenses. Game Packs, executables, maps and replays are
external inputs, not part of this source distribution.
