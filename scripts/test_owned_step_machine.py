"""Differential stepping, branch, rewind, reset and unknown-input rejection.

Requires private local fixtures, never starts or opens the game process.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture
from owned_step_machine import open_owned_machine, UncapturedStepError


def run(args):
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32,
                               native_guard=getattr(args,"native_guard",None),
                               initialize_writes=getattr(args,"initialize_writes",False))
    fixture=machine.fixture
    other=load_original_step_fixture(args.brake_fixture)
    require(fixture.metadata["initialSnapshotSeedFixtureSha256"]==other.sha256,
            "Branch comparison requires this retained seed")
    require(fixture.metadata["trace"]["outputs"]==other.metadata["trace"]["outputs"],
            "Branch trace layouts differ")
    shared_mask=bytes(a&b for a,b in zip(fixture.trace_mask,other.trace_mask))
    require(all(shared_mask[:88]),"Complete rigid comparison is required")
    count=0
    def check_frame(actual,reference,index):
        nonlocal count
        width=reference.metadata["trace"]["frameBytes"]
        expected=reference.trace_expected[index*width:(index+1)*width]
        mask=fixture.trace_mask if reference is fixture else shared_mask
        require(all(not observed or a==b for observed,a,b in zip(mask,actual,expected)),
                "Owned interactive trace differs at tick "+str(index+1))
        count+=1
    schedule=fixture.metadata["scenarioControlSchedule"]
    started=time.perf_counter()
    initial=machine.observation()
    for index in range(25):
        check_frame(machine.step(schedule[index]),fixture,index)
    checkpoint=machine.save()
    for index in range(25,60):
        check_frame(machine.step(schedule[index]),fixture,index)
    reference60=machine.save()
    machine.restore(checkpoint)
    for index in range(25,60):
        check_frame(machine.step(schedule[index]),fixture,index)
    for page,raw in reference60.pages.items():
        require(bytes(machine.mu.mem_read(page,4096))==raw,
                "Checkpoint replay differs outside typed observations")
    machine.restore(checkpoint)
    for index in range(25,50):
        check_frame(machine.step(other.metadata["scenarioControlSchedule"][index]),other,index)
    require(machine.observation()["tick"]==50,"Branch time is incorrect")
    machine.reset()
    require(machine.observation()==initial,"Reset observation differs")
    for index in range(10):
        check_frame(machine.step(schedule[index]),fixture,index)
    saved=machine.save()
    rejected=0
    for controls in ([float("nan"),0,0],[0,0,2],[True,0,0],[0,0],None):
        if controls is None:
            continue  # None is deliberately supported by the low-level reference replayer.
        try:
            machine.step(controls)
        except ValueError:
            rejected+=1
        else:
            raise AssertionError("Invalid control accepted")
        require(machine.frame==10 and not machine.failed,"Invalid controls changed state")
    try:
        machine.restore(replace(saved,owner=object()))
    except ValueError:
        rejected+=1
    else:
        raise AssertionError("Foreign checkpoint accepted")
    address=machine.metadata["manager"]+0x10  # A read dependency, never an explicit action write.
    page=address&~4095
    previous=machine.data[page]
    mask=bytearray(previous[0]);mask[address&4095]=0
    machine.data[page]=(bytes(mask),previous[1],previous[2])
    try:
        machine.step([1,0,0])
    except UncapturedStepError:
        rejected+=1
    else:
        raise AssertionError("Unobserved input accepted")
    require(machine.failed and machine.frame==10,"Incomplete step was accepted")
    try:
        machine.observation()
    except ValueError:
        rejected+=1
    else:
        raise AssertionError("Observation emitted after incomplete step")
    machine.data[page]=previous
    machine.restore(saved)
    check_frame(machine.step(schedule[10]),fixture,10)
    report=dict(schema="tm2020_owned_interactive_step_qualification_v1",
        fixtureSha256=fixture.sha256,brakeFixtureSha256=other.sha256,
        typedFramesCompared=count,allComparedFramesBitExact=True,
        checkpointAtTick=25,replayedCheckpointThroughTick=60,
        allCheckpointPagesCompared=True,alternativeBrakeBranchThroughTick=50,
        resetInitialObservationExact=True,resetFirst10TicksExact=True,
        rejectedCases=rejected,incompleteStepObservationDenied=True,
        restorationAfterIncompleteStepVerified=True,gameProcessAccessed=False,
        unknownSparseAccessRejected=True,arbitraryActionDomainQualified=False,
        fullSimulatorQualified=False,elapsedSeconds=time.perf_counter()-started)
    report["alternativeBranchObservedBytesPerFrame"]=sum(shared_mask)
    report["coverageGuardImplementation"]=machine.report["coverageGuardImplementation"]
    report["writeInitializationTracked"]=machine.initialize_writes
    if machine.native_guard is not None:
        report["nativeGuardCounters"]=machine.native_guard.counters()
        report["nativeGuardDllSha256"]=hashlib.sha256(machine.native_guard.path.read_bytes()).hexdigest()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    print("PASS OWNED_INTERACTIVE_STEP frames="+str(count)+" branch_rewind_reset_bit_exact=true")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-guard",type=Path)
    parser.add_argument("--initialize-writes",action="store_true")
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--brake-fixture",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    parser.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    parser.add_argument("--report",type=Path,required=True)
    run(parser.parse_args())
