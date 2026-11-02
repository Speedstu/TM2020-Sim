#!/usr/bin/env python3
"""Cross-check read-only four-snapshot pose hypotheses against the actual
Trackmania 2020 Fall 2026 - 01 GBX map. No injection or runtime hooks.

GBX authored world grid has 32m horizontal blocks: start center of
RoadTechStart at (37*32+16, 42*32+16) = (1200, 1360) in X,Z.
Do not infer Y from grid because grid terrain altitude differs from item height.

Any corroborated float3 triplets remain *candidate copies*, not confirmed
live physics entity pointers. Calibration remains valid for this game process
and map only, never across a restart without revalidation.
"""
from __future__ import annotations
from pathlib import Path
import json, hashlib, math, sys

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"local"
MAP=BASE/"campaign-2026-autumn"/"Autumn-2026-01.Map.json"
GBX=BASE/"campaign-2026-autumn"/"Autumn-2026-01.Map.Gbx"
CAND=BASE/"recon"/"multi-copy-motion-candidates.json"
OUTPUT=BASE/"recon"/"map-corroborated-pose-clusters.json"

def pos2(p):
    return float(p[0]),float(p[2])

def dist(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])

def nearest_road(blocks,p):
    choices=[]
    for block in blocks:
        if not block["name"].startswith(("Road","Platform","Penalty","Turbo","Booster")):
            continue
        grid=block.get("grid")
        if not isinstance(grid,list) or len(grid)!=3:continue
        center=(float(grid[0])*32+16,float(grid[2])*32+16)
        choices.append((dist(pos2(p),center),block["name"],grid))
    return min(choices) if choices else None

def evaluate(m,report):
    starts=[b for b in m["blocks"] if b["name"]=="RoadTechStart"]
    if len(starts)!=1:
        raise ValueError(f"Expected exactly one start: found {len(starts)}")
    g=starts[0]["grid"]
    center=[float(g[0]*32+16),float(g[2]*32+16)]
    entries=[]
    for item in report["groups"]:
        before=item["beforeXYZ"]
        after=item["afterXYZ"]
        near=nearest_road(m["blocks"],after)
        start_error=dist(pos2(before),center)
        evidence=(start_error<=12.0 and near and near[0]<=48
                  and item["distinct4KPages"]>=3
                  and item["supportingTriplets"]>=4
                  and -10<before[1]<100 and -50<after[1]<100)
        if not evidence:continue
        entries.append({
            "startHorizontalErrorM":round(start_error,4),
            "endNearestTrackBlock":near[1],
            "endNearestTrackBlockGrid":near[2],
            "endNearestBlockCenterDistanceM":round(near[0],4),
            "supportingTriplets":item["supportingTriplets"],
            "distinct4KPages":item["distinct4KPages"],
            "measuredDisplacement":item["displacement"],
            "beforeXYZ":before,"afterXYZ":after,
            "addressesInCurrentProcess":item["addressExamples"],
            "validatedPlayerPose":False,
            "scope":"THIS PID ONLY; UNVERIFIED until reset/replay motion tracking",
        })
    entries.sort(key=lambda x:(
        x["startHorizontalErrorM"]+0.1*x["endNearestBlockCenterDistanceM"],
        -x["distinct4KPages"],-x["supportingTriplets"]))
    return {
        "schema":"tm2020_gbx_corroborated_pose_candidates_v1",
        "mapUid":m["uid"],
        "mapName":m["mapName"],
        "mapFileSha256":hashlib.sha256(GBX.read_bytes()).hexdigest(),
        "gamePid":report["pid"],
        "startBlockName":"RoadTechStart",
        "startBlockGrid":g,
        "startGridCellMeters":32,
        "startBlockCenterXZ":center,
        "fourSnapshotCandidateGroups":len(report["groups"]),
        "mapCorroboratedCandidateGroups":len(entries),
        "confirmedLivePlayerStatePointer":False,
        "confirmed100HzPhysicsState":False,
        "confidence":"strong map/position correlation, NOT a validated runtime pointer chain",
        "caveat":"Map X,Z ordered as-is; previous ZYX assumption was WRONG. Candidate addresses not stable between process launches.",
        "rankedCandidates":entries[:30]
    }

def selftest():
    fake={"uid":"test-map","mapName":"test","blocks":[
        {"name":"RoadTechStart","grid":[37,19,42]},
        {"name":"RoadTechCheckpointTiltLeft","grid":[35,16,37]}
    ]}
    yes={"beforeXYZ":[1200,34,1360],"afterXYZ":[1148,11,1188],
         "distinct4KPages":6,"supportingTriplets":12,"displacement":181,
         "addressExamples":["0x12300"]}
    no=dict(yes);no["beforeXYZ"]=[3000,34,3000]
    info={"pid":42,"groups":[yes,no]}
    # This pure unit test does not depend on real GBX bytes.
    global GBX
    original=GBX
    try:
        GBX=Path(__file__)  # readable file to hash, irrelevant to test
        result=evaluate(fake,info)
    finally:GBX=original
    assert result["mapCorroboratedCandidateGroups"]==1,result
    assert result["rankedCandidates"][0]["startHorizontalErrorM"]==0.0
    assert result["confirmedLivePlayerStatePointer"] is False
    print("PASS GBX coordinate corroboration scoring selftest")

def main():
    if "--selftest" in sys.argv:
        selftest();return
    m=json.loads(MAP.read_text(encoding="utf-8-sig"))
    candidates=json.loads(CAND.read_text(encoding="utf-8-sig"))
    result=evaluate(m,candidates)
    if result["mapCorroboratedCandidateGroups"]<2:
        raise RuntimeError("Too few physically corroborated candidate groups")
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS GBX_POSE_CORROBORATION map",result["mapName"],
        "pid",result["gamePid"],"start",result["startBlockCenterXZ"],
        "groups",result["mapCorroboratedCandidateGroups"])
    for x in result["rankedCandidates"][:7]:
        print("CORRELATED copies",x["supportingTriplets"],
              "pages",x["distinct4KPages"],
              "startError",x["startHorizontalErrorM"],
              "nearEndBlock",x["endNearestTrackBlock"],
              "blockCenterDistance",x["endNearestBlockCenterDistanceM"],
              "before",x["beforeXYZ"],
              "after",x["afterXYZ"])
    print("IMPORTANT: still NOT a validated player pointer or 100Hz physics feed")
    print("OUTPUT",OUTPUT)
if __name__=="__main__":main()
