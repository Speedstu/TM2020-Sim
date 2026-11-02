"""Cross-check restart capture, numeric seed provenance, resets and scene scope."""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture
from pinned_build import ROOT,SHA


def audit(args):
    recon=ROOT/"local/recon"
    def read(name):return json.loads((recon/name).read_text())
    seed=load_original_step_fixture(recon/"main-step-fixtures-v6-pedals/owned_control_schedule.tmstep")
    plans=[("mixed-300","main-step-fixtures-v6-mixed-300",300,0,
            "original-step-capture-v6-mixed-300.json","original-step-wheel-diagnostics-v6-mixed-300.json",
            "reset-cleared-1000-result.json"),
           ("pose-sync","main-step-fixtures-posesync-pedals",100,3,
            "original-step-capture-posesync-pedals.json","original-step-offline-posesync-pedals.json","native-1000.json"),
           ("query-cycle","main-step-fixtures-querycycle-pedals",100,4,
            "original-step-capture-querycycle-pedals.json","original-step-offline-querycycle-pedals.json","native-1000.json"),
           ("source-activation","main-step-fixtures-sourceactivation-pedals",100,4,
            "original-step-capture-sourceactivation-pedals.json","original-step-offline-sourceactivation-pedals.json","native-1000.json"),
           ("source-activation-mixed","main-step-fixtures-sourceactivation-mixed-300",300,4,
            "original-step-capture-sourceactivation-mixed-300.json","original-step-offline-sourceactivation-mixed-300.json","native-1000.json")]
    results=[]
    for name,folder,ticks,pipeline_version,capture_name,offline_name,native_name in plans:
        fixture=load_original_step_fixture(recon/folder/"owned_control_schedule.tmstep")
        m=fixture.metadata
        current_seed=load_original_step_fixture(recon/"main-step-fixtures-sourceactivation-pedals/owned_control_schedule.tmstep") if name=="source-activation-mixed" else seed
        capture,offline,native=read(capture_name),read(offline_name)["fixtures"][0],read(folder+"/"+native_name)
        require(capture["sha256"]==SHA and capture["readOnlyProcessHandle"] is True
                and capture["gameMemoryWritten"] is False and capture["codeExecutedInGame"] is False
                and capture["sourceBindingRecheckedAfterCapture"] is True
                and capture["atomicSnapshot"] is False and capture["completePhysics"] is False,
                "Capture provenance or scope differs: "+name)
        require(m["initialSnapshotSeedFixtureSha256"]==current_seed.sha256
                and m["sourcePid"]==current_seed.metadata["sourcePid"]
                and m["sourceProcessCreationFiletime"]==current_seed.metadata["sourceProcessCreationFiletime"]
                and m["modules"]==current_seed.metadata["modules"]
                and m["tickCount"]==ticks and len(m["scenarioControlSchedule"])==ticks,
                "Seed/process/control cohort differs: "+name)
        activation=m.get("sourceBodyActivationRestored") is True
        allowed_changes={}
        if activation:
            observed=m["observedSourceBodyActivation"]
            require(observed==capture["observedSourceBodyActivation"]
                    and observed["modelWord50"]!=0 and (observed["sourceFlags"]&8)==0,
                    "Observed source no longer selects the fixed-body scene path")
            for address,raw in ((observed["modelAddress"]+0x50,struct.pack("<I",observed["modelWord50"])),
                                (observed["sourceFlagsAddress"],bytes([observed["sourceFlags"]]))):
                for offset,value in enumerate(raw):
                    at=address+offset;page=fixture.pages[at&~4095]
                    require(page.mask[at&4095] and page.initial[at&4095]==value,
                            "Restored source activation input differs")
                    allowed_changes[at]=value
        overlap=0;changed_activation=0
        for address,page in fixture.pages.items():
            if address not in current_seed.pages:continue
            previous=current_seed.pages[address]
            for offset,(a,b) in enumerate(zip(page.mask,previous.mask)):
                if a and b:
                    if page.initial[offset]!=previous.initial[offset]:
                        require(allowed_changes.get(address+offset)==page.initial[offset],
                                "Known seeded initial input changed without observed provenance")
                        changed_activation+=1
                    overlap+=1
        require(overlap>1000,"Insufficient known seed overlap")
        require(offline["fixtureSha256"]==fixture.sha256 and offline["completed"] is True
                and offline["allTypedPhysicalFramesBitExact"] is True
                and offline["typedFramesCompared"]==ticks and offline["allDataPagesBitExact"] is True
                and not offline["faultReasons"] and offline["error"] is None
                and offline["storedControlPlanReplayed"] is True,"Guarded offline comparison failed: "+name)
        native_input=recon/folder/"schedule.tmstepnative"
        require(native["sourceFixtureSha256"]==fixture.sha256
                and native["nativeFixtureSha256"]==hashlib.sha256(native_input.read_bytes()).hexdigest()
                and native["resetEpisodesCompared"]==1000 and native["totalTypedFramesCompared"]==ticks*1000
                and native["allTypedPhysicalFramesBitExact"] is True
                and native["syntheticArenaBytesClearedPerReset"]==0x9000000
                and native["fullHeadlessSimulatorQualified"] is False
                and native.get("selectedScenePipelineVersion",0)==pipeline_version,
                "Native reset comparison failed: "+name)
        synchronized=0
        if pipeline_version>=3:
            width=m["trace"]["frameBytes"];vehicle_offset=m["stateCount"]*88
            for frame in range(ticks):
                for state_at,vehicle_at,n in ((0x30,0x12e0,16),(0x24,0x12f0,12),
                                            (0x40,0x12fc,12),(0x4c,0x1308,12)):
                    at=vehicle_offset+vehicle_at
                    require(all(fixture.trace_mask[at:at+n]),"Unobserved synchronized state")
                    raw=fixture.trace_expected[frame*width:(frame+1)*width]
                    require(raw[state_at:state_at+n]==raw[at:at+n],"Vehicle state remains stale")
                synchronized+=1
        probes=offline["wheelFlagsAtEngineUpdateEntry"]
        if not activation:
            require(probes["samples"]==ticks,"Missing wheel-entry probes")
        substeps=0
        if activation:
            counts=offline["originalProcedureEntryCounts"]
            intervals=offline["vehiclePoseSubstepIntervalCountsByFrame"]
            require(set(intervals)=={str(i+1) for i in range(ticks)},"Missing adaptive interval samples")
            for values in intervals.values():
                dt=[(struct.unpack("<f",struct.pack("<I",int(bits,16)))[0],n) for bits,n in values.items()]
                require(all(math.isfinite(value) and 0<value<=0.011 and type(n) is int and n>0
                            for value,n in dt),"Invalid vehicle substep duration")
                require(abs(sum(value*n for value,n in dt)-struct.unpack("<f",struct.pack("<I",0x3c23d70b))[0])<1e-8,
                        "Vehicle substeps do not cover the constructed 10ms tick")
                substeps+=sum(n for _,n in dt)
            require(counts["0x14ff9d0"]==substeps and counts["0x14ffee0"]==substeps
                    and counts["0x15009d0"]==substeps and counts["0x1500140"]>0
                    and counts["0x843920"]>0 and probes["anyNonzeroWheelFlagSamples"]>1,
                    "Original source-activation contact/integration path was not exercised")
        results.append(dict(name=name,fixtureSha256=fixture.sha256,ticks=ticks,pipelineVersion=pipeline_version,
            seededInitialBytesCompared=overlap,bitExactNativeResetFrames=ticks*1000,
            synchronizedVehicleFrames=synchronized,wheelEntrySamplesWithAnyContact=probes["anyNonzeroWheelFlagSamples"],
            sourceBodyActivationPreserved=activation,seedActivationBytesExplicitlyChanged=changed_activation,
            vehicleAdaptiveSubsteps=substeps,
            contactAbsorberCalls=offline["originalProcedureEntryCounts"]["0x843920"],
            stepsPerSecondIncludingResetAndComparison=native["stepsPerSecondIncludingComparisonAndProgressOutput"]))
    interactive=read("owned-interactive-step-qualification.json")
    require(interactive["allComparedFramesBitExact"] is True and interactive["typedFramesCompared"]==131
            and interactive["restorationAfterIncompleteStepVerified"] is True
            and interactive["allCheckpointPagesCompared"] is True,"Interactive branch/rewind incomplete")
    rejection=read("native-pipeline-reset-rejection.json")
    require(rejection["allRejectedBeforeStep"] is True and len(rejection["cases"])==10,
            "Native rejection coverage missing")
    response=read("pedal-control-response-v6.json")
    require(response["physicalActionResponseObserved"] is True
            and response["firstNumericallyChangedKinematicTick"]==26,"Pedal response not established")
    result=dict(schema="tm2020_owned_step_continuation_audit_v1",executableSha256=SHA,
        captures=results,interactiveComparedFrames=131,sourceSnapshotAtomic=False,
        rawPlayerActionMappingQualified=False,completeSceneUpdateQualified=False,
        fullTireSlipDomainQualified=False,originalSourceVehicleContactPathExercised=True,
        arbitraryActionNativeSteppingQualified=False,
        completeStandaloneSimulatorQualified=False,fullTrackmaniaHeadlessRLReady=False,
        originalExecutableAndCapturedOsCohortRequired=True,gameProcessAccessedByAudit=False)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+"\n")
    print("PASS OWNED STEP AUDIT captures="+str(len(results))+" native_reset_frames="+
          str(sum(r["bitExactNativeResetFrames"] for r in results))+" complete_simulator=false")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report",type=Path,default=ROOT/"local/recon/owned-step-continuation-audit.json")
    audit(p.parse_args())
