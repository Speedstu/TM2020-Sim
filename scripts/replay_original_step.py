"""Offline main-step replay. No process handles, live reads or UI calls."""

import argparse
import copy
import sys, json, struct, hashlib, time, math
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from pinned_build import ROOT, SHA
from original_step_fixture import (
    load_original_step_fixture,
    verify_original_step_images,
)
from force_worker_fixture import require

sys.path.insert(0, str(ROOT / "tools/physics-python"))
from unicorn import *
from unicorn.x86_const import *
import pefile
from owned_step_machine import OriginalStepMachine, UncapturedStepError


def replay(args):
    files = [args.exe, args.ntdll, args.kernel32]
    results = []
    for fixture_path in args.fixtures:
        f = load_original_step_fixture(fixture_path)
        metadata = f.metadata
        images = verify_original_step_images(f, files)
        images[1].parse_data_directories(directories=[0])
        export_rvas = {
            item.name.decode(): item.address
            for item in images[1].DIRECTORY_ENTRY_EXPORT.symbols
            if item.name
        }
        data = {
            address: (p.mask, p.initial, p.expected) for address, p in f.pages.items()
        }
        fixture = fixture_path
        trial = fixture.stem
        scenario = args.scenario_controls
        if scenario is not None:
            require(all(math.isfinite(value) and abs(value)<=1.0 for value in scenario),
                    "Held internal control outside [-1, 1]")
        scenario_schedule = None
        if args.scenario_control_schedule is not None:
            require(scenario is None, "Choose held controls or a control schedule, not both")
            scenario_schedule = json.loads(args.scenario_control_schedule.read_text())
            require(
                isinstance(scenario_schedule, list)
                and len(scenario_schedule) == metadata["tickCount"]
                and all(isinstance(row, list) and len(row) == 3 for row in scenario_schedule),
                "Control schedule must contain one [drive, brake, steering] row per tick",
            )
            require(
                all(math.isfinite(float(x)) and abs(float(x)) <= 1.0 for row in scenario_schedule for x in row),
                "Scheduled internal control outside [-1, 1]",
            )
        scenario_active = scenario is not None or scenario_schedule is not None
        require(not (scenario_active and getattr(args,"initialize_writes",False)),
                "Counterfactual fixture export requires strict captured inputs; generated-byte serialization is not implemented")
        require(not args.scenario_steering_command or scenario_active,
                "Steering command override requires a control scenario")
        steering_offset = 0xA0 if args.scenario_steering_command else 0x1430
        scenario_action_axis = args.scenario_action_axis
        if not scenario_active:
            scenario_schedule=metadata.get("scenarioControlSchedule")
            inherited=metadata.get("scenarioControls")
            if inherited is not None and inherited.get("heldEveryStep") is True:
                require(scenario_schedule is None,"Fixture contains multiple control plans")
                scenario=[inherited["drive"],inherited["brake"],inherited["steering"]]
            steering_offset=metadata.get("scenarioSteeringOffset",0x1430)
            if scenario_action_axis is None:
                scenario_action_axis=metadata.get("scenarioActionAxis")
        controls_active=scenario is not None or scenario_schedule is not None
        require(steering_offset in (0xa0,0x1430),"Unsupported steering field")
        if scenario_schedule is not None:
            require(isinstance(scenario_schedule,list) and len(scenario_schedule)==metadata["tickCount"]
                    and all(isinstance(row,list) and len(row)==3
                            and all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=1
                                    for v in row) for row in scenario_schedule),
                    "Invalid stored control schedule")
        if scenario is not None:
            require(all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=1 for v in scenario),
                    "Invalid stored held controls")
        initial_scenario = scenario_schedule[0] if scenario_schedule is not None else scenario
        require(not args.scenario_steering_command or scenario_action_axis is None,
                "Version-6 steering commands do not combine action-axis overrides")
        require(
            scenario_action_axis is None or controls_active,
            "Action-axis schedule requires a counterfactual control scenario",
        )
        if scenario_action_axis is not None:
            require(-1.0 <= scenario_action_axis <= 1.0, "Action axis outside [-1, 1]")
        if scenario_active:
            require(
                len(args.fixtures) == 1 and args.scenario_output_dir is not None,
                "Counterfactual capture requires one fixture and an output directory",
            )
            vehicle = metadata["vehicle"]
            for offset, value in zip((0x98, 0x9C, steering_offset), initial_scenario):
                address = vehicle + offset
                page = address & ~4095
                require(page in data, "Control override page was not captured")
                mask, initial, expected = data[page]
                at = address - page
                require(all(mask[at : at + 4]), "Control override bytes were not observed")
                initial = bytearray(initial)
                initial[at : at + 4] = struct.pack("<f", value)
                data[page] = (mask, bytes(initial), expected)
            if scenario_action_axis is not None:
                address = vehicle + 0x1280 + 0xF4
                page = address & ~4095
                require(page in data, "Action-axis override page was not captured")
                mask, initial, expected = data[page]
                at = address - page
                require(all(mask[at : at + 4]), "Action-axis bytes were not observed")
                initial = bytearray(initial)
                initial[at : at + 4] = struct.pack("<f", scenario_action_axis)
                data[page] = (mask, bytes(initial), expected)
        machine = OriginalStepMachine(f, images, args.kernel32, data, trial,
                                      native_guard=getattr(args,"native_guard",None),
                                      initialize_writes=getattr(args,"initialize_writes",False))
        mu, report, fault_reason = machine.mu, machine.report, machine.fault_reason
        watched_roots, integration_intervals = machine.watched_roots, machine.integration_intervals
        started = time.perf_counter()
        error = None
        exact_frames = 0
        actual_frames = []
        try:
            for frame in range(metadata.get("tickCount", 1)):
                current_controls = (
                    scenario_schedule[frame] if scenario_schedule is not None else scenario
                ) if controls_active else None
                actual_frame = machine.step(current_controls, scenario_action_axis, steering_offset)
                if scenario_active:
                    actual_frames.append(actual_frame)
                width = metadata["trace"]["frameBytes"]
                expected_frame = f.trace_expected[frame * width : (frame + 1) * width]
                if not scenario_active and any(
                    mask and a != b
                    for mask, a, b in zip(f.trace_mask, actual_frame, expected_frame)
                ):
                    fault_reason.append(
                        f"Typed physical trace differs at frame {frame}"
                    )
                    break
                exact_frames += 1
                if frame % 10 == 0:
                    print("OFFLINE_STEP_REPLAY", trial, frame + 1, flush=True)
        except UncapturedStepError as exc:
            error = str(exc)
        end = mu.reg_read(UC_X86_REG_RIP)
        differences = []
        final_pages = {}
        for address, (mask, initial, expected) in data.items():
            actual = bytes(mu.mem_read(address, 4096))
            final_pages[address] = actual
            if scenario_active:
                continue
            if actual != expected:
                differences.append(
                    {
                        "address": hex(address),
                        "bytes": [
                            (i, actual[i], expected[i])
                            for i in range(4096)
                            if actual[i] != expected[i]
                        ][:8],
                    }
                )
        result = {
            "fixture": fixture.name,
            "fixtureSha256": f.sha256,
            "allTypedPhysicalFramesBitExact": not scenario_active and not fault_reason
            and error is None
            and exact_frames == metadata["tickCount"],
            "typedFramesCompared": 0 if scenario_active else exact_frames,
            "counterfactualFramesGenerated": exact_frames if scenario_active else 0,
            "tickCount": metadata.get("tickCount", 1),
            "completed": end == 0x500000000 and exact_frames == metadata["tickCount"],
            "endAddress": hex(end),
            "error": error,
            "faultReasons": fault_reason,
            "differingPages": differences[:16],
            "dataPages": len(data),
            "codePages": len(machine.code_pages),
            "allDataPagesBitExact": None if scenario_active else not differences,
            "counterfactualControls": (
                dict(drive=initial_scenario[0], brake=initial_scenario[1], steering=initial_scenario[2])
                if scenario_active and scenario is not None
                else None
            ),
            "counterfactualControlScheduleTicks": len(scenario_schedule) if scenario_active and scenario_schedule is not None else 0,
            "storedControlPlanReplayed": controls_active and not scenario_active,
            "counterfactualActionAxis": scenario_action_axis,
            "counterfactualSteeringOffset": hex(steering_offset) if scenario_active else None,
            "gameProcessAccessed": False,
            "originalGameCodeModified": False,
            "modeledOsImports": report["modeledOsImports"],
            "originalGameCalleesSkipped": False,
            "platformHeapAndMemoryApisModeled": True,
            "originalProcedureEntryCounts": {
                hex(rva): count for rva, count in watched_roots.items()
            },
            "integrationIntervalBinary32Counts": integration_intervals,
            "vehiclePoseSubstepIntervalCountsByFrame":machine.vehicle_substep_intervals,
            "vehicleSubstepSelectionInputsByFrame":machine.vehicle_selection_inputs,
            "wheelFlagsAtEngineUpdateEntry": {
                "samples": len(machine.wheel_entry_samples),
                "anyNonzeroWheelFlagSamples": sum(any(row["groundFlags"]) for row in machine.wheel_entry_samples),
                "allZeroWheelFlagSamples": sum(not any(row["groundFlags"]) for row in machine.wheel_entry_samples),
                "firstSamples": machine.wheel_entry_samples[:4],
                "atFunctionRva": "0x8447b0",
                "stepBoundaryFlagsAloneDoNotEstablishGrounding": True,
            },
            "wholeStepInstructionOracleQualified": False,
            "coverageGuardImplementation":report["coverageGuardImplementation"],
            "writeInitializationTracked":machine.initialize_writes,
            "nativeGuardCounters":machine.native_guard.counters() if machine.native_guard else None,
            "nativeGuardDllSha256":hashlib.sha256(machine.native_guard.path.read_bytes()).hexdigest() if machine.native_guard else None,
            "elapsedSeconds": time.perf_counter() - started,
        }
        results.append(result)
        if scenario_active and result["completed"] and error is None and not fault_reason:
            write_scenario_fixture(
                fixture_path,
                args.scenario_output_dir / f"{fixture_path.stem}-counterfactual.tmstep",
                metadata,
                data,
                final_pages,
                actual_frames,
                scenario_schedule if scenario_schedule is not None else scenario,
                scenario_action_axis,
                steering_offset,
            )
        print(
            json.dumps(
                {
                    k: result[k]
                    for k in [
                        "fixture",
                        "completed",
                        "endAddress",
                        "error",
                        "faultReasons",
                        "allDataPagesBitExact",
                        "differingPages",
                        "elapsedSeconds",
                    ]
                }
            ),
            flush=True,
        )
        args.report.write_text(
            json.dumps(
                {
                    "schema": "tm2020_original_step_offline_v1",
                    "sha256": SHA,
                    "fixtures": results,
                    "fullSimulatorReady": False,
                },
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        if any(
            not item["completed"]
            or item["error"]
            or item["faultReasons"]
            or (not scenario_active and not item["allDataPagesBitExact"])
            for item in results
        ):
            raise ValueError("Complete original main-step replay failed")


def write_scenario_fixture(source, destination, metadata, data, final_pages, frames, controls, action_axis, steering_offset):
    require(not destination.exists(), "Counterfactual fixture output already exists")
    updated = copy.deepcopy(metadata)
    updated["counterfactualSourceFixtureSha256"] = load_original_step_fixture(source).sha256
    updated.pop("scenarioControlSchedule", None)
    updated.pop("scenarioSteeringOffset", None)
    if controls and isinstance(controls[0], list):
        updated["scenarioControlSchedule"] = controls
        updated["scenarioControls"] = {
            "heldEveryStep": False,
            "ticks": len(controls),
            "source": "explicit internal record override per tick",
        }
    else:
        updated["scenarioControls"] = {
            "drive": controls[0], "brake": controls[1], "steering": controls[2],
            "heldEveryStep": True, "source": "explicit internal record override",
        }
    updated["scenarioActionAxis"] = action_axis
    if steering_offset != 0x1430:
        updated["scenarioSteeringOffset"] = steering_offset
    for record in updated["dataPages"]:
        address = record["address"]
        mask, initial, _ = data[address]
        final = final_pages[address]
        record["sha256"] = hashlib.sha256(mask + initial + final).hexdigest()
    trace_mask = load_original_step_fixture(source).trace_mask
    trace_expected = b"".join(frames)
    updated["trace"]["expectedSha256"] = hashlib.sha256(trace_expected).hexdigest()
    payloads = {
        "metadata.json": (json.dumps(updated, indent=2) + "\n").encode(),
        "trace-expected.bin": trace_expected,
    }
    for address, (mask, initial, _) in data.items():
        payloads[f"data/{address:016x}.bin"] = mask + initial + final_pages[address]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(source) as original, ZipFile(destination, "x") as result:
        for info in original.infolist():
            name = info.filename
            data_bytes = payloads.pop(name, None)
            if data_bytes is None:
                data_bytes = original.read(name)
            result.writestr(name, data_bytes, compress_type=ZIP_DEFLATED)
        require(not payloads, "Counterfactual fixture is missing archive members")
    print(
        "SAVED COUNTERFACTUAL_STEP_FIXTURE",
        destination,
        "controls=drive/brake/steering",
        "ticks=",
        len(frames),
        "sourceTraceMaskBytes=",
        len(trace_mask),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument(
        "--ntdll", type=Path, default=Path(r"C:\Windows\System32\ntdll.dll")
    )
    parser.add_argument(
        "--scenario-control-schedule",
        type=Path,
        help="JSON array with one [drive, brake, steering] internal record triple per tick",
    )
    parser.add_argument(
        "--kernel32", type=Path, default=Path(r"C:\Windows\System32\kernel32.dll")
    )
    parser.add_argument("--fixtures", type=Path, nargs="+", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--native-guard",type=Path,help="Optional compiled Unicorn coverage guard DLL")
    parser.add_argument("--initialize-writes",action="store_true")
    parser.add_argument(
        "--scenario-controls",
        type=float,
        nargs=3,
        metavar=("DRIVE", "BRAKE", "STEERING"),
        help="Hold these internal control-record scalars before every original step",
    )
    parser.add_argument("--scenario-output-dir", type=Path)
    parser.add_argument(
        "--scenario-steering-command", action="store_true",
        help="Apply steering at vehicle+0xa0 so the original slew updates +0x1430",
    )
    parser.add_argument(
        "--scenario-action-axis",
        type=float,
        help="Hold internal action-record axis at vehicle+0x1374 before every step",
    )
    replay(parser.parse_args())
