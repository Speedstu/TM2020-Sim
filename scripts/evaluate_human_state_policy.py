#!/usr/bin/env python3
"""Matched-seed A/B evaluation for the autonomous, state-conditioned v8 policy."""
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hybrid_tracking import load_asset
from train_hardcode_recorded_inputs import replay_action_tape_similarity
from tune_hybrid_tracking import NativeEvaluator


def summarize(rows, top100_ms, top10_ms):
    finish = [r["finishMs"] for r in rows if r.get("finishMs") is not None]
    return {"runs": len(rows), "finishes": len(finish), "finishRate": len(finish) / max(len(rows), 1),
            "meanFinishMs": float(np.mean(finish)) if finish else None,
            "medianFinishMs": float(np.median(finish)) if finish else None,
            "bestFinishMs": min(finish) if finish else None,
            "top100Finishes": sum(v <= top100_ms for v in finish),
            "top10Finishes": sum(v <= top10_ms for v in finish),
            "humanActionProxy": "recorded per-run action statistics in rows; proxy only"}


def main():
    root = ROOT
    folder = root / "local/training/hardcode-human-0.73/03"
    map_path = root / "local/campaign-2026-autumn/Autumn-2026-03.Map.Gbx"
    meta = json.loads((root / "local/training/fall-campaign-0.52/03/map.json").read_text())
    qual = json.loads((folder / "latest-qualification.json").read_text())
    candidates = {"retained-replay-reference": folder / "historical-champion.tmhyb",
                  "state-policy-v8": folder / "state-policy-v8.tmhyb",
                  "state-policy-v8-absolute": folder / "state-policy-v8-absolute.tmhyb",
                  "state-policy-v8-delta-scaled-005": folder / "state-policy-v8-delta-scaled-005.tmhyb",
                  "state-policy-v8-delta-scaled-010": folder / "state-policy-v8-delta-scaled-010.tmhyb",
                  "state-policy-v8-delta-scaled-025": folder / "state-policy-v8-delta-scaled-025.tmhyb",
                  "state-policy-v8-plus-physics-feedback": folder / "state-policy-v8-feedback.tmhyb"}
    report = {"map": 3, "sameSeeds": True, "seedFamilies": {}, "candidates": {},
              "physics": "local/training/hybrid-speed-0.58/native/libtm2020_speed.so",
              "native": "native/build-hardcode-0.73", "promotion": False}
    api = root / "native/build-hardcode-0.73/libtm2020_vector_physics.so"
    library = root / "local/training/hybrid-speed-0.58/native/libtm2020_speed.so"
    evaluator = NativeEvaluator(64, str(next(iter(candidates.values()))), api_path=api,
                                map_path=map_path, horizon=3500, library=library)
    try:
        for family in ("normal64", "perturbed64"):
            cases = qual["cases"][family]
            report["seedFamilies"][family] = [int(c["seed"]) for c in cases]
            for name, asset in candidates.items():
                _, gains, _ = load_asset(asset, map_path=map_path, uid=meta["mapUid"])
                rows, seconds = evaluator.evaluate(gains, cases, assets=[asset] * 64)
                report["candidates"].setdefault(name, {})[family] = summarize(
                    rows, int(qual["top100TargetMs"]), int(qual["top10TargetMs"]))
                report["candidates"][name][family]["elapsedSeconds"] = seconds
                report["candidates"][name][family]["actionTapeSimilarity"] = replay_action_tape_similarity(3, asset)
                report["candidates"][name][family]["rows"] = rows
    finally:
        evaluator.close()
    output = folder / "state-policy-v8-ab64.json"
    output.write_text(json.dumps(report, indent=2))
    compact = {name: {fam: {k: v for k, v in vals.items() if k != "rows"}
                      for fam, vals in result.items()} for name, result in report["candidates"].items()}
    print(json.dumps({"report": str(output), "candidates": compact}, indent=2))


if __name__ == "__main__":
    main()
