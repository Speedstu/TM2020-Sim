#!/usr/bin/env python3
"""One-time offline conversion from verified GBX JSON to a portable, native C++ binary SDK.

NO game memory, no physics approximation. Exact stored 50 ms samples + 10ms
input change events, and map layout metadata, retained as IEEE754 double
precision for vehicle state positions/quaternions/velocities/controls.

Output format v1 is documented in native/FORMAT.md. Explicit little-endian.
This is a DATASET; it is *not* an interactive physics simulator.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import pathlib
import struct
import sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"local"/"native-datasets"
MAGIC=b"TMRDSV1\x00"
MAPMAG=b"TMRMAP1\x00"

def read(path:pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def wstr(f,s:str):
    b=s.encode("utf-8")
    if len(b)>32768:raise ValueError("String too long")
    f.write(struct.pack("<H",len(b)))
    f.write(b)

def checked(values,n,name):
    vals=[float(v) for v in values]
    if len(vals)!=n or not all(math.isfinite(v) for v in vals):
        raise ValueError(f"Invalid {name} vector")
    return vals

MATERIALS={"None":0, "Asphalt":1,"Concrete":2,"Dirt":3,"Grass":4,"Ice":5,
           "Metal":6,"Plastic":7,"Rubber":8,"Sand":9,"Wood":10,"Water":11}
def material_id(s):
    return MATERIALS.get(s,255)

def export_replay(pair):
    uid=pair["mapUid"]
    source=ROOT/pair["datasetJson"]
    raw=read(source)
    ghosts=[g["result"] for g in raw["ghosts"] if g["result"].get("stateInputRows")]
    if len(ghosts)!=1:raise ValueError("Expected one vehicle ghost")
    ghost=ghosts[0]
    frames=ghost["stateInputRows"]
    events=ghost["inputEventTimeline"]
    race_ms=pair["timeMs"] if "timeMs" in pair else None
    if race_ms is None:
        txt=ghost["raceTime"]
        m,s=txt.split(":")
        whole,frac=(s.split(".")+["0"])[:2]
        race_ms=int(m)*60000+int(whole)*1000+int(frac.ljust(3,"0")[:3])
    if len(frames)>100_000 or len(events)>1_000_000: raise ValueError("Invalid counts")
    name=pair.get("mapName","")
    dest=OUT/(str(pair["tmxId"])+".tmreplay")
    with dest.open("wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<IIIII",1,len(frames),len(events),int(race_ms),50))
        wstr(f,uid)
        wstr(f,name)
        prev=-1
        for frame in frames:
            t=int(frame["tMs"])
            if t<=prev: raise ValueError(f"Nonmonotonic frame times: {source}")
            prev=t
            pos=checked(frame["position"],3,"position")
            quat=checked(frame["rotation"],4,"quaternion")
            vel=checked(frame["velocity"],3,"velocity")
            control=frame["recordedControls"]
            scalars=[float(frame["speedKmh"]),float(frame["euler"][1]),
                     float(control["steer"]),float(control["gas"]),float(control["brake"]),
                     float(frame["sideSpeed"])]
            if not all(math.isfinite(v) for v in scalars):raise ValueError("Bad scalar")
            materials=frame["tire"]["groundMaterials"]
            if len(materials)!=4:raise ValueError("Bad materials")
            f.write(struct.pack("<i16d4BB",t,*(pos+quat+vel+scalars),
                                *[material_id(x) for x in materials],int(bool(frame["ground"]))))
        last=-2**31
        for event in events:
            t=int(event["tMs"])
            if t<last:raise ValueError("Nonmonotonic input event sequence")
            last=t
            steer=event.get("steerRaw")
            if steer is not None and not -128<=int(steer)<=127:
                raise ValueError("Steer is not signed 8 bit")
            values=[
                t, int(steer) if steer is not None else -32768,
                *[(-1 if event.get(k) is None else int(bool(event[k]))) for k in ("gas","brake","respawn")]
            ]
            f.write(struct.pack("<ihbbb",*values))
    return dest

def export_map(pair):
    uid=pair["mapUid"]
    raw=read(ROOT/pair["mapJson"])
    if raw["uid"]!=uid:raise ValueError("Map UID mismatch")
    blocks=raw["blocks"]
    items=raw["items"]
    if len(blocks)>1_000_000 or len(items)>1_000_000:raise ValueError("Map too large")
    dest=OUT/(str(pair["tmxId"])+".tmmap")
    with dest.open("wb") as f:
        f.write(MAPMAG)
        f.write(struct.pack("<III",1,len(blocks),len(items)))
        wstr(f,uid)
        wstr(f,raw.get("mapName",""))
        for b in blocks:
            wstr(f,b["name"])
            xyz=b["grid"]
            if len(xyz)!=3:raise ValueError("Invalid grid")
            f.write(struct.pack("<iii",*map(int,xyz)))
            wstr(f,b["direction"])
            flags=((1 if b["isGround"] else 0)|(2 if b["isFree"] else 0))
            f.write(struct.pack("<B",flags))
            haspos=b["absolutePositionInMap"] is not None
            hasrot=b["yawPitchRoll"] is not None
            f.write(struct.pack("<BB",int(haspos),int(hasrot)))
            if haspos:f.write(struct.pack("<3d",*checked(b["absolutePositionInMap"],3,"block pos")))
            if hasrot:f.write(struct.pack("<3d",*checked(b["yawPitchRoll"],3,"block ypr")))
        for it in items:
            wstr(f,it["model"])
            f.write(struct.pack("<6d",*checked(it["positionInMap"],3,"item pos"),
                                *checked(it["yawPitchRoll"],3,"item rotation")))
    return dest

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=0,help="0 means all verified 24 map/replay pairs")
    args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    meta=[]
    m1=read(ROOT/"local"/"dataset-manifest.json")["linked"]
    m2=read(ROOT/"local"/"corpus"/"manifest.json")["pairs"]
    all_pairs=[*m1,*m2]
    if args.limit:all_pairs=all_pairs[:args.limit]
    seen=set()
    for pair in all_pairs:
        if pair["mapUid"] in seen:raise ValueError("Duplicate map UID")
        seen.add(pair["mapUid"])
        replay=export_replay(pair)
        map_file=export_map(pair)
        meta.append({"tmxId":pair["tmxId"],"mapUid":pair["mapUid"],"replay":replay.name,
                     "map":map_file.name,"replaySha256":hashlib.sha256(replay.read_bytes()).hexdigest(),
                     "mapSha256":hashlib.sha256(map_file.read_bytes()).hexdigest()})
        print("PASS native dataset",pair["tmxId"],replay.stat().st_size,map_file.stat().st_size,flush=True)
    (OUT/"manifest.json").write_text(json.dumps({"format":"tm2020_native_dataset_v1",
                              "fullPhysics":False,"pairs":meta},indent=2)+"\n",encoding="utf-8")
    print("READY native replay/map data",len(meta),"pairs at",OUT)
    return 0
if __name__=="__main__":sys.exit(main())
