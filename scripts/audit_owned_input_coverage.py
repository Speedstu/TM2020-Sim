"""Verify the fresh source branch, observed input union and finite action grid."""
import hashlib
import itertools
import json
import struct
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture
from pinned_build import ROOT,SHA
from merge_original_step_inputs import COHORT_FIELDS


def main():
    recon=ROOT/"local/recon"
    def read(name):return json.loads((recon/name).read_text())
    fixtures={}
    native_total=0
    for name,ticks in (("source424-pedals",100),("source424-mixed-300",300),("source424-input-union",300)):
        folder=recon/("main-step-fixtures-"+name)
        fixture=load_original_step_fixture(folder/"owned_control_schedule.tmstep")
        fixtures[name]=fixture
        native=read(folder.name+"/native-1000.json")
        offline=read("original-step-offline-"+name+".json")["fixtures"][0]
        require(fixture.metadata["sourceBodyActivationRestored"] is True
                and fixture.metadata["postStepPipeline"]["version"]==4
                and fixture.metadata["tickCount"]==ticks,"Incorrect source vehicle branch/horizon")
        require(native["sourceFixtureSha256"]==fixture.sha256
                and native["nativeFixtureSha256"]==hashlib.sha256((folder/"schedule.tmstepnative").read_bytes()).hexdigest()
                and native["resetEpisodesCompared"]==1000 and native["totalTypedFramesCompared"]==ticks*1000
                and native["allTypedPhysicalFramesBitExact"] is True
                and native["syntheticArenaBytesClearedPerReset"]==0x9000000,"Native reset reference differs")
        require(offline["fixtureSha256"]==fixture.sha256 and offline["completed"] is True
                and offline["allTypedPhysicalFramesBitExact"] is True
                and offline["allDataPagesBitExact"] is True and offline["typedFramesCompared"]==ticks
                and not offline["faultReasons"] and offline["error"] is None,"Strict reference replay differs")
        native_total+=ticks*1000
    primary=fixtures["source424-mixed-300"]
    union=fixtures["source424-input-union"]
    seed=fixtures["source424-pedals"]
    require(primary.metadata["initialSnapshotSeedFixtureSha256"]==seed.sha256,"Mixed seed differs")
    for name in ("source424-pedals","source424-mixed-300"):
        capture=read("original-step-capture-"+name+".json")
        require(capture["sourceBindingRecheckedAfterCapture"] is True
                and capture["readOnlyProcessHandle"] is True and capture["atomicSnapshot"] is False
                and capture["gameMemoryWritten"] is False and capture["codeExecutedInGame"] is False
                and capture["trials"][0]["sparseFixtureSha256"]==fixtures[name].sha256,
                "Fresh source capture provenance differs")
    require(union.trace_mask==primary.trace_mask and union.trace_expected==primary.trace_expected
            and all(union.metadata.get(k)==primary.metadata.get(k) for k in COHORT_FIELDS),
            "Union changed primary physical reference or cohort")
    for address,page in primary.pages.items():
        merged=union.pages[address]
        require(all(not observed or (merged.mask[i] and merged.initial[i]==page.initial[i]
                                     and merged.expected[i]==page.expected[i])
                    for i,observed in enumerate(page.mask)),"Union changed observed primary bytes")
    contributors=read("source424-action-inputs.json")
    require(contributors["seedFixtureSha256"]==primary.sha256 and contributors["allBranchesCaptured"] is True
            and len(contributors["branches"])==27,"Source grid capture incomplete")
    provenance=union.metadata["observedInputUnion"]
    require(provenance["primaryFixtureSha256"]==primary.sha256
            and [r["sha256"] for r in provenance["contributors"]]==[r["sha256"] for r in contributors["branches"]],
            "Union contributor list differs")
    for row in contributors["branches"]:
        contributor=load_original_step_fixture(row["fixture"])
        require(contributor.sha256==row["sha256"]
                and contributor.metadata["initialControlsNormalizedToSeed"] is True
                and contributor.metadata["initialSnapshotSeedFixtureSha256"]==primary.sha256
                and all(contributor.metadata.get(k)==primary.metadata.get(k) for k in COHORT_FIELDS),
                "Contributor provenance differs")
        for address,page in contributor.pages.items():
            merged=union.pages[address]
            require(all(not observed or (merged.mask[i] and merged.initial[i]==page.initial[i])
                        for i,observed in enumerate(page.mask)),"Contributor input was lost or changed")
    grid=read("owned-source424-action-grid.json")
    expected=list(itertools.product((0.,.5,1.),(0.,.5,1.),(-1.,0.,1.)))
    require(grid["sourceFixtureSha256"]==union.sha256 and grid["allBranchesCompared"] is True
            and grid["nativeComparedFrames"]==54 and len(grid["branches"])==27,
            "Finite action grid comparison incomplete")
    require(all(tuple(row["controls"])==controls and row["completed"] is True
                for row,controls in zip(grid["branches"],expected)),"Action grid differs")
    interactive=read("owned-source424-interactive.json")
    require(interactive["fixtureSha256"]==union.sha256 and interactive["brakeFixtureSha256"]==seed.sha256
            and interactive["allComparedFramesBitExact"] is True and interactive["typedFramesCompared"]==131
            and interactive["allCheckpointPagesCompared"] is True
            and interactive["restorationAfterIncompleteStepVerified"] is True,"Source interactive branch differs")
    protocol=read("owned-source424-protocol.json")
    require(protocol["requests"]==10 and protocol["allValidRequestIdsMatched"] is True
            and protocol["rewindObservationBitExact"] is True and protocol["nullControlRejected"] is True
            and protocol["nonfiniteJsonRejected"] is True,"Strict JSON interface qualification missing")
    result=dict(schema="tm2020_owned_input_coverage_audit_v1",executableSha256=SHA,
        primaryFixtureSha256=primary.sha256,unionFixtureSha256=union.sha256,
        addedObservedInputBytes=sum(r["addedObservedBytes"] for r in provenance["contributors"]),
        nativeResetFramesCompared=native_total,initialActionGridBranchesCompared=27,
        initialActionGridNativeFramesCompared=54,sourceInteractiveFramesCompared=131,
        originalSourceVehiclePath=True,sourceCaptureAtomic=False,
        continuousActionDomainQualified=False,allMapsAndSurfacesQualified=False,
        completeStandaloneSimulatorQualified=False,fullTrackmaniaHeadlessRLReady=False)
    config=union.metadata["configuration"]
    coefficients=[]
    for offset in (0xb24,0xb2c,0x1d58,0x1d5c):
        address=config+offset;page=union.pages[address&~4095];at=address&4095
        require(all(page.mask[at:at+4]),"Missing newly observed configuration word")
        raw=page.initial[at:at+4]
        coefficients.append(dict(configurationOffset=hex(offset),bits=hex(struct.unpack("<I",raw)[0]),
                                 binary32Value=struct.unpack("<f",raw)[0],unitsQualified=False))
    result["newlyObservedConfigurationWords"]=coefficients
    (recon/"owned-input-coverage-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    print("PASS OBSERVED INPUT COVERAGE",native_total,"native frames; 27 initial actions; 131 interactive frames")


if __name__=="__main__":main()
