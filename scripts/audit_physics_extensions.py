"""Audit original-instruction geometry extensions without promoting full physics."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tomllib
import xml.etree.ElementTree as ET
from force_worker_fixture import require
from pinned_build import ROOT,SHA
from headless_engine import UPSTREAM

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def main(args):
    args.run=args.run.resolve(strict=True);args.sdk=args.sdk.resolve(strict=True);args.output=args.output.resolve()
    require(not args.output.exists(),"Never overwrite extension audits")
    evidence={}
    def proof(path):
        evidence[path.relative_to(ROOT).as_posix()]=sha(path);return read(path)
    manifest=proof(ROOT/"local/recon/gearbox-extensions-0.34-source-v2.json")
    fork=ROOT/"cache/gearbox-extensions-0.34-v2";original=ROOT/"cache/gearbox-upstream-e0583ee"
    require(subprocess.check_output(["git","-C",str(original),"rev-parse","HEAD"],text=True).strip()==UPSTREAM,"Unknown upstream base")
    require(not subprocess.check_output(["git","-C",str(original),"status","--porcelain"],text=True).strip(),"Original source checkout changed")
    for item in manifest["changedFiles"]:
        require(sha(fork/item["path"])==item["extendedSha256"],"Extension source changed")
        if item["originalSha256"]:require(sha(original/item["path"])==item["originalSha256"],"Base source changed")
    lock=tomllib.loads((ROOT/"integrations/gearbox-extensions/Cargo.lock").read_text())
    for package in lock["package"]:
        if package["name"].startswith("gearbox-"):
            if package["name"]=="gearbox-engine":require("source" not in package,"Engine patch was not linked")
            else:require(package.get("source","").endswith("#"+UPSTREAM),"Mixed upstream versions")
    native=proof(args.run/"geometry-original/report.json");wake=proof(args.run/"wake-original/report.json")
    active=proof(args.run/"active-slot-original/report.json")
    rust=proof(args.run/"rust-oracle.json")
    require(native["exeSha256"]==wake["exeSha256"]==SHA,"Original executable mismatch")
    require(native["rayCases"]==native["sphereCases"]==native["fullMeshCases"]==20000
        and native["rayCppPortBitExact"] and native["originalInstructionsExecuted"],"Original geometry proof differs")
    require(all(rust[key] for key in ("rayFractionAndClassificationBitExact","sphereDefinedOutputBitsExact","sphereDispatcherExercised","fullMeshDefinedOutputBitsExact","wakeQueueLogicalBitsExact")),"Rust original-instruction proof failed")
    require(rust["fullMeshTrianglesPerCase"]==3 and rust["fullMeshGeneralEulerRotations"]
        and rust["equalFractionTieCasesIncluded"] and rust["wakeCases"]==20000
        and wake["requests"]==rust["wakeRequests"]==640000,"Oracle coverage differs")
    for cpp_key,rust_key in (("rayHits","rayHits"),("twoSidedHits","twoSidedHits"),("sphereHits","sphereHits"),
        ("fullMeshHits","fullMeshHits"),("fullMeshTwoSidedHits","fullMeshTwoSidedHits")):
        require(native[cpp_key]==rust[rust_key],"Native/Rust case accounting differs")
    require(wake["cppIndexBytesAndLogicalQueueBitExact"] and not wake["activationCallbackExercised"]
        and not rust["wakeActivationConsumerQualified"],"Wake enqueue overstates activation")
    require(active["exeSha256"]==SHA and active["cases"]==20000 and active["cppDefinedOutputsExact"]
        and active["originalInstructionsExecuted"] and not active["synchronizationQualified"]
        and not active["wakeConsumerQualified"],"Active list slice evidence differs")
    proof(ROOT/"local/recon/raycast-original-evidence-0.34-v2.json")
    proof(ROOT/"local/recon/wake-queue-original-evidence-0.34.json")
    cold=proof(args.run/"cold/report.json");cars=proof(args.run/"cars/report.json")
    require(len(cold["maps"])==3 and all(m["checkpointBranchBitExact"] and m["repeatRolloutBitExact"] and m["invalidCommandsRejected"]==4 for m in cold["maps"]),"Cold map regression differs")
    require(len(cars["cars"])==4 and cars["physicsExtensionSha256"]==manifest["physicsExtensionSha256"]
        and all(c["finished"] and c["mixedControlsExactAcrossReset"] and c["checkpointFutureExact"] for c in cars["cars"]),"Four-car engine matrix failed")
    identity=proof(args.run/"identity/report.json");gym=proof(args.run/"gym/report.json")
    require(identity["wrongIdentitiesRejected"]==2 and identity["acknowledgedExtensionAccepted"]
        and gym["officialCheckerPassed"] and gym["finishPartialRepeatTicks"]==1,"Protocol/Gym checks failed")
    proof(args.run/"asset-catalog.json")
    replay=proof(ROOT/"local/recon/extended-game-replays-v2/report.json")
    eligible=[r for r in replay["replays"] if r.get("ok")]
    require(len(replay["replays"])==23 and len(eligible)==21 and all(r["finishDeltaMs"]==0 for r in eligible),"Full replay regression differs")
    sdk=proof(args.sdk/"report.json");require(sdk["externalConsumerExecuted"] and sdk["raycastPublicKernelLinked"] and sdk["wakePublicKernelLinked"] and sdk["activeSlotKernelLinked"],"External SDK consumer missing")
    suite=args.run/"native-tests.xml";tree=ET.parse(suite).getroot()
    require(len(list(tree.iter("testcase")))==42 and not list(tree.iter("failure")) and not list(tree.iter("error")),"Native test suite failed")
    evidence[suite.relative_to(ROOT).as_posix()]=sha(suite)
    numeric=[]
    for path in [*sorted((args.run/"geometry-original").glob("*.cases")),*sorted((args.run/"wake-original").glob("*.cases")),*sorted((args.run/"active-slot-original").glob("*.cases"))]:
        numeric.append(dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
    unresolved=[]
    for package in ("engine","world"):
        for path in sorted((fork/"packages"/package/"src").rglob("*.rs")):
            for line_number,line in enumerate(path.read_text().splitlines(),1):
                if re.search(r"\b(todo|unimplemented)!",line):
                    unresolved.append(dict(path=path.relative_to(fork).as_posix(),line=line_number,expression=line.strip()))
    require(unresolved,"Full qualification needs independent review even when source markers disappear")
    project_files=[]
    sources=[*sorted((ROOT/"integrations/gearbox-extensions").glob("*")),
        *[ROOT/p for p in ("scripts/prepare_gearbox_extensions.py","scripts/headless_engine.py","scripts/headless_gym.py",
            "scripts/run-physics-extension-checks.ps1","native/src/recovered_raycast.cpp","native/include/tm2020/recovered_raycast.hpp",
            "native/src/recovered_activation.cpp","native/include/tm2020/recovered_activation.hpp",
            "native/tests/geometry_gap_oracle.cpp","native/tests/wake_queue_oracle.cpp","native/tests/active_slot_oracle.cpp","scripts/test_active_slot_slice.py")]]
    for path in sources:
        if path.is_file():project_files.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=sha(path)))
    host=ROOT/"cache/gearbox-extensions-target/release/tm2020-gearbox-extended-host.exe"
    require(sha(host)==cars["hostSha256"]==cold["maps"][0]["hostSha256"],"Extended host changed")
    result=dict(schema="tm2020_geometry_extensions_milestone_v1",researchVersion="0.34",exeSha256=SHA,
        upstreamRevision=UPSTREAM,physicsExtensionSha256=manifest["physicsExtensionSha256"],hostSha256=sha(host),
        nativeTests=42,geometryOriginalCases=60000,wakeOriginalRequests=640000,activeSlotOriginalSliceCases=20000,
        fourCarEngineMatrix=cars["cars"],originalGameOracleForAllCarsQualified=False,
        sourceGameProcessAccessed=False,openplanetUsed=False,completeExactSimulatorQualified=False,generalPolicyQualified=False,
        wakeActivationConsumerQualified=False,retainedUnimplementedSourceMarkers=len(unresolved),
        sourceMarkersAreNotAnExhaustiveCompletionSpecification=True,unimplementedSourceSites=unresolved,
        numericOracleFiles=numeric,projectFiles=project_files,evidence=evidence)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    if args.update_capabilities:
        path=ROOT/"local/framework-capabilities.json";caps=read(path)
        for key in ("completeStandaloneSimulatorQualified","completeSceneUpdateQualified","faithfulGeneralHeadlessRlQualified"):
            require(caps[key] is False,"Unexpected global completion flag")
        caps.update(schema="tm2020_framework_capabilities_v27",updatedUtc=datetime.now(timezone.utc).isoformat(),
            researchContinuation="0.34",nativeSuiteTests=42,externalPhysicsExtensionSha256=manifest["physicsExtensionSha256"],
            recoveredTriangleRaycastOriginalCases=20000,externalPatchedGeometryOriginalCases=60000,
            recoveredWakeEnqueueOriginalRequests=640000,recoveredWakeActivationConsumerQualified=False,
            recoveredActiveSlotOriginalSliceCases=20000,
            externalFourCarColdResetAndFinishVerified=True,externalFourCarIndependentPhysicsOracleQualified=False,
            note="Research 0.34 adds original-instruction-qualified two-sided raycasts and sphere/sphere collision to a separate Gearbox fork. Triangle, multi-triangle mesh and sphere outputs pass 60,000 cases; C++/Rust wake enqueue logic passes 640,000 original requests, while the later activation consumer remains unqualified. Sport/Snow/Rally/Desert finish the same cold test map with exact reset/rewind. The 21 recorded finish-time regressions still pass. SDK external consumer and 42 native tests pass. Complete exact physics and general race RL remain unqualified; no Openplanet runtime.")
        path.write_text(json.dumps(caps,indent=2)+"\n")
    print("PASS EXTENSION_MILESTONE geometry=60000 wake_requests=640000 native_tests=42 remaining_markers="+str(len(unresolved)))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("run","sdk","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--update-capabilities",action="store_true");main(p.parse_args())
