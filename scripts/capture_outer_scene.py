"""Capture one original outer-scene call while its source debug event is held.

The observer resumes the game on explicit release OR a bounded timeout. The
completed live call supplies an independent physical oracle. No live fallback
read is accepted after the stopped-source lease ends.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

from force_worker_fixture import require


def main(args):
    require(not args.output.exists(),"Outer-scene experiment never overwrites retained evidence")
    args.output.mkdir(parents=True)
    prefix=args.output/"source-observer"
    stage_path=Path(str(prefix)+".stage.json")
    final_path=Path(str(prefix)+".json")
    k=C.WinDLL("kernel32",use_last_error=True)
    k.CreateEventW.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_wchar_p];k.CreateEventW.restype=C.c_void_p
    k.SetEvent.argtypes=[C.c_void_p];k.CloseHandle.argtypes=[C.c_void_p]
    name=f"Local\\TM2020-Outer-Snapshot-{os.getpid()}-{time.time_ns()}"
    event=k.CreateEventW(None,True,False,name);require(event,"Cannot create stopped snapshot release event")
    observer=subprocess.Popen([str(args.observer.resolve()),"--confirm-local-solo-scene",str(args.target.resolve()),
        str(prefix.resolve()),name,str(args.steps)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    capture=None;stage=None
    try:
        deadline=time.monotonic()+12
        while stage is None:
            if stage_path.exists():
                try:stage=json.loads(stage_path.read_text())
                except json.JSONDecodeError:pass
            if stage is not None:break
            require(observer.poll() is None,"Source observer exited before publishing a stopped stage")
            require(time.monotonic()<deadline,"Stopped source stage was not reached");time.sleep(.01)
        command=[sys.executable,str(Path(__file__).with_name("capture_original_step.py")),
            "--exe",str(args.exe),"--source-binding",str(args.binding),"--steps",str(args.steps),"--active-only",
            "--outer-scene-stage",str(stage_path),"--snapshot-observer-pid",str(observer.pid),
            "--snapshot-release-event",name,"--output",str(args.output/"fixture"),
            "--report",str(args.output/"capture.json")]
        if args.controls is not None:command += ["--outer-scene-controls",*map(str,args.controls)]
        if args.native_capture is not None:command += ["--native-capture",str(args.native_capture)]
        if args.scenarios is not None:command += ["--outer-scene-scenarios",str(args.scenarios)]
        capture=subprocess.run(command,capture_output=True,text=True,timeout=55)
    finally:
        k.SetEvent(event)
        stdout,stderr=observer.communicate(timeout=12)
        k.CloseHandle(event)
        (args.output/"observer.log").write_text(stdout+stderr)
        if capture is not None:(args.output/"capture.log").write_text(capture.stdout+capture.stderr)
    require(observer.returncode==0 and final_path.exists(),"Source observer failed; see retained observer.log")
    final=json.loads(final_path.read_text())
    require(final["detached"] and final["restoreFailures"]==0 and final["sceneReturned"],"Source scene/debugger did not resume correctly")
    captured=json.loads((args.output/"capture.json").read_text()) if (args.output/"capture.json").exists() else None
    successful=bool(capture and capture.returncode==0 and captured and captured["trials"][0]["completed"])
    before=after=forces=None;frame_checks=[]
    if successful:
        trial=captured["trials"][0]
        def digest(words):return hashlib.sha256(struct.pack("<"+"I"*len(words),*words)).hexdigest()
        live_ticks=final.get("physicalTicks") or [final]
        require(len(live_ticks)==args.steps,"Source physical oracle tick count differs")
        before=trial["rigidBefore"][0]["bytesSha256"]==digest(live_ticks[0]["rigidBeforeWords"])
        from original_step_fixture import load_original_step_fixture
        fixture=load_original_step_fixture(args.output/"fixture/outer_scene_observed.tmstep")
        width=fixture.metadata["trace"]["frameBytes"]
        for i,tick in enumerate(live_ticks):
            frame=fixture.trace_expected[i*width:(i+1)*width]
            frame_checks.append(dict(tick=i+1,sourceClockWord=tick["clockWord"],
                rigidAfterMatched=hashlib.sha256(frame[:88]).hexdigest()==digest(tick["rigidAfterWords"]),
                forceAfterMatched=hashlib.sha256(frame[-24:]).hexdigest()==digest(tick["forcesAfterWords"])))
        after=all(row["rigidAfterMatched"] for row in frame_checks)
        forces=all(row["forceAfterMatched"] for row in frame_checks)
    result=dict(schema="tm2020_outer_scene_stopped_capture_v1",sourceObserverExitCode=observer.returncode,
        capturerExitCode=capture.returncode if capture else None,
        sceneFunctionCompletedInOwnedEmulator=successful,
        sourceSnapshotLeaseTimedOut=final["snapshotLeaseTimedOut"],
        sourceGamePrivateMemoryStoppedDuringCapture=successful and not final["snapshotLeaseTimedOut"],
        livePhysicalOracleCaptured=final["singleBodyPhysicalOracleCaptured"],
        independentLiveRigidBeforeMatched=before,independentLiveRigidAfterMatched=after,
        independentLiveForceAfterMatched=forces,
        observerEntryRva=final["entryRva"],sourceClockWord=final["clockWord"],sourceModeWord=final["modeWord"],
        sourceDebuggerCleanlyDetached=True,explicitSourceProcessMemoryWrites=False,
        capturedOwnedTicks=args.steps,independentLiveOracleTicks=len(final.get("physicalTicks",[])),
        livePhysicalFrameChecks=frame_checks,
        platformClockMode="exploratoryHostClock",platformClockTraceEquivalent=False,
        ownedCounterfactualControls=args.controls,liveActionOracleQualified=False,
        sourceExecutableInstructionsPatched=False,completeWorldInitializationQualified=False,
        completeExactSimulatorQualified=False,generalRlQualified=False)
    (args.output/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    require(successful and not final["snapshotLeaseTimedOut"],"Outer-scene execution stopped; diagnostic evidence retained")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("observer","target","binding","exe","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--steps",type=int,choices=range(1,101),default=1)
    p.add_argument("--controls",nargs=3,type=float,metavar=("DRIVE","BRAKE","STEERING"))
    p.add_argument("--native-capture",type=Path)
    p.add_argument("--scenarios",type=Path)
    main(p.parse_args())
