"""Compile a private masked reference for the owned native main-step runner."""

import argparse
import hashlib
import json
from pathlib import Path
import struct

from force_worker_fixture import require
from original_step_fixture import (
    load_original_step_fixture,
    verify_original_step_images,
)


def compile_fixture(args):
    require(
        not args.output.exists() or args.verify_existing,
        "Compiler never overwrites a native fixture",
    )
    f = load_original_step_fixture(args.fixture)
    verify_original_step_images(f, (args.exe, args.ntdll, args.kernel32))
    m = f.metadata
    require(m["entryRva"]=="0x7bd0e0","Native main-step runner does not implement the stopped outer-scene ABI")
    pipeline=m.get("postStepPipeline")
    game, nt = m["modules"]
    external = m["externalPlatformModels"][0]
    code = [rva for module, rva in m["codePages"] if module == 0]
    require(
        all(o["module"] == 0 for o in m["codeDataOverlays"]),
        "Native runner does not overwrite host OS module data/code",
    )
    data = [
        (a, p)
        for a, p in sorted(f.pages.items())
        if not nt["base"] <= a < nt["base"] + nt["imageSize"]
    ]
    scenario = m.get("scenarioControls")
    control_schedule = m.get("scenarioControlSchedule")
    steering_offset = m.get("scenarioSteeringOffset", 0x1430)
    require(steering_offset in (0xA0, 0x1430), "Unsupported steering field")
    command_scenario = steering_offset == 0xA0
    require(pipeline is None or command_scenario,
            "Native scene pipeline requires version-6 steering command controls")
    require(not command_scenario or scenario or control_schedule,
            "Steering command field without a control scenario")
    require(
        not (control_schedule and scenario and scenario.get("heldEveryStep") is True),
        "Fixture contains multiple control schedules",
    )
    out = bytearray(
        (b"TMSTNV7\0" + struct.pack("<I", 7))
        if pipeline is not None
        else (b"TMSTNV6\0" + struct.pack("<I", 6))
        if command_scenario
        else (b"TMSTNV5\0" + struct.pack("<I", 5))
        if control_schedule
        else (b"TMSTNV4\0" + struct.pack("<I", 4))
        if scenario
        else (b"TMSTNV3\0" + struct.pack("<I", 3))
    )
    for digest in (game["sha256"], nt["sha256"], external["moduleSha256"], f.sha256):
        out += bytes.fromhex(digest)
    out += struct.pack("<Q", external["address"])
    out += struct.pack(
        "<2Q4I2Q2I3I",
        game["base"],
        nt["base"],
        game["imageSize"],
        len(code),
        len(data),
        len(m["codeDataOverlays"]),
        m["manager"],
        m["stateAddress"],
        m["stateCount"],
        m["tickCount"],
        *m["timingWords"]
    )
    if control_schedule or command_scenario:
        if control_schedule is None:
            require(scenario.get("heldEveryStep") is True, "Unsupported command schedule")
            control_schedule = [[scenario["drive"], scenario["brake"], scenario["steering"]]
                                for _ in range(m["tickCount"])]
        require(len(control_schedule) == m["tickCount"], "Control schedule horizon mismatch")
        require(m.get("scenarioActionAxis") is None, "Scheduled controls do not combine held action-axis overrides")
        require(
            all(isinstance(row, list) and len(row) == 3 and all(abs(float(v)) <= 1.0 for v in row) for row in control_schedule),
            "Invalid per-tick internal control schedule",
        )
        out += struct.pack("<QI", m["vehicle"], len(control_schedule))
        if command_scenario:
            out += struct.pack("<I", steering_offset)
        for row in control_schedule:
            out += struct.pack("<3f", *row)
    elif scenario:
        require(scenario.get("heldEveryStep") is True, "Unsupported control schedule")
        controls = (scenario["drive"], scenario["brake"], scenario["steering"])
        require(all(abs(float(value)) <= 1.0 for value in controls), "Control scalar outside [-1, 1]")
        action_axis = m.get("scenarioActionAxis")
        flags = 1 | (2 if action_axis is not None else 0)
        if action_axis is None:
            action_axis = 0.0
        require(abs(float(action_axis)) <= 1.0, "Action axis outside [-1, 1]")
        out += struct.pack("<IQ4f", flags, m["vehicle"], *controls, action_axis)
    if pipeline is not None:
        out += struct.pack("<I2Q",pipeline["version"],pipeline["collisionWorld"],
                           pipeline["registeredForceContext"])
    out += struct.pack("<" + "I" * len(code), *code)
    for overlay in m["codeDataOverlays"]:
        out += struct.pack("<2I", overlay["rva"], len(overlay["bytes"]))
        for offset, value in overlay["bytes"]:
            out += struct.pack("<HB", offset, value)
    for address, p in data:
        out += struct.pack("<Q", address) + p.initial
    outputs = m["trace"]["outputs"]
    width, at = m["trace"]["frameBytes"], 0
    out += struct.pack("<I", len(outputs))
    for output in outputs:
        count = output["bytes"]
        out += (
            struct.pack("<QI", output["address"], count) + f.trace_mask[at : at + count]
        )
        for frame in range(m["tickCount"]):
            out += f.trace_expected[frame * width + at : frame * width + at + count]
        at += count
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        require(
            args.verify_existing and args.output.read_bytes() == out,
            "Existing native fixture differs from the verified source",
        )
    else:
        with args.output.open("xb") as target:
            target.write(out)
    report = dict(
        schema="tm2020_original_step_native_input_v1",
        sourceFixtureSha256=f.sha256,
        nativeFixtureSha256=hashlib.sha256(out).hexdigest(),
        nativeFixtureBytes=len(out),
        referenceFrames=m["tickCount"],
        nativeFixtureVersion=7 if pipeline is not None else 6 if command_scenario else 5 if control_schedule else 4 if scenario else 3,
        selectedScenePipelineVersion=pipeline["version"] if pipeline is not None else 0,
        steeringOverrideOffset=steering_offset if scenario or control_schedule else None,
        originalCodeBytesIncluded=False,
        rawUnaccessedHeapBytesIncluded=False,
        wholeHeadlessSimulatorQualified=False,
    )
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS NATIVE MAIN-STEP INPUT", m["tickCount"], "frames;", len(out), "bytes")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", type=Path, required=True)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--ntdll", type=Path, default=Path(r"C:\Windows\System32\ntdll.dll"))
    p.add_argument(
        "--kernel32", type=Path, default=Path(r"C:\Windows\System32\kernel32.dll")
    )
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--verify-existing", action="store_true")
    compile_fixture(p.parse_args())
