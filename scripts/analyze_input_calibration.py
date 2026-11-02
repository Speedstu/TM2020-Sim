"""Identify an actuator mapping from a stationary native all-copy sweep.

Use newest visual clock per frame; counting old buffered copies would bias the
fit. The result is evidence for this session/settings, not a universal constant.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics


def analyze(path: Path):
    frames = collections.defaultdict(list)
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["valid"] == "1":
                frames[row["elapsed_ms"]].append(row)
    grouped = collections.defaultdict(list)
    positions = []
    for rows in frames.values():
        elapsed = float(rows[0]["elapsed_ms"]) / 1000
        if not .4 < elapsed % 1 < .95:
            continue
        # Sweeps are bounded to 30 s; wrap cannot occur between copies here.
        newest = max(rows, key=lambda row: int(row["raw_header3"]))
        if float(newest["gas"]) != 0 or float(newest["brake"]) != 0:
            raise ValueError("Calibration requires no throttle/brake input")
        positions.append(tuple(float(newest[k]) for k in ("x", "y", "z")))
        grouped[float(newest["command_steer"])].append(float(newest["steer"]))
    pairs = [(x, statistics.median(values), len(values)) for x, values in sorted(grouped.items())]
    if len(pairs) < 20 or any(n < 20 for _, _, n in pairs):
        raise ValueError("Insufficient settled bidirectional sweep")
    motion = max(math.dist(positions[0], p) for p in positions)
    if motion > .1:
        raise ValueError("Car moved during steering calibration")
    if max(abs(y * 127 - round(y * 127)) for _, y, _ in pairs) > .001:
        raise ValueError("Observed response does not match signed seven-bit quantization")
    low, high = 0., .8
    for x, y, _ in pairs:
        if x == 0:
            if abs(y) > 1e-6:
                raise ValueError("Neutral steering is not neutral")
            continue
        if x * y < 0:
            raise ValueError("Steering sign mismatch")
        x, k = abs(x), round(abs(y) * 127)
        if k >= 127:
            continue
        if k > 0:
            high = min(high, (127 * x - k) / (127 - k))
        if k < 126:
            low = max(low, (127 * x - k - 1) / (126 - k))
    if not 0 <= low < high < .8:
        raise ValueError("No consistent linear deadzone/truncation model")
    rounded = round((low + high) / 2, 2)
    estimate = rounded if low < rounded <= high else (low + high) / 2
    return {
        "schema": "tm2020_empirical_actuator_calibration_v1",
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source": str(path), "maximum_stationary_displacement_m": motion,
        "deadzone_feasible_interval": [low, high], "suggested_deadzone": estimate,
        "signed_quantization_levels": 127, "selection": "newest_visual_clock_per_settled_frame",
        "pairs": [{"sent": x, "received_median": y, "frames": n} for x, y, n in pairs],
        "settings_specific": True, "physics_owner_verified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    result = analyze(args.capture)
    args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("ACTUATOR_CALIBRATION", result["suggested_deadzone"], result["deadzone_feasible_interval"])
