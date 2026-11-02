"""Distinguish changed command bytes from an observed physical trajectory response."""
import argparse
import json
import math
import struct
from pathlib import Path
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture


def audit(args):
    baseline = load_original_step_fixture(args.baseline)
    scenario = load_original_step_fixture(args.scenario)
    b, s = baseline.metadata, scenario.metadata
    require(b["tickCount"] == s["tickCount"], "Different horizons")
    require(b["trace"] == {**s["trace"], "expectedSha256": b["trace"]["expectedSha256"]},
            "Different trace layout")
    require(baseline.trace_mask == scenario.trace_mask, "Different observed masks")
    require(b["modules"] == s["modules"] and b["timingWords"] == s["timingWords"],
            "Different module cohort or timing")
    outputs = b["trace"]["outputs"]
    require(outputs[0]["name"] == "rigidStates" and outputs[0]["bytes"] == 88,
            "Audit requires one complete rigid body")
    require(all(baseline.trace_mask[:88]), "Rigid observation is incomplete")
    width, ticks = b["trace"]["frameBytes"], b["tickCount"]
    records = [{"name": o["name"], "changedBytesAcrossFrames": 0,
                "changedFrames": 0, "firstChangedTick": None} for o in outputs]
    sampled, max_position, max_velocity = [], 0.0, 0.0
    kinematic_frames, first_kinematic_tick = 0, None
    for tick in range(ticks):
        at, changes = 0, []
        for output, result in zip(outputs, records):
            count = output["bytes"]
            changed = sum(bool(mask) and baseline.trace_expected[tick*width+at+j]
                          != scenario.trace_expected[tick*width+at+j]
                          for j, mask in enumerate(baseline.trace_mask[at:at+count]))
            changes.append(changed)
            result["changedBytesAcrossFrames"] += changed
            if changed:
                result["changedFrames"] += 1
                if result["firstChangedTick"] is None:
                    result["firstChangedTick"] = tick+1
            at += count
        def delta(offset):
            a = struct.unpack_from("<3f", baseline.trace_expected, tick*width+offset)
            z = struct.unpack_from("<3f", scenario.trace_expected, tick*width+offset)
            require(all(math.isfinite(x) for x in (*a, *z)), "Nonfinite rigid state")
            return math.sqrt(sum((x-y)**2 for x,y in zip(a,z)))
        position, velocity = delta(0x24), delta(0x40)
        a=struct.unpack_from("<22f",baseline.trace_expected,tick*width)
        z=struct.unpack_from("<22f",scenario.trace_expected,tick*width)
        require(all(math.isfinite(x) for x in (*a,*z)),"Nonfinite rigid kinematics")
        # Compare matrix/position/velocities numerically. Signed zeros and a
        # quaternion-only representation change do not establish physical response.
        if any(a[j]!=z[j] for j in (*range(12),*range(16,22))):
            kinematic_frames+=1
            if first_kinematic_tick is None:first_kinematic_tick=tick+1
        max_position, max_velocity = max(max_position,position), max(max_velocity,velocity)
        if tick in (0, ticks//2-1, ticks//2, ticks//2+1, ticks-1):
            sampled.append({"tick": tick+1, "changedBytesByRecord": changes,
                            "positionDeltaMetres": position,
                            "linearVelocityDelta": velocity})
    response = kinematic_frames>0
    report = dict(schema="tm2020_original_step_control_response_v1",
                  baselineFixtureSha256=baseline.sha256, scenarioFixtureSha256=scenario.sha256,
                  ticksCompared=ticks, records=records, samples=sampled,
                  maximumPositionDeltaMetres=max_position,
                  maximumLinearVelocityDelta=max_velocity,
                  numericallyChangedKinematicFrames=kinematic_frames,
                  firstNumericallyChangedKinematicTick=first_kinematic_tick,
                  physicalActionResponseObserved=response,
                  steeringOverrideOffset=s.get("scenarioSteeringOffset",0x1430),
                  forceAccumulatorComparisonIsOnlyAtStepBoundary=True,
                  generalActionDomainQualified=False, fullSimulatorQualified=False,
                  gameProcessAccessed=False)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    require(not args.require_rigid_response or response,
            "Only command/internal bytes changed; no rigid trajectory response")
    print("PASS CONTROL_RESPONSE_AUDIT", "physical_response="+str(response).lower(),
          "first_rigid_change="+str(records[0]["firstChangedTick"]),
          "max_position_delta_m="+str(max_position))


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline",type=Path,required=True)
    p.add_argument("--scenario",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--require-rigid-response",action="store_true")
    audit(p.parse_args())
