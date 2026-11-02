#!/usr/bin/env python3
"""Replay verified human inputs through the normal simulator and causal v7 governor."""
import argparse
import ctypes as C
import json
import subprocess
import struct
import hashlib
from pathlib import Path

import numpy as np

from hybrid_tracking import Hybrid, load_asset, save_asset
from prepare_fall_campaign import ROOT, save_json
from train_hardcode_recorded_inputs import human_action_constraints, NATIVE, PHYSICS
from vector_physics import VectorPhysics


def read_human_inputs(map_index, rank):
    folder = ROOT / f"local/training/human-rework-0.70/corpus/{map_index:02d}/leaderboard-rank{rank}"
    analysis = json.loads((folder / "analysis.json").read_text())
    timeline = np.load(folder / "timeline.npz")
    meta = json.loads((ROOT / f"local/training/fall-campaign-0.52/{map_index:02d}/map.json").read_text())
    source_ghost = Path(analysis.get("source", meta["referenceGhost"]))
    if not source_ghost.is_absolute():
        source_ghost = ROOT / source_ghost
    if hashlib.sha256(source_ghost.read_bytes()).hexdigest() != analysis["sha256"]:
        raise RuntimeError(f"Human ghost source hash differs from analyzed replay: {source_ghost}")
    decoded = json.loads(subprocess.check_output([
        str(ROOT / "cache/training-metadata-target/release/tm2020-training-metadata"),
        "inputs", str(source_ghost)], text=True))["ghosts"][0]
    group = decoded["groups"][0]
    offset = round(-group["start_offset_ms"] / 10)
    source = group["ticks"][offset:offset + len(timeline["controls"])]
    decoded_controls = np.asarray([
        [float(x["gas"]), float(x["brake"]), float(x["steer"]) / 127.]
        for x in source], dtype=np.float32)
    recorded = np.asarray(timeline["controls"], dtype=np.float32)
    if decoded_controls.shape != recorded.shape or not np.array_equal(decoded_controls, recorded):
        mismatch = np.flatnonzero(np.any(decoded_controls != recorded, axis=1))
        raise RuntimeError(f"Raw replay decode differs from analysis timeline at tick {int(mismatch[0])}")
    # The input-decoder command returns raw groups, while the retained analysis
    # record carries checkpoint and visual reference metadata for this same GBX.
    # Merge only after matching both source identity fields.
    original = json.loads((folder / "decoded-original.json").read_text())["ghosts"][0]
    if (original.get("declaredMs") != decoded.get("declaredMs") or
            original.get("validationSeed") != decoded.get("validationSeed")):
        raise RuntimeError("Raw input decode does not match the retained ghost metadata")
    decoded.update({key: original[key] for key in ("checkpointMs", "visualSamples") if key in original})
    return meta, analysis, timeline, decoded, recorded


def make_v7(path, source, meta, constraints):
    ref, gains, net = load_asset(source, map_path=meta["map"], uid=meta["mapUid"])
    data = Path(source).read_bytes()
    version = struct.unpack_from("<I", data, 8)[0]
    nu, ns = struct.unpack_from("<II", data, 24)
    feedback = np.zeros(3, dtype=np.float64)
    feedback[2] = 10.
    if version in (3, 5, 6, 7):
        offset = 32 + nu + ns + (6 + 449) * 8
        feedback = np.frombuffer(data, dtype="<f8", count=3, offset=offset).copy()
    save_asset(path, ref, gains, net, map_path=meta["map"], uid=meta["mapUid"],
               version=7, feedback_filter=feedback, human_constraints=constraints)
    return ref, gains, net, feedback


