"""Audit source capture, every offline frame and independent native main steps."""

import argparse
import hashlib
import json
from pathlib import Path

from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture
from pinned_build import ROOT, SHA


def audit(args):
    capture = json.loads(args.capture.read_text())
    offline = json.loads(args.offline.read_text())
    require(
        capture["sha256"] == offline["sha256"] == SHA
        and capture["readOnlyProcessHandle"]
        and capture["sourceBindingRecheckedAfterCapture"]
        and not capture["gameMemoryWritten"]
        and not capture["codeExecutedInGame"]
        and not capture["rawHeapPagesPersisted"]
        and not capture["sourceCodeBytesPersisted"]
        and not capture["atomicSnapshot"]
        and capture["ownedWorkerCount"] == 0
        and not capture["systemCallsExecuted"],
        "Capture provenance/runtime scope mismatch",
    )
    require(
        len(capture["trials"]) == len(offline["fixtures"]) == 2,
        "Missing main-step references",
    )
    references = {r["fixture"]: r for r in offline["fixtures"]}
    results = []
    for trial in capture["trials"]:
        name = trial["trial"]
        f = load_original_step_fixture(args.fixtures / (name + ".tmstep"))
        replay = references[name + ".tmstep"]
        native = json.loads((args.native / (name + ".json")).read_text())
        require(
            trial["completed"]
            and not trial["error"]
            and not trial["faultReasons"]
            and trial["sparseFixtureSha256"]
            == f.sha256
            == replay["fixtureSha256"]
            == native["sourceFixtureSha256"],
            "Mixed/incomplete reference input",
        )
        require(
            replay["completed"]
            and not replay["error"]
            and not replay["faultReasons"]
            and replay["allDataPagesBitExact"]
            and replay["allTypedPhysicalFramesBitExact"]
            and not replay["gameProcessAccessed"]
            and not replay["originalGameCodeModified"]
            and not replay["originalGameCalleesSkipped"]
            and replay["platformHeapAndMemoryApisModeled"],
            "Offline original main-step comparison failed",
        )
        require(
            native["sha256"] == SHA
            and native["allTypedPhysicalFramesBitExact"]
            and native["completeMainProcedureReturnedEveryFrame"]
            and not native["originalGameInstructionsModified"]
            and not native["gameProcessAccessed"]
            and native["platformAbiBoundOnOwnedThread"]
            and native["originalExecutableRequired"]
            and native["sameOsModuleCohortRequired"]
            and not native["runtimePythonRequired"],
            "Native original main-step comparison failed",
        )
        frames = f.metadata["tickCount"]
        require(
            frames == 100
            and replay["typedFramesCompared"]
            == frames
            == native["typedFramesCompared"]
            == native["referenceFrames"]
            and native["rigidStateBytesPerFrame"] == f.metadata["stateCount"] * 88
            and native["observedBytesPerFrame"] == sum(f.trace_mask),
            "Frame/output inventory mismatch",
        )
        native_input = args.inputs / (name + ".tmstepnative")
        require(
            hashlib.sha256(native_input.read_bytes()).hexdigest()
            == native["nativeFixtureSha256"],
            "Native reference bytes changed",
        )
        require(
            not replay["wholeStepInstructionOracleQualified"]
            and not native["wholeStepInstructionOracleQualified"]
            and not native["fullHeadlessSimulatorQualified"],
            "Original-code backend scope overstated",
        )
        results.append(
            dict(
                name=name,
                fixtureSha256=f.sha256,
                referenceFrames=frames,
                observedBytesPerFrame=sum(f.trace_mask),
                activeForceWorkerExecuted=trial["executedVariant5"],
                rigidBefore=f.metadata["rigidBefore"],
                rigidAfter=f.metadata["rigidAfter"],
                stepsPerSecondIncludingComparisonAndProgressOutput=native[
                    "stepsPerSecondIncludingComparisonAndProgressOutput"
                ],
            )
        )
    require(
        sum(r["activeForceWorkerExecuted"] for r in results) == 1,
        "Need both inactive and active cases",
    )
    sources = (
        "scripts/pinned_build.py",
        "scripts/force_worker_fixture.py",
        "scripts/capture_original_step.py",
        "scripts/replay_original_step.py",
        "scripts/original_step_fixture.py",
        "scripts/compile_original_step_fixture.py",
        "native/src/original_step_native.cpp",
        "scripts/audit_original_step.py",
    )
    report = dict(
        schema="tm2020_original_main_step_qualification_v1",
        sha256=SHA,
        entryRva="0x7bd0e0",
        references=results,
        sourceHashes={
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in sources
        },
        completeMainStepObservedFramesNativeAndEmulatedBitExact=True,
        totalReferenceFrames=200,
        activeReferenceFrames=100,
        originalPortableArithmeticOperations=72,
        newPortableArithmeticOperations=0,
        platformApisSuppliedByOwnedAdapters=True,
        runningGameRequiredByReplay=False,
        completeMapCoverageVerified=False,
        arbitraryActionCoverageVerified=False,
        liveAuthoritativePhysicsClockVerified=False,
        playerOwnershipVerified=False,
        fullHeadlessSimulatorReady=False,
    )
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        "PASS ORIGINAL MAIN STEP: 100 active + 100 inactive frames; every observed physical frame exact"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("capture", "offline", "fixtures", "native", "inputs", "report"):
        p.add_argument("--" + name, type=Path, required=True)
    audit(p.parse_args())
