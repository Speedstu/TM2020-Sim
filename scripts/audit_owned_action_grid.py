"""Compare 27 initial-state action branches in the guarded emulator and native CPU.

This qualifies a finite grid at one state, never a continuous action domain.
"""
import argparse
import copy
import itertools
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

from force_worker_fixture import require
from owned_step_machine import open_owned_machine,UncapturedStepError
from original_step_fixture import load_original_step_fixture
from replay_original_step import write_scenario_fixture
from compile_original_step_fixture import compile_fixture


def main(args):
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32)
    source=machine.fixture
    require(source.metadata.get("sourceBodyActivationRestored") is True,
            "Grid qualification requires the source vehicle integration path")
    args.output.mkdir(parents=True,exist_ok=True)
    results=[]
    for index,controls in enumerate(itertools.product((0.0,0.5,1.0),(0.0,0.5,1.0),(-1.0,0.0,1.0))):
        machine.reset()
        name=f"action-{index:02d}"
        row=dict(controls=controls)
        try:
            actual=machine.step(list(controls))
            actual=bytes(a if mask else 0 for a,mask in zip(actual,source.trace_mask))
            final_pages={address:bytes(machine.mu.mem_read(address,4096)) for address in machine.data}
            meta=copy.deepcopy(source.metadata);meta["tickCount"]=1;meta["trace"]["frames"]=1
            fixture=args.output/(name+".tmstep")
            if not fixture.exists():
                write_scenario_fixture(args.fixture,fixture,meta,machine.data,final_pages,
                                       [actual],[list(controls)],None,0xa0)
            retained=load_original_step_fixture(fixture)
            require(retained.trace_expected==actual and retained.trace_mask==source.trace_mask
                    and retained.metadata["scenarioControlSchedule"]==[list(controls)]
                    and retained.metadata["counterfactualSourceFixtureSha256"]==source.sha256,
                    "Retained grid fixture differs")
            for address,page in retained.pages.items():
                require(page.initial==machine.data[address][1]
                        and page.expected==final_pages[address],"Retained grid memory differs")
            native_input=args.output/(name+".tmstepnative")
            compiled=args.output/(name+"-compiled.json")
            compile_fixture(SimpleNamespace(fixture=fixture,exe=args.exe,ntdll=args.ntdll,
                kernel32=args.kernel32,output=native_input,report=compiled,verify_existing=True))
            report=args.output/(name+"-native.json")
            native=subprocess.run([str(args.runner.resolve()),str(args.exe.resolve()),str(native_input.resolve()),
                                   str(report.resolve()),"--episodes","2"],capture_output=True,text=True,timeout=30)
            require(native.returncode==0,"Grid native differential failed: "+native.stderr)
            native_result=json.loads(report.read_text())
            require(native_result["allTypedPhysicalFramesBitExact"] is True
                    and native_result["totalTypedFramesCompared"]==2,"Grid comparison incomplete")
            row.update(completed=True,fixtureSha256=retained.sha256,nativeResetFramesCompared=2,
                       guardedUnknownInputRejected=False)
        except (UncapturedStepError,ValueError) as exc:
            row.update(completed=False,error=str(exc),guardedUnknownInputRejected=machine.failed)
        results.append(row)
        print("ACTION GRID",index+1,"completed="+str(row["completed"]).lower(),flush=True)
    passed=all(row["completed"] for row in results)
    args.report.write_text(json.dumps(dict(schema="tm2020_owned_initial_action_grid_v1",
        sourceFixtureSha256=source.sha256,branches=results,allBranchesCompared=passed,
        nativeComparedFrames=sum(row.get("nativeResetFramesCompared",0) for row in results),
        stateCount=1,gameProcessAccessed=False,continuousActionDomainQualified=False,
        generalRolloutDomainQualified=False,completeSimulatorQualified=False),indent=2)+"\n")
    require(passed,"Some initial action branches exceed the captured domain; see grid report")
    print("PASS OWNED ACTION GRID branches=27 native_frames=54 initial_states=1")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--runner",type=Path,required=True)
    parser.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    parser.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    main(parser.parse_args())
