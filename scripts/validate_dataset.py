#!/usr/bin/env python3
"""No third-party packages. Offline quality gate for Trackmania replay state/input exports."""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import sys


def validate(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if data["schema"] != "tm2020_replay_dataset_v1":
        raise ValueError("Unknown replay dataset schema")

    report: dict = {"source": str(path), "ghosts": []}
    for idx, container in enumerate(data["ghosts"]):
        ghost = container["result"]
        rows = ghost.get("stateInputRows", [])
        events = ghost.get("inputEventTimeline", [])
        if not rows:
            report["ghosts"].append({"index": idx, "error": "No vehicle telemetry"})
            continue

        times = [r["tMs"] for r in rows]
        steps = [b - a for a, b in zip(times, times[1:])]
        invalid_floats = []
        for j, r in enumerate(rows):
            values = [r["speedKmh"], *r["position"], *r["rotation"], *r["velocity"]]
            if not all(math.isfinite(v) for v in values):
                invalid_floats.append(j)
        speed_err = []
        speed_samples = 0
        for r in rows:
            velocity = r["velocity"]
            predicted = math.sqrt(sum(x * x for x in velocity)) * 3.6
            if predicted > 1:
                speed_err.append(abs(predicted - r["speedKmh"]))
                speed_samples += 1

        by_surface = Counter(
            m for row in rows for m in row["tire"]["groundMaterials"]
        )

        # The recorded steering value may follow the game's special quantization.
        steer_raw = [r["replayInput"]["steerRaw"] for r in rows]
        diffs = {
            "steerRawOver127": statistics.fmean(
                abs(r["recordedControls"]["steer"] - r["replayInput"]["steerRaw"] / 127)
                for r in rows
            ),
            "steerRawOver128": statistics.fmean(
                abs(r["recordedControls"]["steer"] - r["replayInput"]["steerRaw"] / 128)
                for r in rows
            ),
            "steerRawBiasOver255": statistics.fmean(
                abs(r["recordedControls"]["steer"] - ((r["replayInput"]["steerRaw"] * 2 - 1) / 255))
                for r in rows
            ),
        }
        gas_diff = sum(int(r["replayInput"]["gas"]) != (r["recordedControls"]["gas"] >= 0.5) for r in rows)
        brake_diff = sum(int(r["replayInput"]["brake"]) != (r["recordedControls"]["brake"] >= 0.5) for r in rows)
        result = {
            "index": idx,
            "rows": len(rows),
            "inputEvents": len(events),
            "timeRangeMs": [times[0], times[-1]],
            "sampleIntervalMs": dict(Counter(steps).most_common(8)),
            "nonMonotonicSampleTimes": sum(step <= 0 for step in steps),
            "nonFiniteStateRows": len(invalid_floats),
            "speedComparedSamples": speed_samples,
            "speedVsVelocityMeanAbsoluteErrorKmh": round(statistics.fmean(speed_err), 5) if speed_err else None,
            "speedVsVelocityMaxErrorKmh": round(max(speed_err), 5) if speed_err else None,
            "gasSampleMismatches": gas_diff,
            "brakeSampleMismatches": brake_diff,
            "meanSteerAlignmentErrors": {k: round(v, 7) for k, v in diffs.items()},
            "steerInputRawRange": [min(steer_raw), max(steer_raw)],
            "wheelContactMaterials": dict(by_surface.most_common(15)),
        }
        if result["nonMonotonicSampleTimes"] or result["nonFiniteStateRows"]:
            raise ValueError(f"Invalid vehicle samples: {result}")
        report["ghosts"].append(result)
    return report


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("dataset", nargs="+", type=Path)
    cli.add_argument("--output", type=Path, help="Save quality report as JSON")
    args = cli.parse_args()
    reports = [validate(path) for path in args.dataset]
    output = {"schema": "tm2020_dataset_validation_v1", "reports": reports}
    text = json.dumps(output, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
