"""Read-only, same-seed source captures for a finite initial action grid.

Each capture executes the original code in a private emulator. Numeric bytes
are accepted only through actual read/write coverage; no game memory is changed.
"""
import argparse
import itertools
import json
from pathlib import Path
import subprocess
import sys
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture


def main(args):
    seed=load_original_step_fixture(args.seed)
    require(seed.metadata.get("sourceBodyActivationRestored") is True,
            "An observed source-activation seed is required")
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for index,controls in enumerate(itertools.product((0.0,0.5,1.0),(0.0,0.5,1.0),(-1.0,0.0,1.0))):
        folder=args.output/f"action-{index:02d}"
        folder.mkdir(exist_ok=True)
        schedule=folder/"schedule.json"
        raw=json.dumps([list(controls)])+"\n"
        if schedule.exists():require(schedule.read_text()==raw,"Retained schedule differs")
        else:schedule.write_text(raw)
        fixture=folder/"owned_control_schedule.tmstep"
        report=folder/"capture.json"
        if not fixture.exists() and not report.exists():
            command=[sys.executable,str(Path(__file__).with_name("capture_original_step.py")),
                "--exe",str(args.exe),"--source-binding",str(args.binding),
                "--initial-fixture",str(args.seed),"--steps","1","--control-schedule",str(schedule),
                "--normalize-initial-controls","--active-only","--vehicle-scene-pipeline",
                "--vehicle-pose-sync","--collision-query-cycle","--source-body-activation",
                "--output",str(folder),"--report",str(report)]
            if seed.metadata.get("sourceVelocityPreserved") is True:
                command.append("--preserve-source-velocity")
            result=subprocess.run(command,timeout=180)
            require(result.returncode==0,"Action source capture failed: "+str(index))
        retained=load_original_step_fixture(fixture)
        capture=json.loads(report.read_text())
        require(retained.metadata["scenarioControlSchedule"]==[list(controls)]
                and retained.metadata["initialSnapshotSeedFixtureSha256"]==seed.sha256
                and retained.metadata["initialControlsNormalizedToSeed"] is True
                and capture["sourceBindingRecheckedAfterCapture"] is True
                and capture["gameMemoryWritten"] is False
                and capture["codeExecutedInGame"] is False
                and capture["trials"][0]["completed"] is True,
                "Action capture failed provenance/completion checks")
        rows.append(dict(controls=controls,fixture=str(fixture.resolve()),sha256=retained.sha256))
        print("SOURCE ACTION INPUT",index+1,"/27",flush=True)
    args.report.write_text(json.dumps(dict(schema="tm2020_owned_action_source_captures_v1",
        seedFixtureSha256=seed.sha256,branches=rows,allBranchesCaptured=True,
        sourceProcessReadOnly=True,sourceSnapshotAtomic=False,
        completeSimulatorQualified=False),indent=2)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--binding",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    main(parser.parse_args())
