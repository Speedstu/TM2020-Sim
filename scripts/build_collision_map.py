#!/usr/bin/env python3
"""Build an INCOMPLETE collision map from explicitly embedded custom Item.Gbx Phy Shapes.

Uses verified GBX.NET-derived CPlugSurface triangles. Built-in stadium blocks and
"IsMeshCollidable" visual-mesh colliders are NOT available in this export.
Rotation order Y(yaw)*X(pitch)*Z(roll) is a hypothesis, not experimentally verified.
Do not use as a ground-truth collision engine.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from collections import Counter
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
EXE=ROOT/"src/GbxLab/bin/Release/net9.0/GbxLab.dll"
def invoke(*args):
    env=dict(os.environ)
    h=ROOT/"cache"
    for name,path in {"DOTNET_CLI_HOME":h/"dotnet-home",
                      "NUGET_PACKAGES":h/"nuget","TEMP":h/"temp","TMP":h/"temp"}.items():
        path.mkdir(parents=True,exist_ok=True)
        env[name]=str(path)
    p=subprocess.run(["dotnet",str(EXE),*map(str,args)],env=env,text=True,capture_output=True)
    if p.returncode:
        raise RuntimeError(f"GBX Lab failed {args[0]} on {args[1]}:\n{p.stderr}\n{p.stdout}")
def asset_key(filename: str)->str:
    # Preserve all nested item paths: matching only basenames risks aliasing
    # user-created assets that happen to share one filename.
    value=filename.replace("\\","/").lstrip("/").casefold()
    if "/items/" in value:
        value=value.rsplit("/items/",1)[1]
    elif value.startswith("items/"):
        value=value[6:]
    return value

def ident_key(model:str)->str:
    # GBX.NET Ident.ToString() format: ("asset/path.Item.Gbx", "Stadium2020", "author")
    parts=model.split('"')
    return asset_key(parts[1]) if len(parts)>=3 else asset_key(model)

def rot_matrix(ang):
    yaw,pitch,roll=map(float,ang)
    cy,sy=math.cos(yaw),math.sin(yaw)
    cp,sp=math.cos(pitch),math.sin(pitch)
    cr,sr=math.cos(roll),math.sin(roll)
    ry=np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    rx=np.array([[1,0,0],[0,cp,-sp],[0,sp,cp]])
    rz=np.array([[cr,-sr,0],[sr,cr,0],[0,0,1]])
    return ry@rx@rz

def parse_obj(path: Path):
    vertices=[]
    faces=[]
    if not path.exists():return vertices,faces
    with path.open(encoding="utf-8-sig") as f:
        for line in f:
            if line.startswith("v "):
                parts=line.split()
                vertices.append([float(parts[1]),float(parts[2]),float(parts[3])])
            elif line.startswith("f "):
                parts=line.split()
                face=[int(q.split('/')[0]) for q in parts[1:]]
                if len(face)==3: faces.append(face)
    return vertices,faces

def prepare_assets(mapid: int):
    mx=ROOT/"local"/"test-maps"/f"tmx-{mapid}.Map.Gbx"
    if not mx.is_file(): raise FileNotFoundError(mx)
    embedded=ROOT/"local"/"embedded"/str(mapid)
    if not (embedded/"manifest.json").is_file():
        invoke("embedded-extract",mx,embedded)
    assets={}
    embedded_items=sorted(
        (p for p in embedded.rglob("*") if p.is_file() and p.name.lower().endswith(".item.gbx")),
        key=lambda p:str(p).lower())
    outbase=ROOT/"local"/"mesh"/str(mapid)
    for ix, itemfile in enumerate(embedded_items):
        d=outbase/f"item_{ix:04d}"
        if not (d/"manifest.json").is_file():
            invoke("mesh-extract",itemfile,d)
        j=json.loads((d/"manifest.json").read_text(encoding="utf-8-sig"))
        surfaces=[s for s in j.get("surfaceExports",[]) if s["name"]=="physical_shape"]
        data={
            "source":str(itemfile.relative_to(ROOT)).replace("\\","/"),
            "meshDir":d,"collidableVisualWithoutShape":bool(j.get("isMeshCollidable")) and not bool(j.get("physicalShapeAvailable")),
            "physicalSurfaces":surfaces,
            "triggerShapes":len([s for s in j.get("surfaceExports",[]) if s["name"]=="trigger_shape"])
        }
        key=asset_key(str(itemfile.relative_to(embedded)))
        if key in assets:
            raise RuntimeError("Ambiguous asset key: "+key)
        assets[key]=data
    return assets

def build(mapid:int):
    assets=prepare_assets(mapid)
    map_file=ROOT/"local"/"test-maps"/f"tmx-{mapid}.json"
    if not map_file.is_file():raise FileNotFoundError(map_file)
    world=json.loads(map_file.read_text(encoding="utf-8-sig"))
    dest=ROOT/"local"/"collision"/str(mapid)
    dest.mkdir(parents=True,exist_ok=True)
    output=dest/"embedded_physical_shapes.obj"
    matched=Counter()
    unexported=Counter()
    objects=0;vertices_out=0;faces_out=0
    cache={}
    # Only physically labelled shapes. Do not mistake triggers for road collisions.
    with output.open("w",encoding="utf-8") as f:
        f.write("# PARTIAL map collider: embedded Item.Gbx physical_shape only\n")
        f.write("# Y(yaw)*X(pitch)*Z(roll) convention is UNVERIFIED\n")
        for i, instance in enumerate(world["items"]):
            key=ident_key(instance["model"])
            asset=assets.get(key)
            if asset is None:continue
            matched[key]+=1
            if not asset["physicalSurfaces"]:
                if asset["collidableVisualWithoutShape"]:
                    unexported[key]+=1
                continue
            pos=np.array(instance["positionInMap"],dtype=np.float64)
            rot=rot_matrix(instance["yawPitchRoll"])
            for surf in asset["physicalSurfaces"]:
                mesh_path=asset["meshDir"]/surf["obj"]
                if mesh_path not in cache:
                    cache[mesh_path]=parse_obj(mesh_path)
                points,triangles=cache[mesh_path]
                if not points or not triangles:continue
                verts=(np.asarray(points,dtype=np.float64)@rot.T)+pos
                f.write(f"g Item_{i}_"+re.sub(r'[^A-Za-z0-9_]','_',key)[:90]+"\n")
                for p in verts:
                    f.write(f"v {p[0]:.8f} {p[1]:.8f} {p[2]:.8f}\n")
                for face in triangles:
                    shifted=[vertices_out+idx for idx in face]
                    f.write(f"f {shifted[0]} {shifted[1]} {shifted[2]}\n")
                vertices_out+=len(verts)
                faces_out+=len(triangles)
                objects+=1
    stats={
        "schema":"tm2020_partial_collision_world_v1",
        "tmxId":mapid,"mapUid":world["uid"],"mapName":world["mapName"],
        "totalAnchoredObjects":len(world["items"]),
        "embeddedAssetModels":len(assets),"matchedEmbeddedInstances":sum(matched.values()),
        "instancesWithPhysicalMesh":objects,
        "missingCollidableVisualInstances":sum(unexported.values()),
        "worldVertices":vertices_out,"worldTriangles":faces_out,
        "obj":str(output.relative_to(ROOT)).replace("\\","/"),
        "matchedAssetCounts":dict(matched),
        "unexportedCollidableVisualAssetCounts":dict(unexported),
        "limitations":[
            "Built-in Trackmania blocks and built-in Nadeo item colliders are missing.",
            "IsMeshCollidable true with no Shape implies collision handled by visual geometry, not exported.",
            "Trigger shapes are excluded; they are NOT physical road surfaces.",
            "YawPitchRoll world transform order is a provisional assumption, not experimentally verified.",
            "No friction, gravity, force or vehicle collision response is implemented.",
            "These are only meshes embedded in the public map, not protected game .pak files."
        ]
    }
    (dest/"coverage.json").write_text(json.dumps(stats,indent=2)+"\n",encoding="utf-8")
    return stats

def main():
    p=argparse.ArgumentParser()
    p.add_argument("mapids",nargs="+",type=int)
    opts=p.parse_args()
    if not EXE.exists():raise FileNotFoundError("Build GbxLab first")
    for mid in opts.mapids:
        result=build(mid)
        print(f"MAP {mid}: {result['instancesWithPhysicalMesh']} physical meshes, "
              f"{result['worldTriangles']} triangles, "
              f"{result['missingCollidableVisualInstances']} collidable visuals unavailable, "
              f"{result['totalAnchoredObjects']} total anchored items")
    return 0
if __name__=="__main__":sys.exit(main())
