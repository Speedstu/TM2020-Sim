"""Exercise the local JSON protocol against an actual owned physics fixture."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from force_worker_fixture import require


def main(args):
    requests=[dict(id=1,op="reset"),dict(id=2,op="step",controls=[1,0,0]),
              dict(id=3,op="save",name="one"),dict(id=4,op="step",controls=[1,0,0]),
              dict(id=5,op="restore",name="one"),dict(id=6,op="step",controls=[1,0,0]),
              dict(id=7,op="step",controls=[False,0,0]),dict(id=8,op="step",controls=None),
              dict(id=9,op="step",controls=[float("nan"),0,0]),dict(id=10,op="close")]
    command=[sys.executable,str(Path(__file__).with_name("serve_owned_step.py")),
        "--fixture",str(args.fixture),"--exe",str(args.exe)]
    if args.native_guard:command.extend(["--native-guard",str(args.native_guard)])
    result=subprocess.run(command,
        input="".join(json.dumps(r)+"\n" for r in requests),capture_output=True,text=True,timeout=60)
    require(result.returncode==0,"Owned JSON server failed: "+result.stderr)
    replies=[json.loads(line) for line in result.stdout.splitlines()]
    require(len(replies)==len(requests) and all(r["id"]==(None if q["id"]==9 else q["id"]) for r,q in zip(replies,requests)),
            "JSON reply count or IDs differ")
    require(all(r["ok"] for r in replies[:6]) and replies[9]["ok"],"Valid protocol operation failed")
    require(replies[3]["result"]==replies[5]["result"],"Restored JSON observation differs")
    require(all(not r["ok"] and not r["resetOrRestoreRequired"] for r in replies[6:9]),
            "Invalid action changed machine state")
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(schema="tm2020_owned_step_json_protocol_v1",requests=10,
        allValidRequestIdsMatched=True,invalidJsonReplyIdIsNull=True,
        rewindObservationBitExact=True,invalidActionRejected=True,
        nullControlRejected=True,nonfiniteJsonRejected=True,
        gameProcessAccessed=False,nativeGuardUsed=args.native_guard is not None,
        fullSimulatorQualified=False),indent=2)+"\n")
    print("PASS OWNED JSON PROTOCOL replies=10 rewind_state_exact=true invalid_controls_rejected=true")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-guard",type=Path)
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    main(parser.parse_args())
