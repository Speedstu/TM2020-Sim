#!/usr/bin/env python3
"""Compare PARTIAL 3D collision mesh ray hits to positions in public replay datasets.

Hit fraction is not a fidelity score of actual game physics: zero simply indicates
missing/crossing geometry or shape transform errors. Only embedded custom physical
shapes are currently available; built-in track geometry is absent.
"""
from pathlib import Path
from collections import Counter
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent
exe=ROOT/"bin/trackray.exe"

def run():
    manifest=json.loads((ROOT/"local/dataset-manifest.json").read_text(encoding="utf-8-sig"))
    output={}
    for pair in manifest["linked"]:
        mapid=pair["tmxId"]
        data=json.loads((ROOT/pair["datasetJson"]).read_text(encoding="utf-8-sig"))
        frames=data["ghosts"][0]["result"]["stateInputRows"]
        mesh=ROOT/"local/collision"/str(mapid)/"embedded_physical_shapes.obj"
        coverage_file=ROOT/"local/collision"/str(mapid)/"coverage.json"
        coverage=json.loads(coverage_file.read_text(encoding="utf-8-sig")) if coverage_file.exists() else {}
        if not mesh.exists() or mesh.stat().st_size<100 or coverage.get("worldTriangles",0)==0:
            output[str(mapid)]={"replayId":pair["replayId"],"samples":len(frames),"hits":0,
                                "status":"no partial collision meshes"}
            continue
        rays=ROOT/"local/collision"/str(mapid)/"ground_rays.txt"
        rays.write_text("\n".join(
            f"{r['position'][0]} {r['position'][1]+2} {r['position'][2]} 0 -1 0 8" for r in frames
        )+"\n",encoding="utf-8")
        p=subprocess.run([str(exe),str(mesh),"--batch",str(rays)],
                         text=True,capture_output=True,env=os.environ.copy())
        if p.returncode!=0:raise RuntimeError(p.stderr)
        data_out=[json.loads(line) for line in p.stdout.splitlines() if line.strip()]
        if len(data_out)!=len(frames):raise RuntimeError("Ray output count mismatch")
        hit=[v for v in data_out if v["hit"]]
        output[str(mapid)]={
            "replayId":pair["replayId"],"samples":len(frames),
            "hits":len(hit),"hitFraction":round(len(hit)/len(frames),6),
            "status":"partial embedded physical meshes only",
            "groundRayOrigin":"vehicle_position + (0,2,0)",
            "groundRay":"downward 8 meters",
            "meanHitDistanceMeters":round(sum(v["distance"] for v in hit)/len(hit),5) if hit else None,
            "caution":"The OBJ world transform order is not yet independently validated; 0% does not imply replay is airborne"
        }
    target=ROOT/"local/collision/ground_probe_validation.json"
    target.write_text(json.dumps({"schema":"tm2020_partial_mesh_ground_probe_v1","maps":output},indent=2)+"\n",
                      encoding="utf-8")
    print(json.dumps(output,indent=2))
    print("SAVED",target)
if __name__=="__main__":
    run()
