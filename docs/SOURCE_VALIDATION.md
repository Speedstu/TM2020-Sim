# Source distribution validation — 2 November 2026

The source snapshot was built in a separate directory, with no installed
build products copied from the research workspace. Game assets and private
checkpoints are not included in this repository.

- Native C++ SDK, vector wrapper and trajectory controller: release build passed.
- Four autonomous native tests passed: controller, tick/failsafes, input statistics, action heads.
- Rust fast-training, speed-training and training-metadata: locked release builds passed.
- Rust SDK: locked library check passed.
- Fourteen autonomous Python regressions passed (style comparison, qualification gate, cleanup boundaries).
- Fresh simulator probe on an external Fall 2026-02 map: 30,000 ticks, about 51,268 ticks/s on the original research PC, without a planner or PPO collection. This is not training SPS.
- External original client replay of Fall 2026-02: recorded finish 21328 ms, simulated finish 21328 ms; difference zero.

The equal-timestamp visual-position RMSE is 0.579998 m. With the
previously declared fixed post-step +10 ms timestamp convention, maximum error
is 0.000878441 m. This convention is reported separately, not fitted to this
replay, and is not a complete internal-state equivalence proof. The test inputs
and private raw reports remain on the research PC. This repository does not
claim a new client run or a trained model available after cloning.

No game or training process was started. The GitHub workflow builds and checks
the autonomous native subset; it does not supply proprietary assets or run a bot.
