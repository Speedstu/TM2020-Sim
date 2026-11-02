"""Exercise stopped entry/return, external snapshot release and timeout cleanup."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import time

from force_worker_fixture import require


def main(args):
    k=C.WinDLL("kernel32",use_last_error=True)
    k.CreateEventW.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_wchar_p];k.CreateEventW.restype=C.c_void_p
    k.SetEvent.argtypes=[C.c_void_p];k.CloseHandle.argtypes=[C.c_void_p]
    k.OpenProcess.argtypes=[C.c_uint32,C.c_int,C.c_uint32];k.OpenProcess.restype=C.c_void_p
    k.ReadProcessMemory.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    results=[];args.folder.mkdir(parents=True,exist_ok=True)
    for expired in (False,True):
        token=f"{os.getpid()}-{time.time_ns()}"
        name="Local\\TM2020-Scene-Lease-Test-"+token
        event=k.CreateEventW(None,True,False,name);require(event,"Cannot create owned release event")
        prefix=args.folder/("timeout-"+token if expired else "released-"+token)
        command=[str(args.runner.resolve()),"--selftest-scene-entry-hold",str(prefix.resolve()),name,
                 "100" if expired else "5000"]
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        source=None
        try:
            stage_path=Path(str(prefix)+".stage.json");deadline=time.monotonic()+10
            while not stage_path.exists():
                require(process.poll() is None,"Scene observer ended before publishing lease")
                require(time.monotonic()<deadline,"Owned lease publication timed out");time.sleep(.01)
            # Publication is a flushed JSON file; tolerate the create-to-flush window.
            stage=None
            while stage is None:
                try:stage=json.loads(stage_path.read_text())
                except json.JSONDecodeError:
                    require(time.monotonic()<deadline,"Incomplete stage JSON");time.sleep(.005)
            require(stage["targetThreadsStopped"] and not stage["gameThreadsStopped"],"Wrong owned lease scope")
            if not expired:
                source=k.OpenProcess(0x1010,False,stage["pid"]);require(source,"Cannot read owned stopped fixture")
                values=[]
                for _ in range(3):
                    value=C.c_uint32();got=C.c_size_t()
                    require(k.ReadProcessMemory(source,C.c_void_p(int(stage["scene"],0)+8),C.byref(value),4,C.byref(got)) and got.value==4,
                            "Cannot read fixture call counter")
                    values.append(value.value);time.sleep(.02)
                require(values==[0,0,0],"Owned target advanced during the debug-event lease")
                require(k.SetEvent(event),"Cannot release owned snapshot lease")
            stdout,stderr=process.communicate(timeout=12)
            require(process.returncode==0,"Owned lease observer failed: "+stdout+stderr)
            report=json.loads(Path(str(prefix)+".json").read_text())
            require(report["sceneReturned"] and report["detached"] and report["restoreFailures"]==0
                    and report["snapshotLeaseTimedOut"]==expired and not report["executableBytesPatched"],
                    "Entry/return or cleanup result differs")
            calls=report["queryPerformanceCounterTranscript"]
            require(len(calls)==2 and all(call["resultWord"]==1 and int(call["counterValue"])>0 for call in calls)
                and int(calls[1]["counterValue"])>=int(calls[0]["counterValue"]),
                "Owned platform counter entry/return transcript differs")
            results.append(dict(timeout=expired,passed=True,entryReturnAbiVerified=True,
                                stoppedCounterVerified=not expired,debuggerCleanlyDetached=True))
        finally:
            k.SetEvent(event)
            if source:k.CloseHandle(source)
            k.CloseHandle(event)
            if process.poll() is None:process.communicate(timeout=12)
    if args.report:args.report.write_text(json.dumps(dict(schema="tm2020_scene_snapshot_lease_owned_v1",cases=results,
        gameProcessAccessed=False,sourceCodePatched=False,completeSimulatorQualified=False),indent=2)+"\n")
    print("PASS OWNED_SCENE_LEASE held_counter_unchanged=true entry_return=true released_and_timeout_cleanup=true")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runner",type=Path,required=True);p.add_argument("--folder",type=Path,required=True)
    p.add_argument("--report",type=Path)
    main(p.parse_args())
