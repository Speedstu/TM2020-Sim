#!/usr/bin/env python3
"""Rank read-only Trackmania game memory vector hypotheses by controlled motion.

Requires TWO stationary snapshots and ONE manually moved snapshot of the
SAME process. Filters background animation/memory churn. This does not
validate coordinates; independent visual + replay validation is mandatory.
Only the filtered candidate numerical triplets are saved in the JSON report.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
DT=np.dtype([("address","<u8"),("xyz","<f4",(3,))])
FMT="<8sIIQQQ"
HSIZE=struct.calcsize(FMT)
def read(path:Path):
    with path.open("rb") as f:
        header=f.read(HSIZE)
    if len(header)!=HSIZE:raise ValueError(f"Truncated TMVEC header {path}")
    magic,version,itemsize,pid,scanned,entries=struct.unpack(FMT,header)
    if magic!=b"TMVEC1\0\0" or version!=1 or itemsize!=20:
        raise ValueError(f"Invalid TMVEC magic/version {path}")
    if entries>10_000_000:raise ValueError("Unreasonable numeric entry count")
    if path.stat().st_size!=HSIZE+entries*DT.itemsize:
        raise ValueError("Snapshot file size mismatch")
    entries=np.memmap(path,dtype=DT,mode="r",offset=HSIZE,shape=(entries,))
    addresses=entries["address"]
    if len(addresses)>1 and np.any(addresses[1:]<=addresses[:-1]):
        raise ValueError("Snapshot addresses are not strictly increasing")
    return pid,scanned,entries

def compare(first:Path,idle:Path,after:Path):
    p1,s1,base=read(first)
    p2,s2,still=read(idle)
    p3,s3,moved=read(after)
    if len({p1,p2,p3})!=1:raise ValueError("Process ID changed; old pointers invalid")
    # Independent address correspondence across all 3 captures, not value similarity.
    address1=base["address"]
    _,a,b=np.intersect1d(address1,still["address"],return_indices=True)
    _,c,d=np.intersect1d(address1[a],moved["address"],return_indices=True)
    ix1=a[c];ix2=b[c];ix3=d
    orig=base["xyz"][ix1]
    same=still["xyz"][ix2]
    new=moved["xyz"][ix3]
    rest=np.linalg.norm(orig.astype(np.float64)-same.astype(np.float64),axis=1)
    displacement=np.linalg.norm(new.astype(np.float64)-same.astype(np.float64),axis=1)
    # A real car initially parked should be steady. Selection deliberately
    # broad since we don't know the world scale/terrain slope yet.
    ok=(rest<=0.035)&(displacement>=0.30)&(displacement<=180.0)
    ix=np.nonzero(ok)[0]
    # Group approximate addresses close in memory; adjacent x/y/z vectors
    # are often copies of the same pose but may also be irrelevant transforms.
    ranked=sorted(ix,key=lambda k:(rest[k],abs(float(same[k][1])),abs(float(displacement[k]))))
    best=[]
    for k in ranked[:250]:
        best.append({
            "address":hex(int(address1[ix1[k]])),
            "stationaryA":np.asarray(orig[k],dtype=float).round(5).tolist(),
            "stationaryB":np.asarray(same[k],dtype=float).round(5).tolist(),
            "afterMovement":np.asarray(new[k],dtype=float).round(5).tolist(),
            "stationaryNoise":round(float(rest[k]),6),
            "movement":round(float(displacement[k]),6),
            "confirmedVehicle":False
        })
    return {
        "schema":"tm2020_motion_correlated_numeric_candidates_v1",
        "gamePid":int(p1),
        "originalSnapshot":str(first),
        "stationaryRepeatSnapshot":str(idle),
        "movementSnapshot":str(after),
        "scannedMBEach":[round(s/1048576,1) for s in (s1,s2,s3)],
        "commonTriplets":int(len(ix1)),
        "stableAtRestAndMovedCandidates":int(len(ix)),
        "reportedTopCandidates":len(best),
        "actualVehiclePositionProven":False,
        "notes":"Hypothesis-only. Changed vectors can represent camera/moving objects/UI. Verify independent replay/screen trajectory and resets before creating an SDK state reader.",
        "candidates":best
    }

def selftest():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        files=[Path(d)/f"{name}.tmvec" for name in ("original","idle","moving")]
        addresses=(0x123400,0x123500,0x123600,0x123700)
        data=[
            [(10.,10.,20.),(30.,5.,40.),(90.,20.,90.),(2.,3.,10.)],
            [(10.,10.,20.),(35.,5.,40.),(90.,20.,90.),(2.,3.,10.)],
            [(15.,10.,35.),(40.,5.,40.),(90.,20.,90.),(2.,3.,10.)]
        ]
        for path,points in zip(files,data):
            with path.open("wb") as f:
                f.write(struct.pack(FMT,b"TMVEC1\0\0",1,20,222,4096,4))
                for address,xyz in zip(addresses,points):
                    f.write(struct.pack("<Q3f",address,*xyz))
        result=compare(*files)
        assert result["stableAtRestAndMovedCandidates"]==1,result
        assert result["candidates"][0]["address"]==hex(addresses[0]),result
        assert result["candidates"][0]["movement"]>10,result
        print("PASS TMVEC controlled-motion ranking selftest")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--selftest",action="store_true")
    parser.add_argument("--before",type=Path)
    parser.add_argument("--still",type=Path)
    parser.add_argument("--after",type=Path)
    parser.add_argument("--out",type=Path,default=ROOT/"local/recon/motion-position-hypotheses.json")
    p=parser.parse_args()
    if p.selftest:return selftest()
    if not all((p.before,p.still,p.after)):parser.error("Need --before, --still and --after")
    result=compare(p.before,p.still,p.after)
    p.out.parent.mkdir(parents=True,exist_ok=True)
    p.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("CANDIDATE_MOTION_COMPARISON",result["stableAtRestAndMovedCandidates"],
          "common",result["commonTriplets"],"confirmedVehicle",False,"output",p.out)
if __name__=="__main__":sys.exit(main())
