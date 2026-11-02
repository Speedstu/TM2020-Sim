"""Build/install the SDK and execute an external consumer of the new trainer ABI."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pinned_build import ROOT
from force_worker_fixture import require


def main():
    build=ROOT/"native/build";dist=ROOT/"dist/sdk-windows-x64"
    consumer=ROOT/"cache/consumer-0.31-mingw"
    commands=[["cmake","--build",str(build),"-j","4"],
        ["ctest","--test-dir",str(build),"--output-on-failure"],
        ["cmake","--install",str(build),"--prefix",str(dist)],
        ["cmake","-G","MinGW Makefiles","-S",str(ROOT/"native/tests/consumer"),
         "-B",str(consumer),"-DCMAKE_PREFIX_PATH="+str(dist)],
        ["cmake","--build",str(consumer),"-j","4"],
        [str(consumer/"tm2020_consumer.exe")]]
    env=dict(os.environ);env["PATH"]=str(dist/"bin")+os.pathsep+env["PATH"]
    results=[];logs=[]
    for command in commands:
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=600)
        logs.append("COMMAND "+repr(command)+"\n"+result.stdout+result.stderr)
        require(result.returncode==0,"SDK qualification command failed:\n"+logs[-1])
        results.append(dict(arguments=command,exitCode=0,
            stdoutSha256=hashlib.sha256(result.stdout.encode()).hexdigest()))
    suite=subprocess.run(["ctest","--test-dir",str(build),"--show-only=json-v1"],capture_output=True,text=True,check=True)
    count=len(json.loads(suite.stdout)["tests"])
    artifacts={}
    for label,source,installed in (
        ("trainerHeader",ROOT/"native/include/tm2020/trainer.h",dist/"include/tm2020/trainer.h"),
        ("policyDll",build/"libtm2020_policy.dll",dist/"bin/libtm2020_policy.dll"),
        ("guardDll",build/"libtm2020_owned_unicorn_guard.dll",dist/"bin/libtm2020_owned_unicorn_guard.dll")):
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        require(digest==hashlib.sha256(installed.read_bytes()).hexdigest(),"Installed SDK artifact differs: "+label)
        artifacts[label]=digest
    report=dict(schema="tm2020_owned_training_installed_sdk_v1",sdkVersion="0.26.0",
        nativeSuiteTests=count,allTestsPassed=True,externalConsumerExecuted=True,
        externalConsumerTrainerSampleCancelVerified=True,artifacts=artifacts,commands=results,
        gameProcessAccessed=False,fullSimulatorQualified=False)
    recon=ROOT/"local/recon"
    (recon/"owned-training-sdk-checks.log").write_text("\n".join(logs))
    (recon/"owned-training-installed-sdk.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PASS INSTALLED SDK 0.26 native_tests="+str(count)+" external_trainer_consumer=true")


if __name__=="__main__":main()
