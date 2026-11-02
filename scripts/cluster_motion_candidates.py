#!/usr/bin/env python3
"""Correlate four bounded numeric-only Trackmania snapshots to find repeated
vector coordinate candidates, requiring stable before and after physical drive.

NO candidate becomes a validated SDK offset; use a second independent
motion/reset/map trial plus verified coordinate frame before promoting one.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path
import struct
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
RECON=ROOT/"local/recon"
FILES=[
    RECON/"stationary-solo-track01.tmvec",
    RECON/"stationary-solo-track01-second.tmvec",
    RECON/"moved-solo-track01.tmvec",
    RECON/"after-move-still.tmvec"
]
OUT=RECON/"multi-copy-motion-candidates.json"
DT=np.dtype([("address","<u8"),("xyz","<f4",(3,))])
HEAD="<8sIIQQQ"

def load(path):
    with path.open("rb") as f:
        h=f.read(struct.calcsize(HEAD))
    if len(h)!=struct.calcsize(HEAD):
        raise ValueError("Truncated header: "+str(path))
    magic,v,size,pid,scanned,n=struct.unpack(HEAD,h)
    if magic!=b"TMVEC1\0\0" or v!=1 or size!=DT.itemsize:
        raise ValueError("Wrong format: "+str(path))
    if n>1_000_000:
        raise ValueError("Too many records")
    if path.stat().st_size!=struct.calcsize(HEAD)+n*DT.itemsize:
        raise ValueError("Corrupt payload")
    d=np.memmap(path,dtype=DT,mode="r",offset=struct.calcsize(HEAD),shape=(n,))
    if np.any(d["address"][1:]<=d["address"][:-1]):
        raise ValueError("Unsorted snapshot")
    return pid,d

def main():
    data=[load(p) for p in FILES]
    if len({pid for pid,_ in data})!=1:
        raise ValueError("Different processes: cannot compare absolute addresses")
    addr=data[0][1]["address"]
    idx=[np.arange(len(addr),dtype=np.int64)]
    for _,d in data[1:]:
        other=d["address"]
        _,i,j=np.intersect1d(addr,other,assume_unique=True,return_indices=True)
        addr=addr[i]
        idx=[prev[i] for prev in idx]+[j]
    if len(addr)<250000:raise ValueError("Too few common numeric vectors")
    vectors=[d["xyz"][i].astype(np.float64) for (_,d),i in zip(data,idx)]
    at0,at1,at2,at3=vectors
    initial_noise=np.linalg.norm(at1-at0,axis=1)
    final_noise=np.linalg.norm(at3-at2,axis=1)
    motion=np.linalg.norm(at2-at1,axis=1)
    candidate=(initial_noise<=0.035)&(final_noise<=0.035)&(motion>=0.3)&(motion<=240)
    cand_ids=np.where(candidate)[0]
    groups=collections.defaultdict(list)
    for k in cand_ids:
        # Quantize 3D initial and final points, not only displacement: repeated
        # car/world transforms give support in independent memory allocations.
        signature=tuple(np.round(np.concatenate((at1[k],at2[k])),1).tolist())
        groups[signature].append(int(k))
    report=[]
    for signature,indices in groups.items():
        if len(indices)<2:continue
        order=sorted(indices,key=lambda k:(initial_noise[k]+final_noise[k],k))
        reference=order[0]
        # Count distinct pages: repeated entries within one object may be
        # correlated; this exposes that fact instead of inflating confidence.
        pages={int(addr[k])//4096 for k in indices}
        report.append({
            "supportingTriplets":len(indices),
            "distinct4KPages":len(pages),
            "beforeXYZ":np.round(at1[reference],4).tolist(),
            "afterXYZ":np.round(at2[reference],4).tolist(),
            "displacement":round(float(motion[reference]),4),
            "stationaryNoiseBefore":round(float(initial_noise[reference]),7),
            "stationaryNoiseAfter":round(float(final_noise[reference]),7),
            "addressExamples":[hex(int(addr[k])) for k in order[:18]],
            "confirmedVehiclePosition":False,
        })
    report.sort(key=lambda d:(-d["supportingTriplets"],-d["distinct4KPages"],-d["displacement"]))
    result={
        "schema":"tm2020_four_snapshot_numeric_position_clusters_v1",
        "pid":data[0][0],
        "snapshots":[str(p) for p in FILES],
        "commonNumericTriplets":int(len(addr)),
        "stationaryBeforeAndAfterButMovingBetween":int(len(cand_ids)),
        "clustersWithTwoOrMoreCopies":len(report),
        "candidateVehicleOffsetsVerified":False,
        "capturesAreOnlyReadOnly":True,
        "notes":"Candidate groups include mirrored camera/render/world transforms. Need independent reference coordinates and a second controlled motion/reset trial before confirming car pose.",
        "groups":report[:250]
    }
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS FOUR_SNAPSHOT_GROUPING pid",result["pid"],
          "common",result["commonNumericTriplets"],
          "stableMovedStable",result["stationaryBeforeAndAfterButMovingBetween"],
          "clusters",result["clustersWithTwoOrMoreCopies"])
    for g in report[:18]:
        print("COPIES",g["supportingTriplets"],"PAGES",g["distinct4KPages"],"MOVE",g["displacement"],
            "BEFORE",g["beforeXYZ"],"AFTER",g["afterXYZ"],"EXAMPLE",g["addressExamples"][:2])
    print("REPORT",OUT)
if __name__=="__main__":sys.exit(main())
