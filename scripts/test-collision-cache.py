#!/usr/bin/env python3
"""Native collision cache equivalence test. No game I/O or physics claims."""
from pathlib import Path
import sys
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"sdk"))
from trackmania2020 import PartialCollisionWorld
DATA=ROOT/"local"/"collision"
def compare(mapid:int):
    parent=DATA/str(mapid)
    original=parent/"embedded_physical_shapes.obj"
    cached=parent/"embedded_physical_shapes.tmcol"
    if not original.exists() or not cached.exists():
        raise FileNotFoundError(f"Missing original or cached collider for TMX {mapid}")
    t0=time.perf_counter()
    with PartialCollisionWorld(original) as a:
        load_obj_ms=(time.perf_counter()-t0)*1000
        t1=time.perf_counter()
        with PartialCollisionWorld(cached) as b:
            load_cached_ms=(time.perf_counter()-t1)*1000
            if a.triangle_count!=b.triangle_count:
                raise AssertionError("Triangle counts do not match")
            rng=np.random.default_rng(3214+mapid)
            sample=np.empty((1200,7),dtype=np.float64)
            sample[:,:3]=rng.uniform([-200,0,-200],[1800,350,1800],size=(1200,3))
            sample[:,3:6]=rng.normal(size=(1200,3))
            sample[:,6]=rng.uniform(0.01,700,size=1200)
            va=a.raycast(sample);vb=b.raycast(sample)
            if not np.array_equal(va[:,0],vb[:,0]):
                raise AssertionError("Different hit/miss mask")
            if not np.allclose(va,vb,atol=1e-10,rtol=1e-10,equal_nan=True):
                raise AssertionError("Different geometry ray results")
            print(f"PASS TMX {mapid}: {a.triangle_count} tris, 1200 identical rays, "
                  f"OBJ load {load_obj_ms:.2f} ms vs tmcol {load_cached_ms:.2f} ms")
if __name__=="__main__":
    for mid in (365553,364956):compare(mid)
