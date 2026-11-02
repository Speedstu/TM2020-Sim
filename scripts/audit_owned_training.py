"""Audit the finite original-code training milestone without promoting global fidelity."""
import hashlib
import json
from pathlib import Path

from pinned_build import ROOT,SHA
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture,verify_original_step_images,SYNTHETIC

RECON=ROOT/"local/recon"
FINAL=RECON/"rest-history-training-canonical-v5/owned_control_schedule.tmstep"
CAPTURES=["rest-history-capture-"+n for n in ("coast","brake","left","right")]+[
    "rest-ppo-contact-frontier-corrected","ppo-frontier-canonical-v1/gap-00",
    "ppo-frontier-canonical-v1/gap-01","ppo-frontier-canonical-v2/gap-00",
    "ppo-frontier-canonical-v3/gap-00","ppo-frontier-canonical-v3/gap-01",
    "ppo-frontier-canonical-v4/gap-00"]


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    exe=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
    images=(exe,Path(r"C:\Windows\System32\ntdll.dll"),Path(r"C:\Windows\System32\kernel32.dll"))
    final=load_original_step_fixture(FINAL);verify_original_step_images(final,images)
    initial=load_original_step_fixture(RECON/"main-step-fixtures-source424-rest-500/owned_control_schedule.tmstep")
    added=synthetic_added=0
    for address,page in final.pages.items():
        old=initial.pages.get(address)
        for offset,mask in enumerate(page.mask):
            if mask and (old is None or not old.mask[offset]):
                added+=1
                if any(a<=address+offset<a+n for a,n in SYNTHETIC):synthetic_added+=1
    guard=ROOT/"native/build/libtm2020_owned_unicorn_guard.dll"
    adversarial=read(RECON/"owned-native-guard-adversarial.json")
    require(adversarial["casesPassed"]==14 and all(r["passed"] for r in adversarial["cases"])
            and adversarial["dllSha256"]==sha(guard),"Compiled guard proof is stale")
    for name,mode in (("owned-native-guard-interactive.json",False),
                      ("owned-native-guard-initialization-interactive.json",True)):
        proof=read(RECON/name)
        require(proof["typedFramesCompared"]==131 and proof["allComparedFramesBitExact"]
                and proof["allCheckpointPagesCompared"] and proof["writeInitializationTracked"]==mode
                and proof["nativeGuardDllSha256"]==sha(guard),"Branch/reset/initialized checkpoint proof differs")
    reference=read(RECON/"owned-training-final-reference.json")["fixtures"][0]
    require(reference["fixtureSha256"]==final.sha256 and reference["completed"]
            and reference["typedFramesCompared"]==500 and reference["allTypedPhysicalFramesBitExact"]
            and reference["allDataPagesBitExact"] and reference["nativeGuardDllSha256"]==sha(guard),
            "Final original-code reference does not pass")
    source_rows=[];native_frames=0
    for folder in CAPTURES+["rest-history-training-canonical-v5"]:
        path=RECON/folder
        fixture=load_original_step_fixture(path/"owned_control_schedule.tmstep")
        verify_original_step_images(fixture,images)
        native=read(path/"native-100.json")
        require(native["sourceFixtureSha256"]==fixture.sha256 and native["resetEpisodesCompared"]==100
                and native["allTypedPhysicalFramesBitExact"] and native["completeMainProcedureReturnedEveryFrame"]
                and not native["gameProcessAccessed"] and not native["originalGameInstructionsModified"],
                "Native reference comparison failed: "+folder)
        native_frames+=native["totalTypedFramesCompared"]
        if folder in CAPTURES:
            capture_path=(RECON/(folder+".json")) if folder.startswith("rest-") else path/"capture.json"
            capture=read(capture_path)
            require(capture["sourceBindingRecheckedAfterCapture"] and capture["readOnlyProcessHandle"]
                    and not capture["gameMemoryWritten"] and not capture["codeExecutedInGame"],
                    "Source capture provenance failed: "+folder)
        source_rows.append(dict(folder=folder,sha256=fixture.sha256,ticks=fixture.metadata["tickCount"]))
    total=steps=episodes=0;runs=[]
    for suffix,expected in (("",320),("-resume",40)):
        run=RECON/("owned-ppo-rest-history-canonical-v5"+suffix)
        report=read(run/"report.json")
        audit=read(RECON/("owned-ppo-canonical-v5"+suffix+"-physics-audit.json"))
        require(report["fixtureSha256"]==final.sha256 and report["totalAcceptedTransitions"]==expected
                and report["horizon"]==100 and report["actionRepeat"]==5
                and report["unknownStepsDiscarded"] and report["writeInitializationTracked"]
                and not report["generalRlQualified"] and not report["fullSimulatorQualified"],"Training scope/count differs")
        require(audit["trainingReportSha256"]==sha(run/"report.json") and audit["transitions"]==expected
                and all(row["allPhysicsDecisionsReplayed"] and row["rewardsExact"]
                        and row["allEpisodeBoundariesExact"] and row["bootstrapMaximumError"]==0
                        for row in audit["updates"]),"Physics/reward/bootstrap audit failed")
        for update in report["updates"]:
            behavior=read(run/f"update-{update['index']:04d}"/"behavior-audit.json")
            require(behavior["transitions"]==update["acceptedTransitions"] and behavior["all_rows_recomputed"]
                    and behavior["max_log_probability_error"]<=1e-7 and behavior["max_value_error"]<=1e-7,
                    "Native on-policy behavior audit failed")
            require(all(e["completed"] and e["error"] is None for e in update["episodes"]),"Training episode still fails")
            episodes+=len(update["episodes"])
        total+=expected;steps+=audit["originalPhysicsStepsReplayed"]
        runs.append(dict(suffix=suffix,transitions=expected,optimizerSteps=report["updates"][-1]["ppoMetrics"]["optimizer_steps"]))
    require(sha(RECON/"owned-ppo-rest-history-canonical-v5/update-0003/updated.tmppo")==
            sha(RECON/"owned-ppo-rest-history-canonical-v5-resume/update-0000/behavior.tmppo")
            and runs[1]["optimizerSteps"]>runs[0]["optimizerSteps"],"Checkpoint resume does not continue policy/optimizer")
    evaluation=read(RECON/"owned-ppo-canonical-v5-evaluation.json")
    require(evaluation["allTrialsCompleted"] and all(p["bitExactAcrossResets"] for p in evaluation["policies"])
            and not evaluation["trainingUpdatesPerformed"] and not evaluation["raceStrengthQualified"],"Evaluation scope differs")
    sdk=read(RECON/"owned-training-installed-sdk.json")
    require(sdk["sdkVersion"]=="0.26.0" and sdk["nativeSuiteTests"]==36 and sdk["allTestsPassed"]
            and sdk["externalConsumerExecuted"] and sdk["artifacts"]["guardDll"]==sha(guard),"Installed SDK proof differs")
    result=dict(schema="tm2020_owned_training_milestone_v1",executableSha256=SHA,finalFixtureSha256=final.sha256,
        finalDataPages=len(final.pages),addedInputBytesRelativeToRest500=added,
        addedSyntheticRuntimeInputBytes=synthetic_added,addedNonSyntheticInputBytes=added-synthetic_added,
        fixedReferenceNativeFramesCompared=native_frames,referenceCaptures=source_rows,
        onPolicyDecisionsIndependentlyAudited=total,originalTrainingPhysicsStepsReplayed=steps,
        completedShortTrainingEpisodes=episodes,nativePpoUpdates=sum(4 if not r["suffix"] else 1 for r in runs),
        nativeGuardAdversarialCases=14,nativeSuiteTests=36,installedSdkConsumerVerified=True,
        deterministicEvaluation=evaluation["policies"],beforeAfterRewardChange=evaluation["beforeAfterRewardChange"],
        allAcceptedTrajectoriesRewardsAndBootstrapsVerified=True,sourceSnapshotsAtomic=False,
        sourceGameProcessWritten=False,openplanetRuntimeRequired=False,
        completeWorldInitializationQualified=False,fullOuterSceneQualified=False,
        arbitraryActionDomainQualified=False,generalRlQualified=False,completeExactSimulatorQualified=False)
    (RECON/"owned-training-milestone-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print("PASS OWNED_TRAINING_MILESTONE decisions="+str(total)+" completed_short_episodes="+str(episodes)+" full_simulator=false")


if __name__=="__main__":main()
