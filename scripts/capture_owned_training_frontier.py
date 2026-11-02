"""Capture exact retained PPO failure histories using read-only source inputs.

Only one history per distinct first missing-byte address is captured. This is
working-set expansion, not a claim that the entire source world was serialized.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture,verify_original_step_images


def main(args):
    seed=load_original_step_fixture(args.seed)
    report=json.loads((args.training/"report.json").read_text())
    require(report["fixtureSha256"]==seed.sha256,"Training report belongs to another seed")
    require(report["unknownStepsDiscarded"] is True,"Failed transition handling is unqualified")
    args.output.mkdir(parents=True,exist_ok=True)
    repeat=report["actionRepeat"];seen=set();rows=[]
    for update in report["updates"]:
        decisions=json.loads((args.training/f"update-{update['index']:04d}"/"physics-decisions.json").read_text())
        for episode in update["episodes"]:
            gap=episode.get("firstUncapturedAccess")
            if not gap or gap["address"] in seen:continue
            seen.add(gap["address"])
            require(len(seen)<=32,"Source frontier capture bound reached")
            accepted=[d for d in decisions if d["episode"]==episode["episode"]]
            require(len(accepted)==episode["acceptedDecisions"],"Accepted decision count differs")
            controls=[]
            for index,decision in enumerate(accepted):
                require(decision["index"]==index and decision["before"]["tick"]==len(controls)
                        and decision["after"]["tick"]==len(controls)+repeat,
                        "Decision sequence is discontinuous")
                controls.extend([decision["controls"]]*repeat)
            require(episode["failedControls"] is not None,"Failed action was not retained")
            controls.extend([episode["failedControls"]]*repeat)
            require(1<=len(controls)<=1000,"Source history horizon bound")
            folder=args.output/f"gap-{len(rows):02d}"
            folder.mkdir(exist_ok=True)
            plan=folder/"controls.json"
            raw=json.dumps(controls,separators=(",",":"))+"\n"
            if plan.exists():require(plan.read_text()==raw,"Existing frontier plan differs")
            else:plan.write_text(raw)
            fixture=folder/"owned_control_schedule.tmstep"
            capture=folder/"capture.json"
            if not fixture.exists() and not capture.exists():
                command=[sys.executable,str(Path(__file__).with_name("capture_original_step.py")),
                    "--exe",str(args.exe),"--source-binding",str(args.binding),
                    "--initial-fixture",str(args.seed),"--steps",str(len(controls)),
                    "--control-schedule",str(plan),"--normalize-initial-controls","--active-only",
                    "--vehicle-scene-pipeline","--vehicle-pose-sync","--collision-query-cycle",
                    "--source-body-activation","--preserve-source-velocity",
                    "--output",str(folder),"--report",str(capture)]
                result=subprocess.run(command,timeout=1800)
                require(result.returncode==0,"Source frontier capture failed")
            retained=load_original_step_fixture(fixture)
            verify_original_step_images(retained,(args.exe,Path(r"C:\Windows\System32\ntdll.dll"),
                                                 Path(r"C:\Windows\System32\kernel32.dll")))
            proof=json.loads(capture.read_text())
            require(retained.metadata["initialSnapshotSeedFixtureSha256"]==seed.sha256
                    and retained.metadata["scenarioControlSchedule"]==controls
                    and proof["sourceBindingRecheckedAfterCapture"] is True
                    and proof["gameMemoryWritten"] is False
                    and proof["codeExecutedInGame"] is False,"Frontier capture provenance failed")
            rows.append(dict(fixture=str(fixture.resolve()),sha256=retained.sha256,
                update=update["index"],episode=episode["episode"],ticks=len(controls),
                targetedAccess=gap))
    require(rows,"No sparse input frontier found")
    args.report.write_text(json.dumps(dict(schema="tm2020_ppo_frontier_source_captures_v1",
        seedFixtureSha256=seed.sha256,captures=rows,sourceReadOnly=True,
        sourceSnapshotAtomic=False,completeWorldQualified=False),indent=2)+"\n")
    print("SOURCE PPO FRONTIERS CAPTURED",len(rows))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("seed","training","exe","binding","output","report"):
        p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
