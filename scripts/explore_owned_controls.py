"""Deterministic action-history frontier exploration of a guarded owned scene.

Successful prefixes are research rollouts, not proof of a general action domain.
Failed steps never produce observations or training transitions. Plans and the
first missing-byte/instruction evidence are retained for targeted source capture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

from owned_step_machine import open_owned_machine,UncapturedStepError


def plans(horizon):
    result=[]
    for prefix in (0,25,100,200):
        for name,action in (("coast",[0,0,0]),("brake",[0,1,0]),
                            ("left",[1,0,-1]),("right",[1,0,1])):
            if prefix<horizon:
                result.append((f"{name}-after-{prefix}",[[1,0,0]]*prefix+[action]*(horizon-prefix)))
    for seed in range(4):
        rng=random.Random(seed)
        sequence=[]
        for index in range(horizon):
            if index%10==0:
                action=[rng.choice((0.0,0.5,1.0)),rng.choice((0.0,0.5,1.0)),rng.choice((-1.0,0.0,1.0))]
            sequence.append(action)
        result.append((f"random-ten-tick-{seed}",sequence))
    return result


def main(args):
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32,
                               max_steps=args.steps,native_guard=args.native_guard)
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    started=time.perf_counter()
    for name,controls in plans(args.steps):
        path=args.output/(name+".json")
        raw=json.dumps(controls,separators=(",",":"))+"\n"
        if path.exists() and path.read_text()!=raw:raise ValueError("Existing exploration plan differs")
        path.write_text(raw)
        machine.reset()
        digest=hashlib.sha256()
        error=None
        begin=time.perf_counter()
        initial=machine.observation()
        observation=initial
        for action in controls:
            try:
                digest.update(machine.step(action))
            except UncapturedStepError as exc:
                error=str(exc)
                break
            observation=machine.observation()
        gaps=machine.report.get("uncapturedAccesses") or machine.report.get("uncapturedMappings",[])
        row=dict(name=name,plan=str(path.resolve()),planSha256=hashlib.sha256(raw.encode()).hexdigest(),
            completed=machine.frame==args.steps and error is None,acceptedFrames=machine.frame,
            requestedFrames=args.steps,error=error,firstUncapturedAccess=gaps[0] if gaps else None,
            acceptedPrefixTraceSha256=digest.hexdigest(),lastAcceptedObservation=observation,
            failedStepObservationReturned=False,elapsedSeconds=time.perf_counter()-begin)
        if gaps:
            row["missingConfigurationOffset"]=gaps[0]["address"]-machine.metadata["configuration"]
        rows.append(row)
        print("OWNED_FRONTIER",name,"accepted="+str(machine.frame),"completed="+str(row["completed"]),flush=True)
        report=dict(schema="tm2020_owned_control_history_frontier_v1",fixtureSha256=machine.fixture.sha256,
            plans=rows,plansCompleted=sum(r["completed"] for r in rows),
            acceptedFrames=sum(r["acceptedFrames"] for r in rows),
            coverageGuardImplementation=machine.report["coverageGuardImplementation"],
            nativeGuardCounters=machine.native_guard.counters() if machine.native_guard else None,
            nativeGuardDllSha256=hashlib.sha256(machine.native_guard.path.read_bytes()).hexdigest() if machine.native_guard else None,
            sourceProcessAccessed=False,failedStepsResumed=False,
            failedStepsUsedForTraining=False,generalActionDomainQualified=False,
            fullSimulatorQualified=False,elapsedSeconds=time.perf_counter()-started)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    parser.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    parser.add_argument("--native-guard",type=Path)
    parser.add_argument("--steps",type=int,default=300)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    main(parser.parse_args())
