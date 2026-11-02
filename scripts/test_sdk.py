#!/usr/bin/env python3
"""End-to-end SDK smoke test without modifying game or installing packages."""
from pathlib import Path
import json
import math
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"sdk"))
from trackmania2020 import ReplayCorpus,PartialCollisionWorld

def main():
    corpus=ReplayCorpus(ROOT)
    assert len(corpus)>=4,len(corpus)
    train,test=corpus.group_split()
    assert set(train).isdisjoint(test)
    all_ids=set()
    valid_frames=0
    for i in range(len(corpus)):
        pair=corpus.by_index(i)
        assert pair.map_uid not in all_ids
        all_ids.add(pair.map_uid)
        assert pair.layout.map_uid==pair.trajectory.map_uid
        assert not pair.layout.has_exact_collision_mesh
        assert not pair.trajectory.counterfactual_simulation_supported
        valid_frames+=len(pair.trajectory.data)
        states=list(pair.trajectory.valid_transitions())
        assert len(states)>2
        for a,b in states[:20]:
            assert b["tMs"]-a["tMs"]==50
            assert b["tMs"]<=pair.trajectory.race_ms
        t0=pair.trajectory.data[0]["tMs"]
        assert pair.trajectory.frame_at(t0)["tMs"]==t0
    assert len(train)+len(test)==len(corpus)
    mesh=ROOT/"local/tests/one-triangle.obj"
    with PartialCollisionWorld(mesh) as w:
        assert w.triangle_count==1
        rays=np.array([[.25,.25,1,0,0,-1,2],[.75,.75,1,0,0,-1,2]],dtype=np.float64)
        hit=w.raycast(rays)
        assert hit.shape==(2,9)
        assert hit[0,0]==1 and abs(hit[0,1]-1)<1e-10
        assert hit[1,0]==0 and math.isnan(hit[1,1])
        try:
            w.raycast(np.array([[0,0,0,0,0,0,2.]],dtype=np.float64))
            raise AssertionError("Zero direction should fail")
        except ValueError:pass
    sample_obj=ROOT/"local/collision/365553/embedded_physical_shapes.obj"
    with PartialCollisionWorld(sample_obj) as w:
        assert w.triangle_count==43595
        replay=next(corpus.by_index(i) for i in range(len(corpus))
                    if corpus.by_index(i).tmx_id==365553).trajectory
        points=np.asarray([r["position"] for r in replay.data])
        start=time.perf_counter()
        rays=w.downcast(points)
        elapsed=time.perf_counter()-start
        assert rays.shape==(len(points),9)
        assert int(rays[:,0].sum())==3, int(rays[:,0].sum())
        rps=round(len(points)/max(elapsed,1e-6))
    output={
        "schema":"tm2020_sdk_validation_v1",
        "maps":len(corpus),"trainMapCount":len(train),"testMapCount":len(test),
        "replayVehicleSamples":valid_frames,
        "nativeBVHTriangles":43595,
        "realReplayGroundProbeHits":3,
        "realReplayGroundProbeSamples":len(points),
        "nativeDllMeasuredBatchRaysPerSecond":rps,
        "counterfactualPhysicsAvailable":False,
        "validated":True
    }
    out=ROOT/"local/sdk_validation.json"
    out.write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8")
    print("PASS",json.dumps(output,ensure_ascii=False))
if __name__=="__main__":main()
