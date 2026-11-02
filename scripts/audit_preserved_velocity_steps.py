"""Audit the two retained source-velocity episodes without invented push speed."""
import hashlib
import json
import math
import struct
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture
from pinned_build import ROOT,SHA


def main():
    recon=ROOT/"local/recon";rows=[];seed=None
    for suffix,ticks in (("source424-rest-throttle",100),("source424-rest-500",500)):
        folder=recon/("main-step-fixtures-"+suffix)
        fixture=load_original_step_fixture(folder/"owned_control_schedule.tmstep")
        m=fixture.metadata
        capture=json.loads((recon/("original-step-capture-"+suffix+".json")).read_text())
        native=json.loads((folder/"native-1000.json").read_text())
        offline=json.loads((recon/("original-step-offline-"+suffix+".json")).read_text())["fixtures"][0]
        require(m["sourceVelocityPreserved"] is True and capture["sourceVelocityPreserved"] is True
                and m["sourceBodyActivationRestored"] is True and m["postStepPipeline"]["version"]==4
                and m["tickCount"]==ticks,"Source-velocity capture mode/horizon differs")
        require(capture["sourceBindingRecheckedAfterCapture"] is True
                and capture["atomicSnapshot"] is False and capture["gameMemoryWritten"] is False
                and capture["codeExecutedInGame"] is False
                and capture["trials"][0]["sparseFixtureSha256"]==fixture.sha256,"Source capture provenance differs")
        require(native["sourceFixtureSha256"]==fixture.sha256
                and native["nativeFixtureSha256"]==hashlib.sha256((folder/"schedule.tmstepnative").read_bytes()).hexdigest()
                and native["allTypedPhysicalFramesBitExact"] is True
                and native["resetEpisodesCompared"]==1000 and native["totalTypedFramesCompared"]==ticks*1000
                and native["syntheticArenaBytesClearedPerReset"]==0x9000000,"Native source-velocity trace differs")
        require(offline["fixtureSha256"]==fixture.sha256 and offline["completed"] is True
                and offline["allTypedPhysicalFramesBitExact"] is True and offline["allDataPagesBitExact"] is True
                and offline["typedFramesCompared"]==ticks and not offline["faultReasons"]
                and offline["error"] is None,"Strict source-velocity reference replay differs")
        before=m["rigidBefore"][m["selectedBodyIndex"]]
        at=m["stateAddress"]+m["selectedBodyIndex"]*88+0x40
        initial=fixture.pages[at&~4095].initial[at&4095:(at&4095)+12]
        require(initial==struct.pack("<3f",*before["linearVelocity"])
                and math.sqrt(sum(v*v for v in before["linearVelocity"]))<.02,
                "Retained initial velocity is no longer the near-stationary source value")
        if seed is not None:
            require(m["initialSnapshotSeedFixtureSha256"]==seed.sha256,"Extended episode has another seed")
            for address,page in fixture.pages.items():
                previous=seed.pages.get(address)
                if previous is not None:
                    require(all(not (a and b) or page.initial[i]==previous.initial[i]
                                for i,(a,b) in enumerate(zip(page.mask,previous.mask))),
                            "Extended episode changed an observed seeded input")
            require(fixture.trace_expected[:len(seed.trace_expected)]==seed.trace_expected
                    if fixture.trace_mask==seed.trace_mask else
                    all(not a or not b or fixture.trace_expected[f*m["trace"]["frameBytes"]+i]
                        ==seed.trace_expected[f*m["trace"]["frameBytes"]+i]
                        for f in range(100) for i,(a,b) in enumerate(zip(fixture.trace_mask,seed.trace_mask))),
                    "Extended episode changed the first 100 shared observed frames")
        else:seed=fixture
        counts=offline["originalProcedureEntryCounts"]
        rows.append(dict(name=suffix,fixtureSha256=fixture.sha256,ticks=ticks,
            nativeResetFramesCompared=ticks*1000,initialLinearVelocity=before["linearVelocity"],
            originalVehiclePoseSubsteps=counts["0x14ff9d0"],
            originalContactAbsorberCalls=counts["0x843920"],
            groundedEngineEntries=offline["wheelFlagsAtEngineUpdateEntry"]["anyNonzeroWheelFlagSamples"]))
    result=dict(schema="tm2020_preserved_source_velocity_audit_v1",executableSha256=SHA,
        captures=rows,nativeResetFramesCompared=600000,constructedVelocityOverrideApplied=False,
        sourceSnapshotAtomic=False,completeSceneUpdateQualified=False,
        completeStandaloneSimulatorQualified=False,fullTrackmaniaHeadlessRLReady=False)
    (recon/"preserved-source-velocity-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print("PASS PRESERVED SOURCE VELOCITY 100/500 ticks; 600000 native reset frames")


if __name__=="__main__":main()
