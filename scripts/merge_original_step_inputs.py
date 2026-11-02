"""Union observed numeric inputs from compatible private, same-process captures.

The primary trace remains unchanged. Newly added bytes were not read or written
by that primary execution, so its expected final value is their observed initial
value. This derivation is recorded explicitly and must be replayed independently.
No game process is opened and no executable instruction bytes are retained.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture


COHORT_FIELDS=("schema","entryRva","outerSceneStage","stoppedSnapshotCohortSha256",
    "sourceSnapshotAtomicUnderLease","ownedStackReturnAddressReplaced",
    "modules","sourcePid","sourceProcessCreationFiletime","manager",
    "vehicle","configuration","selectedBodyIndex","stateAddress","stateCount",
    "externalPlatformModels","synthetic","postStepPipeline",
    "sourceBodyActivationRestored","observedSourceBodyActivation","pinnedReadonlyConstantExtensions")


def merge(primary_path, contributor_paths, output, report_path):
    require(not output.exists() and not report_path.exists(),"Merge never overwrites evidence")
    primary=load_original_step_fixture(primary_path)
    require(1<=len(contributor_paths)<=128,"Contributor count bound")
    m=copy.deepcopy(primary.metadata)
    pages={a:[bytearray(p.mask),bytearray(p.initial),bytearray(p.expected)]
           for a,p in primary.pages.items()}
    code_pages=set(map(tuple,m["codePages"]))
    overlays={}
    for rec in m["codeDataOverlays"]:
        overlays[(rec["module"],rec["rva"])]=dict(rec["bytes"])
    inputs=[];seen={primary.sha256}
    for path in contributor_paths:
        other=load_original_step_fixture(path)
        require(other.sha256 not in seen,"Duplicate input contributor")
        seen.add(other.sha256)
        require(all(other.metadata.get(k)==m.get(k) for k in COHORT_FIELDS),
                "Contributor belongs to a different process, binding or scene cohort")
        require(other.metadata.get("sourceVelocityPreserved",False)==m.get("sourceVelocityPreserved",False),
                "Contributor has a different source-velocity provenance")
        require(other.metadata.get("initialSnapshotSeedFixtureSha256") in
                {primary.sha256,m.get("initialSnapshotSeedFixtureSha256")}-{None},
                "Contributor has no retained common initial state")
        added=0;overlap=0
        for address,page in other.pages.items():
            mask,initial,expected=pages.setdefault(address,[bytearray(4096) for _ in range(3)])
            for offset,observed in enumerate(page.mask):
                if not observed:continue
                if mask[offset]:
                    require(initial[offset]==page.initial[offset],
                            f"Conflicting observed initial input at {address+offset:#x}")
                    overlap+=1
                else:
                    mask[offset]=1
                    initial[offset]=expected[offset]=page.initial[offset]
                    added+=1
        require(overlap>1000,"Insufficient observed common initial state")
        code_pages.update(map(tuple,other.metadata["codePages"]))
        for rec in other.metadata["codeDataOverlays"]:
            values=overlays.setdefault((rec["module"],rec["rva"]),{})
            for offset,value in rec["bytes"]:
                require(offset not in values or values[offset]==value,"Conflicting numeric code overlay")
                values[offset]=value
        inputs.append(dict(sha256=other.sha256,addedObservedBytes=added,matchingInitialBytes=overlap))
    require(sum(i["addedObservedBytes"] for i in inputs)>0,"No newly observed inputs")
    m["codePages"]=[list(k) for k in sorted(code_pages)]
    m["codeDataOverlays"]=[dict(module=k[0],rva=k[1],bytes=sorted(v.items()))
                            for k,v in sorted(overlays.items())]
    m["observedInputUnion"]={"version":1,"primaryFixtureSha256":primary.sha256,
        "contributors":inputs,"primaryTraceUnchanged":True,
        "addedExpectedBytesDerivedFromUnaccessedPrimaryInputs":True,
        "atomicSnapshot":False,"completeSimulatorQualified":False}
    m["dataPages"]=[]
    payloads={"trace-mask.bin":primary.trace_mask,"trace-expected.bin":primary.trace_expected}
    for address,(mask,initial,expected) in sorted(pages.items()):
        raw=bytes(mask+initial+expected)
        name=f"data/{address:016x}.bin"
        payloads[name]=raw
        m["dataPages"].append(dict(address=address,file=name,sha256=hashlib.sha256(raw).hexdigest()))
    payloads["metadata.json"]=(json.dumps(m,indent=2)+"\n").encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,"x",ZIP_DEFLATED) as archive:
        for name,raw in payloads.items():archive.writestr(name,raw)
    retained=load_original_step_fixture(output)
    require(retained.trace_mask==primary.trace_mask and retained.trace_expected==primary.trace_expected,
            "Primary trace changed")
    report=dict(schema="tm2020_observed_input_union_v1",fixtureSha256=retained.sha256,
        primaryFixtureSha256=primary.sha256,contributors=inputs,
        totalAddedObservedBytes=sum(i["addedObservedBytes"] for i in inputs),
        primaryReferenceFrames=primary.metadata["tickCount"],
        primaryTraceUnchanged=True,gameProcessAccessed=False,referenceReplayPending=True,
        completeSimulatorQualified=False)
    report_path.write_text(json.dumps(report,indent=2)+"\n")
    print("OBSERVED INPUT UNION",report["totalAddedObservedBytes"],"bytes; reference replay required")
    return retained


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary",type=Path,required=True)
    parser.add_argument("--contributors",type=Path,nargs="+",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True)
    args=parser.parse_args()
    merge(args.primary,args.contributors,args.output,args.report)
