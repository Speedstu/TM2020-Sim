#!/usr/bin/env python3
"""Replay Top-100 100 Hz human inputs in the local simulator and record state/action pairs.

The action tape is used only as a teacher during collection. The exported dataset
contains physical observations and labels, not an executable action timeline.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from hybrid_tracking import Hybrid, load_asset
from prepare_fall_campaign import save_json
from vector_physics import VectorPhysics

CAMPAIGN = ROOT / "local/campaign-2026-autumn"
CORPUS = ROOT / "local/training/human-rework-0.70/top100-cohort"
OUT = ROOT / "local/training/hardcode-human-0.73"
PHYSICS = ROOT / "local/training/hybrid-speed-0.58/native/libtm2020_speed.so"
API = Path(os.environ.get("TM2020_HARDCODE_NATIVE", ROOT / "native/build-hardcode-0.73")) / "libtm2020_vector_physics.so"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=int, default=3)
    ap.add_argument("--first-rank", type=int, default=1)
    ap.add_argument("--last-rank", type=int, default=100)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args()
    idx = args.map
    map_path = CAMPAIGN / f"Autumn-2026-{idx:02d}.Map.Gbx"
    meta = json.loads((ROOT / f"local/training/fall-campaign-0.52/{idx:02d}/map.json").read_text())
    route_asset = OUT / f"{idx:02d}/historical-champion.tmhyb"
    reference, _, _ = load_asset(route_asset, map_path=map_path, uid=meta["mapUid"])
    rows = []
    episodes = []
    stats = {"finished": 0, "terminated_early": 0, "truncated": 0, "missing": 0}

    ranks = list(range(args.first_rank, args.last_rank + 1))
    for start in range(0, len(ranks), args.batch):
        group = ranks[start:start + args.batch]
        streams = []
        for rank in group:
            folder = CORPUS / f"{idx:02d}" / f"leaderboard-rank{rank:03d}"
            timeline = folder / "timeline.npz"
            analysis = folder / "analysis.json"
            if not timeline.is_file() or not analysis.is_file():
                stats["missing"] += 1
                streams.append(None)
                continue
            with np.load(timeline) as data:
                controls = np.asarray(data["controls"], dtype=np.float32).copy()
            doc = json.loads(analysis.read_text())
            if controls.ndim != 2 or controls.shape[1] != 3 or not len(controls):
                raise ValueError(f"Bad control timeline: {timeline}")
            if not np.isin(controls[:, :2], [0., 1.]).all() or not np.allclose(controls[:, 2] * 127., np.rint(controls[:, 2] * 127.), atol=1e-5, rtol=0):
                raise ValueError(f"Non-binary pedals or non-i8 steering: {timeline}")
            streams.append((controls, doc))

        n = len(group)
        horizon = max((len(item[0]) for item in streams if item), default=100)
        env = VectorPhysics(n, decision_ticks=1, api_path=API, library=PHYSICS,
                            map_path=map_path, horizon=horizon + 2)
        bot = Hybrid(route_asset, n)
        active = np.zeros(n, dtype=bool)
        lengths = np.zeros(n, dtype=np.int32)
        terminated = np.zeros(n, dtype=bool)
        episode_rows = [[] for _ in group]
        checkpoint_events = [[] for _ in group]
        last_checkpoint_count = np.zeros(n, dtype=np.uint32)
        final_states = [None] * n
        try:
            for lane, item in enumerate(streams):
                bot.reset(lane)
                if item is None:
                    continue
                controls, doc = item
                env.reset(lane, int(doc["validationSeed"]))
                active[lane] = True
                lengths[lane] = len(controls)
            for tick in range(horizon):
                if not active.any():
                    break
                actions = bot.act(env)
                step_actions = np.zeros((n, 3), dtype=np.float32)
                for lane, item in enumerate(streams):
                    if not active[lane] or item is None:
                        continue
                    controls, _ = item
                    state = env.states[lane]
                    if state.terminated or state.truncated:
                        active[lane] = False
                        terminated[lane] = bool(state.terminated)
                        continue
                    if tick >= len(controls):
                        active[lane] = False
                        continue
                    feature = bot.features[lane].copy()
                    # Historical route assets are v4 and place feedforward steer in
                    # feature 8; v8 runtime uses the previous *applied* steer.
                    # Rebuild that feature from the exact 100 Hz teacher history.
                    feature[8] = float(controls[tick - 1, 2]) if tick else 0.0
                    route_index = bot.cursor_index(lane)
                    feature[9] = route_index / max(1, len(reference) - 1)
                    here = reference[route_index]
                    ahead = reference[min(route_index + 10, len(reference) - 1)]
                    h0 = np.arctan2(float(here[2]), float(here[8]))
                    h1 = np.arctan2(float(ahead[2]), float(ahead[8]))
                    feature[10] = np.clip(np.remainder(h1 - h0 + np.pi, 2 * np.pi) - np.pi, -.4, .4) * 10.
                    action = controls[tick].copy()
                    episode_rows[lane].append((feature, action))
                    bot.commit(lane, float(action[2]))
                    step_actions[lane] = action
                env.step(step_actions)
                for lane in range(n):
                    if not active[lane]:
                        continue
                    state = env.states[lane]
                    count = int(state.checkpoints)
                    if count > last_checkpoint_count[lane]:
                        checkpoint_events[lane].extend([int(state.tick * 10)] * (count - int(last_checkpoint_count[lane])))
                        last_checkpoint_count[lane] = count
            final_states = [env.states[lane] for lane in range(n)]
        finally:
            bot.close()
            env.close()

        for lane, item in enumerate(streams):
            if item is None:
                continue
            controls, doc = item
            state = final_states[lane]
            # Finish is not inferred from the terminal bit: simulator checkpoint parity
            # is recorded separately and will be checked before accepting the dataset.
            checkpoint = list(doc.get("checkpointCumulativeMs", []))
            expected_checkpoints = len(checkpoint)
            sim_finish_ms = int(state.finish_ms)
            accepted = sim_finish_ms >= 0 and int(state.checkpoints) >= expected_checkpoints
            if accepted:
                stats["finished"] += 1
            elif state.truncated:
                stats["truncated"] += 1
            else:
                stats["terminated_early"] += 1
            collected = episode_rows[lane]
            if collected:
                features = np.stack([x for x, _ in collected]).astype(np.float32)
                labels = np.stack([y for _, y in collected]).astype(np.float32)
                rows.append((features, labels, group[lane]))
            episodes.append({"rank": group[lane], "seed": int(doc["validationSeed"]),
                             "inputTicks": len(controls), "collectedTicks": len(collected),
                             "simTerminal": bool(state.terminated), "simTruncated": bool(state.truncated),
                             "simCheckpoints": int(state.checkpoints), "expectedCheckpoints": expected_checkpoints,
                             "simFinishMs": sim_finish_ms, "checkpointEventsMs": checkpoint_events[lane],
                             "checkpointAbsErrorMs": [abs(a-b) for a,b in zip(checkpoint_events[lane], checkpoint)],
                             "acceptedForTraining": bool(accepted),
                             "checkpointTimesHumanMs": checkpoint})

    if not rows:
        raise RuntimeError("No state/action samples collected")
    features = np.concatenate([x for x, _, _ in rows])
    labels = np.concatenate([y for _, y, _ in rows])
    sample_ranks = np.concatenate([np.full(len(x), rank, dtype=np.int16) for x, _, rank in rows])
    target = OUT / f"{idx:02d}/behavior-dataset-top{args.last_rank:03d}.npz"
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, features=features, controls=labels, rank=sample_ranks)
    report = {"map": idx, "sourceRanks": [args.first_rank, args.last_rank], "samples": len(features),
              "acceptedRanks": [x["rank"] for x in episodes if x.get("acceptedForTraining")],
              "episodes": episodes, "simulatorOutcomes": stats,
              "features": "v8 physical route-relative state; no action tape stored",
              "labels": "human 100 Hz gas/brake/i8 steering", "dataset": str(target)}
    save_json(target.with_suffix(".json"), report)
    print(json.dumps({"dataset": str(target), "samples": len(features), "outcomes": stats}, indent=2))


if __name__ == "__main__":
    main()