def run_controls(meta, seed, controls, *, governor_asset=None, timeline=None, expected_ghost=None):
    commands = np.ascontiguousarray(controls, dtype=np.float32)
    expected = expected_ghost
    if expected is None:
        expected = json.loads((ROOT / f"local/training/human-rework-0.70/corpus/{meta['index']:02d}/leaderboard-rank1/decoded-original.json").read_text())["ghosts"][0]
    vis = ({int(ms): p for ms, p in zip(timeline["visual_ms"], timeline["position"])}
           if timeline is not None else {})
    errors, crossings, first_cmd_diff, first_command_delta = [], [], None, None
    governor = Hybrid(governor_asset, 1) if governor_asset else None
    try:
        with VectorPhysics(1, decision_ticks=1, api_path=NATIVE / "libtm2020_vector_physics.so",
                           library=PHYSICS, map_path=meta["map"], horizon=len(commands) + 700,
                           normal_inputs=True) as env:
            env.reset(0, int(seed))
            state = env.buffer[0]
            initial = np.asarray(state.rigid_words, dtype=np.uint32).view(np.float32)[9:12].astype(float)
            if 0 in vis:
                errors.append({"ms": 0, "positionErrorM": float(np.linalg.norm(initial - vis[0]))})
            last_cp = 0
            applied_rows = []
            for i, raw in enumerate(commands):
                if governor:
                    action = governor.govern_controls(raw[None, :], np.asarray([i * 10], dtype=np.uint32))[0]
                else:
                    action = raw
                if first_cmd_diff is None and not np.array_equal(action, raw):
                    first_cmd_diff = i
                    first_command_delta = {"raw": raw.tolist(), "applied": action.tolist()}
                applied_rows.append(action.copy())
                env.step(action.reshape(1, 3)); state = env.buffer[0]
                if state.checkpoints > last_cp:
                    crossings.append({"checkpoint": int(state.checkpoints), "simMs": int(state.tick * 10),
                                      "ghostMs": int(expected["checkpointMs"][state.checkpoints - 1])})
                    last_cp = state.checkpoints
                ms = int(state.tick * 10)
                if ms in vis:
                    pos = np.asarray(state.rigid_words, dtype=np.uint32).view(np.float32)[9:12]
                    errors.append({"ms": ms, "positionErrorM": float(np.linalg.norm(pos - vis[ms]))})
                if state.terminated or state.truncated:
                    break
            if governor:
                governor.close()
                governor = None
            applied = np.asarray(applied_rows, dtype=np.float32).reshape(-1, 3)
            result = {"finishMs": int(state.finish_ms), "checkpoints": int(state.checkpoints),
                      "ticks": int(state.tick), "terminated": bool(state.terminated),
                      "initialSimPosition": initial.tolist(), "checkpointCrossings": crossings,
                      "ghostCheckpointMs": expected["checkpointMs"],
                      "visualSamples": len(errors),
                      "firstPositionDivergenceOver10cm": next((e for e in errors if e["positionErrorM"] > .1), None),
                      "firstPositionDivergenceOver1m": next((e for e in errors if e["positionErrorM"] > 1.), None),
                      "maximumVisualPositionErrorM": max((e["positionErrorM"] for e in errors), default=None),
                      "firstCommandDifferenceTick": first_cmd_diff,
                      "firstCommandDifference": first_command_delta,
                      "appliedControlsSha256": hashlib.sha256(applied.tobytes()).hexdigest(),
                      "appliedInputStatistics": command_metrics(applied)}
            return result
    finally:
        if governor:
            governor.close()


