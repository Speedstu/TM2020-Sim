"""Install the research SDK separately and execute a real external C++ consumer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from force_worker_fixture import require
from pinned_build import ROOT

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main(args):
    require(not args.output.exists() and not args.prefix.exists() and not args.build.exists(),"Research SDK verification uses new output/install/build directories")
    args.output.mkdir(parents=True);logs=[];commands=[]
    env=dict(os.environ);env["PATH"]=str(args.prefix.resolve()/"bin")+os.pathsep+env["PATH"]
    for command in (["cmake","--install",str(ROOT/"native/build"),"--prefix",str(args.prefix.resolve())],
        ["cmake","-S",str(ROOT/"native/tests/consumer"),"-B",str(args.build.resolve()),"-G","MinGW Makefiles","-DCMAKE_PREFIX_PATH="+str(args.prefix.resolve())],
        ["cmake","--build",str(args.build.resolve()),"--parallel","4"],
        [str(args.build.resolve()/"tm2020_consumer.exe")]):
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=600)
        logs.append("COMMAND "+repr(command)+"\n"+result.stdout+result.stderr)
        (args.output/"commands.log").write_text("\n".join(logs))
        require(result.returncode==0,"Research SDK command failed: "+logs[-1])
        commands.append(dict(command=command,exitCode=0))
    files=[]
    for relative in ("include/tm2020/recovered_raycast.hpp","include/tm2020/recovered_activation.hpp","lib/libtm2020_sdk.a","bin/libtm2020_policy.dll"):
        installed=args.prefix/relative
        original=ROOT/("native/"+relative if relative.startswith("include/") else "native/build/"+installed.name)
        require(sha(installed)==sha(original),"Installed SDK file changed: "+relative)
        files.append(dict(path=str(installed.resolve()),sha256=sha(installed)))
    report=dict(schema="tm2020_geometry_research_sdk_consumer_v1",sdkBaseVersion="0.26.0",researchVersion="0.35",
        externalConsumerExecuted=True,raycastPublicKernelLinked=True,sphereRayPublicKernelLinked=True,
        wakePublicKernelLinked=True,activeSlotKernelLinked=True,
        trainerCAbiSampleCancelVerified=True,installedFiles=files,commands=commands,
        sourceGameProcessAccessed=False,completeExactSimulatorQualified=False)
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PASS RESEARCH_SDK installed raycast/wake kernels and external trainer consumer")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("output","prefix","build"):p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
