#!/usr/bin/env python3
"""Collect off-trajectory policy states and label them from nearest human state/action."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hybrid_tracking import Hybrid
from prepare_fall_campaign import save_json
from vector_physics import VectorPhysics


def main():
    root = ROOT
    folder = root / "local/training/hardcode-human-0.73/03"
    map_path = root / "local/campaign-2026-autumn/Autumn-2026-03.Map.Gbx"
    api = Path(os.environ.get("TM2020_HARDCODE_NATIVE", root / "native/build-hardcode-0.73")) / "libtm2020_vector_physics.so"
    library = root / "local/training/hybrid-speed-0.58/native/libtm2020_speed.so"
    source = folder / "behavior-dataset-top100.npz"
    source_report = json.loads(source.with_suffix(".json").read_text())
    with np.load(source) as d:
        hx = torch.from_numpy(d["features"].copy()).cuda()
        hy = d["controls"].copy()
        hrank = d["rank"].copy()
    accepted = torch.as_tensor(np.isin(hrank, source_report["acceptedRanks"]), device="cuda")
    train_human = accepted & torch.as_tensor(hrank <= 80, device="cuda")
    hx = hx[train_human]
    hy = hy[train_human.cpu().numpy()]
    scale = torch.clamp(hx.std(0), min=.05)
    hx = hx / scale

    rng = np.random.default_rng(20261031)
    n = 16
    cases = [{"seed": int(rng.integers(1, 2**32 - 1)), "warm": int(rng.integers(200, 1600)),
              "duration": int(rng.integers(2, 7)), "kick": float(rng.choice([-1, 1]) * rng.uniform(.02, .08))}
             for _ in range(n)]
    feats, rows = [], [[] for _ in range(n)]
    active = np.ones(n, dtype=bool)
    final_outcomes = [None] * n
    with VectorPhysics(n, decision_ticks=1, api_path=api, library=library, map_path=map_path, horizon=2300) as env, \
            Hybrid(folder / "state-policy-v8.tmhyb", n) as policy:
        for lane, case in enumerate(cases):
            env.reset(lane, case["seed"])
            policy.reset(lane)
        for t in range(2300):
            if not active.any():
                break
            actions = policy.act(env)
            for lane, case in enumerate(cases):
                if not active[lane]:
                    continue
                state = env.states[lane]
                if state.terminated or state.truncated:
                    active[lane] = False
                    final_outcomes[lane] = {"finishMs": int(state.finish_ms), "checkpoints": int(state.checkpoints),
                                            "terminated": bool(state.terminated), "truncated": bool(state.truncated)}
                    continue
                feature = policy.features[lane].copy()
                if feature[11] == 0.0:
                    # Controller lost route localization. Do not pad the DAgger set
                    # with repeated zero observations after its failsafe neutralizes.
                    active[lane] = False
                    final_outcomes[lane] = {"finishMs": int(state.finish_ms), "checkpoints": int(state.checkpoints),
                                            "terminated": bool(state.terminated), "truncated": bool(state.truncated),
                                            "controllerLostRoute": True}
                    continue
                rows[lane].append(feature)
                if case["warm"] <= t < case["warm"] + case["duration"]:
                    actions[lane, 2] = np.clip(actions[lane, 2] + case["kick"], -1., 1.)
                actions[lane, 2] = np.rint(actions[lane, 2] * 127.) / 127.
            env.step(actions)
        for lane in range(n):
            if final_outcomes[lane] is None:
                s = env.states[lane]
                final_outcomes[lane] = {"finishMs": int(s.finish_ms), "checkpoints": int(s.checkpoints),
                                        "terminated": bool(s.terminated), "truncated": bool(s.truncated)}
    for lane, values in enumerate(rows):
        if values:
            feats.extend(values)
    q = torch.as_tensor(np.asarray(feats, dtype=np.float32), device="cuda")
    qn = q / scale
    human_norm_sq = (hx * hx).sum(1)
    matches, match_dist = [], []
    for batch in qn.split(256):
        d2 = (batch * batch).sum(1, keepdim=True) + human_norm_sq[None, :] - 2 * batch @ hx.T
        # Require local route progress; among comparable states prefer the closest physics state.
        phase = batch[:, 9:10] - hx[None, :, 9]
        d2 += 400. * phase.square()
        vals, inds = d2.min(1)
        matches.extend(inds.cpu().numpy().tolist())
        match_dist.extend(vals.clamp_min(0).sqrt().cpu().numpy().tolist())
    distances = np.asarray(match_dist, dtype=np.float32)
    keep = distances <= 6.0
    feats = np.asarray(feats, dtype=np.float32)[keep]
    labels = hy[np.asarray(matches, dtype=np.int64)[keep]].copy()
    dagger = folder / "dagger-human-nearest.npz"
    np.savez_compressed(dagger, features=feats, controls=labels.astype(np.float32),
                        nearestDistance=distances[keep])
    report = {"map": 3, "seedProtocol": "16 deterministic unseen seeds with one short steering perturbation",
              "samples": len(feats), "unfilteredOnPolicySamples": len(distances),
              "nearestDistanceGate": 6.0, "sourceHumanRanks": "accepted ranks 1-80 only",
              "labeling": "nearest human state/action, scaled physical features and route progress penalty",
              "nearestDistanceMedian": float(np.median(match_dist)) if match_dist else None,
              "nearestDistanceP95": float(np.percentile(match_dist, 95)) if match_dist else None,
              "acceptedDistanceMedian": float(np.median(distances[keep])) if keep.any() else None,
              "acceptedDistanceP95": float(np.percentile(distances[keep], 95)) if keep.any() else None,
              "episodes": [{"seed": c["seed"], "warm": c["warm"], "duration": c["duration"], "kick": c["kick"],
                            "collectedTicks": len(rows[i]), **(final_outcomes[i] or {})} for i, c in enumerate(cases)],
              "dataset": str(dagger), "validationSeedOverlap": False}
    save_json(dagger.with_suffix(".json"), report)
    print(json.dumps({k: v for k, v in report.items() if k != "episodes"}, indent=2))


if __name__ == "__main__":
    main()