def command_metrics(actions):
    steer = np.rint(actions[:, 2] * 127).astype(int)
    delta = np.diff(steer)
    changes = np.flatnonzero(delta != 0) + 1
    reversals = sum(1 for a, b in zip(changes[:-1], changes[1:])
                    if b - a <= 10 and (delta[a - 1] < 0) != (delta[b - 1] < 0))
    small = sum(1 for a, b in zip(changes[:-1], changes[1:])
                if b - a <= 10 and (delta[a - 1] < 0) != (delta[b - 1] < 0)
                and max(abs(delta[a - 1]), abs(delta[b - 1])) <= 2)
    return {"steeringChangesPerSecond": float(len(changes) / max(len(actions) * .01, .01)),
            "steeringStepP99Raw": float(np.percentile(np.abs(delta), 99)) if len(delta) else 0.,
            "fastReversalsPerSecond": float(reversals / max(len(actions) * .01, .01)),
            "smallReversalsPerSecond": float(small / max(len(actions) * .01, .01)),
            "gasTransitionsPerSecond": float(np.count_nonzero(np.diff(actions[:, 0])) / max(len(actions) * .01, .01)),
            "brakeTransitionsPerSecond": float(np.count_nonzero(np.diff(actions[:, 1])) / max(len(actions) * .01, .01)),
            "gasDuty": float(actions[:, 0].mean()), "brakeDuty": float(actions[:, 1].mean()),
            "i8Quantized": bool(np.allclose(actions[:, 2] * 127, np.rint(actions[:, 2] * 127), atol=1e-5))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--map", type=int, default=1)
    ap.add_argument("--rank", type=int, default=1)
    ap.add_argument("--output", type=Path, default=ROOT / "local/training/hardcode-inputs-0.72/01/human-feasibility-ablation.json")
    ap.add_argument('--source',type=Path,help='Retained hardcode asset; original remains read-only')
    args = ap.parse_args()
    meta, analysis, timeline, decoded, controls = read_human_inputs(args.map, args.rank)
    map_meta = json.loads((ROOT / f"local/training/fall-campaign-0.52/{args.map:02d}/map.json").read_text())
    map_meta["index"] = args.map
    constraints = human_action_constraints(args.map)
    source = args.source or ROOT / f"local/training/hardcode-inputs-0.72/{args.map:02d}/search-incumbent.tmhyb"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    asset = args.output.parent / "diagnostic-v7.tmhyb"
    make_v7(asset, source, map_meta, constraints)
    results = {"humanRawDirect": run_controls(map_meta, analysis["validationSeed"], controls, timeline=timeline,
                                               expected_ghost=decoded),
               "humanThroughFullV7Governor": run_controls(map_meta, analysis["validationSeed"], controls,
                                                            governor_asset=asset, timeline=timeline,
                                                            expected_ghost=decoded)}
    ablations = {
        "pedals": [5, 6, 7], "steerAmplitudeAndStep": [0, 8], "steeringChangeRate": [1],
        "rapidReversals": [2, 3], "holdDurations": [4, 6, 7],
    }
    for name, indices in ablations.items():
        relaxed = constraints.copy()
        for i in indices:
            relaxed[i] = ([127, 100, 100, 100, 10, 100, 10, 10, 127][i])
        relaxed[9:] = constraints[9:]
        path = args.output.parent / f"diagnostic-v7-no-{name}.tmhyb"
        make_v7(path, source, map_meta, relaxed)
        results[f"humanV7Without_{name}"] = run_controls(map_meta, analysis["validationSeed"], controls,
                                                        governor_asset=path, timeline=timeline,
                                                        expected_ghost=decoded)
    permissive = np.r_[np.asarray([127, 100, 100, 100, 10, 100, 10, 10, 127], dtype=float),constraints[9:]]
    path = args.output.parent / "diagnostic-v7-permissive.tmhyb"
    make_v7(path, source, map_meta, permissive)
    results["humanV7PermissiveFormatOnly"] = run_controls(map_meta, analysis["validationSeed"], controls,
                                                          governor_asset=path, timeline=timeline,
                                                          expected_ghost=decoded)
    report = {"map": args.map, "humanRank": args.rank, "sourceGhostSha256": analysis["sha256"],
              "rawDecoderExactlyMatches100HzTimeline": True, "inputTicks": len(controls),
              "humanDeclaredMs": analysis["declaredMs"], "simulatorPhysicsLibrary": str(PHYSICS),
              "normalHistory100Hz": True, "seed": analysis["validationSeed"],
              "actionConstraints": constraints.tolist(), "actionEnvelopeVersion":7,"results": results,
              "oldChampionsModified": False, "clientGameAccessed": False}
    save_json(args.output, report)
    print(json.dumps({k: {"finishMs": v["finishMs"], "checkpoints": v["checkpoints"],
                         "appliedInputStatistics": v["appliedInputStatistics"]}
                      for k, v in results.items()}, indent=2))
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
