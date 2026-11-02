"""Publish audited bounded training capabilities while retaining global false gates."""
import json
from datetime import datetime,timezone
from audit_owned_training import main as audit
from pinned_build import ROOT
from force_worker_fixture import require


def main():
    audit()
    proof=json.loads((ROOT/"local/recon/owned-training-milestone-audit.json").read_text())
    path=ROOT/"local/framework-capabilities.json"
    caps=json.loads(path.read_text())
    for key in ("arbitraryActionSimulatorQualified","completeStandaloneSimulatorQualified","completeSceneUpdateQualified"):
        require(caps[key] is False,"Unexpected global qualification gate")
    caps.update(schema="tm2020_framework_capabilities_v25",updatedUtc=datetime.now(timezone.utc).isoformat(),
        sdkNativeReleaseVersion="0.26.0",researchContinuation="0.31",nativeSuiteTests=36,
        compiledUnicornInstructionAndSourceByteGuardVerified=True,
        compiledUnicornGuardAdversarialCasesVerified=proof["nativeGuardAdversarialCases"],
        generatedByteInitializationCheckpointResetVerified=True,
        ownedTrainingSceneInputBytesAdded=proof["addedInputBytesRelativeToRest500"],
        ownedTrainingAdditionalFixedReferenceResetFramesVerified=proof["fixedReferenceNativeFramesCompared"],
        nativePpoTrainerCAbiVersion=1,installedNativePpoTrainerConsumerVerified=True,
        boundedOriginalScenePpoDecisionsAudited=proof["onPolicyDecisionsIndependentlyAudited"],
        boundedOriginalScenePpoPhysicsTicksReplayed=proof["originalTrainingPhysicsStepsReplayed"],
        boundedOriginalScenePpoCompletedOneSecondEpisodes=proof["completedShortTrainingEpisodes"],
        boundedOriginalScenePpoUpdates=proof["nativePpoUpdates"],
        boundedOriginalScenePpoCheckpointResumeVerified=True,
        boundedOriginalScenePpoRewardsAndBootstrapRecomputed=True,
        boundedOriginalScenePolicyBeatsFullThrottleBaseline=False,
        faithfulGeneralHeadlessRlQualified=False,
        note="SDK 0.26.0 + research 0.31: compiled Unicorn guards, generated-byte checkpoint tracking and a native PPO trainer C ABI now support 18 completed one-second owned-scene episodes. All 360 decisions (1,800 original physics ticks), rewards, bootstrap values and behavior likelihoods are independently audited, including checkpoint resume. The 500-tick reference and 204,000 additional repeated native reference frames pass. The local learned policy improves its forward-displacement scalar but remains below full throttle. These bounded owned-context experiments do not qualify complete world initialization, the full outer scene, all surfaces/vehicles/actions or faithful general race RL. No Openplanet runtime dependency.")
    path.write_text(json.dumps(caps,indent=2)+"\n")
    print("UPDATED BOUNDED TRAINING CAPABILITIES complete_simulator=false general_rl=false")


if __name__=="__main__":main()
