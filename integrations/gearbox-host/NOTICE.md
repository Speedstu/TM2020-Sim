# External engine integration

This standalone host uses [Gearbox](https://github.com/Mergemat/gearbox),
copyright Bagautdin Omarov and contributors, under GPL-3.0-or-later.
The dependency revision is `e0583ee55168e950a65a645778e591bd26b6a0f2`.
Its physics implementation and asset loader are upstream work, not newly
recovered code from this project. The host and its matching source are
distributed under GPL-3.0-or-later. Keep upstream notices and license with
redistributions. Game assets are read from the user's installation and are
not bundled.

The host communicates over local standard input/output. It does not use
Openplanet, open the game process, or inject into the game. Our native SDK's
PPO trainer and live runtime remain separate components.

Upstream simulation is a candidate backend with unsupported branches. Its
README's broad accuracy claims are not treated as an independent validation
of this project's installed game version. Exactness must be measured against
original-game references; unsupported branches return failures.
