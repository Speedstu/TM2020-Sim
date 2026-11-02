"""Audit bounded 0.32/0.33 evidence and retain the unqualified global gates."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from force_worker_fixture import require
from pinned_build import ROOT,SHA
from headless_engine import UPSTREAM

RECON=ROOT/"local/recon"
def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args):
    require(not args.output.exists(),"Never overwrite a sealed milestone audit")
    evidence={}
    def proof(relative):
        path=RECON/relative;evidence[str(path.relative_to(ROOT)).replace("\\","/")]=sha(path);return read(path)
    require(sha(Path(r"D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe"))==SHA,"Game image changed")
    cold=proof("headless-cold-validation-v3/report.json")
    host=ROOT/"cache/gearbox-host-target/release/tm2020-gearbox-host.exe";host_sha=sha(host)
    provenance=proof("headless-build-provenance-v1.json")
    require(provenance["upstreamRevision"]==UPSTREAM and provenance["upstreamCheckoutUnmodified"]
        and all(sha(Path(f["path"]))==f["sha256"] for f in provenance["projectFiles"]+provenance["replays"]+provenance["bcDatasetFiles"]),"Build/source/replay provenance changed")
    require(len(cold["maps"])==3 and all(m["coldLoaded"] and m["checkpointBranchBitExact"]
        and m["resetBitExact"] and m["repeatRolloutBitExact"] and m["observationCount"]==233
        and m["invalidCommandsRejected"]==4 and m["hostSha256"]==host_sha for m in cold["maps"]),"Cold engine proof differs")
    require(any(m["finished"] and m["finishTimeMs"]==17406 for m in cold["maps"]),"Reference finish absent")
    gym=proof("headless-gym-final-v1/report.json")
    require(gym["officialCheckerPassed"] and gym["postFinishStepRejectedWithoutMutation"]
        and gym["finishPartialRepeatTicks"]==1 and gym["truncationRepeatTicks"]==[5,2],"Gym boundary proof differs")
    source=proof("outer-scene-9696-native-100-v1/result.json")
    require(source["independentLiveOracleTicks"]==100 and source["sourceDebuggerCleanlyDetached"]
        and all(r["rigidAfterMatched"] and r["forceAfterMatched"] for r in source["livePhysicalFrameChecks"])
        and len(source["livePhysicalFrameChecks"])==100,"Independent original-game oracle differs")
    offline=proof("outer-scene-9696-native-100-v1/offline-replay-strict.json")["fixtures"][0]
    require(offline["typedFramesCompared"]==100 and offline["allTypedPhysicalFramesBitExact"]
        and offline["allDataPagesBitExact"] and offline["completed"],"Original outer-scene offline replay differs")
    outer=proof("outer-scene-ppo-v2/physics-audit.json")
    require(outer["transitions"]==20 and outer["originalPhysicsStepsReplayed"]==100,"Bounded outer PPO audit differs")
    train=proof("headless-ppo-v3/report.json");audit=proof("headless-ppo-v3/physics-audit/report.json")
    require(train["hostSha256"]==host_sha and train["totalAcceptedTransitions"]==audit["transitions"]==8000
        and audit["engineTicksReplayed"]==40000 and audit["trainingReportSha256"]==sha(RECON/"headless-ppo-v3/report.json"),"Native PPO physics proof differs")
    require(all(u["behaviorAudit"]["all_rows_recomputed"] and u["behaviorAudit"]["max_log_probability_error"]==0
        and u["behaviorAudit"]["max_value_error"]==0 and all(e["error"] is None for e in u["episodes"])
        for u in train["updates"]),"Native behavior audit failed")
    old=proof("headless-ppo-v2/report.json")
    require([u["updatedModelSha256"] for u in old["updates"]]==[u["updatedModelSha256"] for u in train["updates"]],"Fresh host rebuild changed seeded PPO models")
    resume=proof("headless-ppo-resume-v2/report.json");resume_audit=proof("headless-ppo-resume-v2/physics-audit/report.json")
    require(resume["totalAcceptedTransitions"]==resume_audit["transitions"]==1000
        and resume_audit["engineTicksReplayed"]==5000 and resume["initialCheckpointSha256"]==sha(RECON/"headless-ppo-v3/update-0003/training.checkpoint")
        and resume["updates"][0]["ppoMetrics"]["optimizer_steps"]>train["updates"][-1]["ppoMetrics"]["optimizer_steps"],"Resume did not preserve native optimizer")
    evaluation=proof("headless-ppo-v3/evaluation/report.json")
    require(all(p["deterministicReset"] and p["completed"] for m in evaluation["maps"] for p in m["policies"]),"Evaluation incomplete")
    before=sum(p["finished"] for m in evaluation["maps"] for p in m["policies"] if p["name"]=="before")
    after=sum(p["finished"] for m in evaluation["maps"] for p in m["policies"] if p["name"]=="after")
    require(before==1 and after==0,"Evaluation interpretation needs review")
    bc=proof("headless-bc-v1/report.json");bc_eval=proof("headless-bc-v1/evaluation/report.json")
    require(not bc["testUsedForSelection"] and all(not p["finished"] for m in bc_eval["maps"] for p in m["policies"] if p["name"]=="candidate"),"BC evaluation interpretation differs")
    replays=[]
    for relative in ("gearbox-game-replay-comparison-v2/report.json","gearbox-game-corpus-comparison-v1/report.json"):
        replays.extend(proof(relative)["replays"])
    exact=[r for r in replays if r.get("ok") and r.get("finishDeltaMs")==0]
    require(len(replays)==23 and len(exact)==21,"Replay corpus accounting changed")
    require(all(r["fixedPostStepTimestampHypothesis"]["offsetMs"]==10 and not r["timestampsFitted"]
        and not r["fixedPostStepTimestampHypothesis"]["offsetFitted"]
        and r["fixedPostStepTimestampHypothesis"]["positionMaximumMetres"]<.001 for r in exact),"Fixed-step visual comparison changed")
    partial=proof("gearbox-replay-denied-partial-v1/report.json")["replays"][0]
    require(not partial["ok"] and "incomplete replay input history" in partial["error"],"Partial replay must be denied")
    unsupported=proof("gearbox-unsupported-car-diagnostic-v1/report.json")["replays"][0]
    require(not unsupported["ok"] and "BayCar" in unsupported["error"] and "unsupported session car" in unsupported["error"],"Unsupported car diagnostic changed")
    exact_checkpoint_histories=sum(r["recordedCheckpointsMs"]==r["simulatedCheckpointsMs"] for r in exact)
    values=proof("public-physics-2026-10-28/numeric-comparison-v2.json")
    require(values["matchedNumericValues"]==len(values["entries"])==20,"Public numeric values differ")
    manifest=proof("public-physics-2026-10-28/source-manifest.json")
    require(len(manifest["files"])==35 and all(sha(RECON/"public-physics-2026-10-28"/f["localPath"])==f["sha256"] for f in manifest["files"]),"Public source evidence changed")
    assets=proof("installed-vehicle-assets-v1/report.json");asset_files=[]
    require(len(assets["cars"])==4 and sum(c["tuningCount"] for c in assets["cars"])==52,"Installed car decoding differs")
    for car in assets["cars"]:
        for field in ("rawTuningLocalFile","decodedLocalFile"):
            path=RECON/"installed-vehicle-assets-v1"/car[field]
            asset_files.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path),localOnly=True))
    suite_path=RECON/"headless-0.33-ctest.xml";suite=ET.parse(suite_path).getroot()
    cases=list(suite.iter("testcase"));require(len(cases)==41 and not list(suite.iter("failure")) and not list(suite.iter("error")),"Native test suite failed")
    evidence[str(suite_path.relative_to(ROOT)).replace("\\","/")]=sha(suite_path)
    for name,digest in (("trackmania2020-re-source-0.26.0.zip","f4874fd8c347bab498da8ee7d2fa8d149176f0d4eec7975083b4882309fe7bb8"),
        ("trackmania2020-sdk-windows-x64-0.26.0.zip","be628dafbbc15d5589bca6d6bcb1c68edbf322fe8f3109ce5a25ede100e3fbe0")):
        require(sha(ROOT/"backups"/name)==digest,"Historical release archive changed")
    result=dict(schema="tm2020_headless_milestone_audit_v1",researchVersion="0.33",exeSha256=SHA,
        upstreamRevision=UPSTREAM,hostSha256=host_sha,nativeTests=41,coldMaps=3,observations=233,
        independentOriginalOuterSceneOracleTicks=100,boundedOriginalOuterScenePpoDecisions=20,
        headlessAcceptedPpoTransitions=8000,headlessPpoPhysicsTicksReplayed=40000,
        additionalResumeTransitions=1000,additionalResumePhysicsTicksReplayed=5000,
        seededModelsIdenticalAcrossHostRebuild=True,replayFilesExamined=23,exactRecordedFinishTimes=21,
        exactRecordedCheckpointHistories=exact_checkpoint_histories,
        exactFinishUniqueMaps=len({r["mapUid"] for r in exact}),
        sameTimestampVisualMaximumMetres=max(r["positionMaximumMetres"] for r in exact),
        fixedPlus10MsHypothesisVisualMaximumMetres=max(r["fixedPostStepTimestampHypothesis"]["positionMaximumMetres"] for r in exact),
        visualTimestampSemanticsIndependentlyQualified=False,unsupportedRecordedCar="BayCar",
        partialReplayColdRunDenied=True,assetCarsDecoded=4,assetTuningsDecoded=52,privateAssetFiles=asset_files,
        publicSourcesVerified=35,publicNumericByteMatches=20,ppoCandidateRejected=True,bcCandidateRejected=True,
        liveDeploymentPerformed=False,sdkNativeReleaseVersion="0.26.0",gameRuntimeRequired=False,openplanetUsed=False,
        completeExactSimulatorQualified=False,generalPolicyQualified=False,raceStrengthQualified=False,evidence=evidence)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    if args.update_capabilities:
        path=ROOT/"local/framework-capabilities.json";caps=read(path)
        for key in ("completeStandaloneSimulatorQualified","completeSceneUpdateQualified","faithfulGeneralHeadlessRlQualified"):
            require(caps[key] is False,"Unexpected global gate")
        caps.update(schema="tm2020_framework_capabilities_v26",updatedUtc=datetime.now(timezone.utc).isoformat(),
            researchContinuation="0.33",nativeSuiteTests=41,externalAssetLoadedColdBackendValidated=True,
            externalAssetBackendUpstreamRevision=UPSTREAM,externalAssetColdMapsValidated=3,
            externalAssetCarTuningsDecoded=52,externalAssetRecordedReplayFinishTimesExact=21,
            externalAssetRecordedReplayMaps= result["exactFinishUniqueMaps"],externalAssetAcceptedPpoTransitionsAudited=9000,
            externalAssetPpoPhysicsTicksReplayed=45000,externalAssetPpoCandidateRaceEvaluationPassed=False,
            originalOuterSceneIndependentLiveRigidForceTicksMatched=100,originalOuterSceneBoundedPpoDecisionsAudited=20,
            fullTrackmaniaHeadlessRLReady=False,
            note="SDK 0.26.0 + research 0.33: a separately licensed pinned Gearbox process cold-loads installed assets/maps, exposes Gymnasium and our native PPO. Three cold-map reset/rewind tests pass; 21 recorded finishes on 19 maps match to the millisecond. A fixed +10 ms post-step timestamp hypothesis reduces visual-position residuals below 1 mm; this is not an independent bit-exact physical oracle. BayCar is unsupported and a partial-input replay is explicitly denied. Four cars/52 tuning sets are decoded locally. Native PPO has 9,000 independently replayed transitions including resume; learned candidates fail race evaluation and are not deployed. The separate original-code outer-scene backend retains its 100-tick live rigid/force oracle. Full exact physics and general race RL remain unqualified; no Openplanet runtime.")
        path.write_text(json.dumps(caps,indent=2)+"\n")
    print("PASS HEADLESS_MILESTONE",len(exact),"exact finish times; 9000 PPO transitions audited; global exact/general gates false")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True)
    p.add_argument("--update-capabilities",action="store_true");main(p.parse_args())
