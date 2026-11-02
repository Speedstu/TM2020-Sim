"""Exercise native schedule rejection before any original procedure executes."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from force_worker_fixture import require


def main(args):
    raw=args.fixture.read_bytes()
    version=struct.unpack_from("<I",raw,8)[0]
    require(version in (6,7) and raw[:8]==b"TMSTNV"+str(version).encode()+b"\0",
            "Expected a valid version-6/7 source")
    at=12+128+8+struct.calcsize("<2Q4I2Q2I3I")
    require(struct.unpack_from("<I",raw,at+12)[0]==0xa0,"Source is not a command schedule")
    cases=[("steering_offset",at+12,"<I",0x1430,"Invalid steering command offset"),
           ("unowned_vehicle",at,"<Q",0x100000000,"Control override outside owned fixture pages"),
           ("horizon",at+8,"<I",1001,"Invalid control schedule horizon"),
           ("nonfinite_action",at+16,"<f",float("nan"),"Scheduled internal control outside [-1, 1]")]
    if version==7:
        pipeline_at=at+16+struct.unpack_from("<I",raw,at+8)[0]*12
        cases.extend([("pipeline_version",pipeline_at,"<I",5,"Unsupported scene pipeline version"),
                      ("pipeline_receiver",pipeline_at+4,"<Q",0x100000000,
                       "Scene pipeline receiver outside owned pages")])
    results=[]
    args.report.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="native-control-rejection-",dir=args.report.parent) as temp:
        for name,offset,fmt,value,message in cases:
            mutated=bytearray(raw);struct.pack_into(fmt,mutated,offset,value)
            fixture=Path(temp)/(name+".tmstepnative");fixture.write_bytes(mutated)
            result=subprocess.run([str(args.runner.resolve()),str(args.exe.resolve()),str(fixture),
                                   str(Path(temp)/(name+".json"))],capture_output=True,text=True,timeout=30)
            require(result.returncode==1 and message in result.stderr
                    and "TICK " not in result.stdout,"Native rejection failed: "+name)
            results.append(dict(case=name,rejectedBeforeStep=True))
        for value in ("0","10001","-1","1x"):
            result=subprocess.run([str(args.runner.resolve()),str(args.exe.resolve()),str(args.fixture.resolve()),
                                   str(Path(temp)/("bad-episode-"+value+".json")),"--episodes",value],
                                  capture_output=True,text=True,timeout=30)
            require(result.returncode==1 and "TICK " not in result.stdout
                    and "Reset episode count outside" in result.stderr,
                    "Invalid episode count was accepted: "+value)
            results.append(dict(case="episode_count_"+value,rejectedBeforeStep=True))
    args.report.write_text(json.dumps(dict(schema="tm2020_native_control_rejection_v1",
        cases=results,allRejectedBeforeStep=True,gameProcessAccessed=False),indent=2)+"\n")
    print("PASS NATIVE_CONTROL_REJECTION cases="+str(len(results))+" before_original_step=true")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runner",type=Path,required=True)
    p.add_argument("--exe",type=Path,required=True)
    p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    main(p.parse_args())
