#!/usr/bin/env python3
"""Measure energy-conscious native vector-physics worker count, same rollout cases."""
import argparse
import hashlib
import json
import os
import time
import numpy as np
from vector_physics import VectorPhysics
from fast_engine import State48
import ctypes as C

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--steps',type=int,default=160)
    p.add_argument('--envs',type=int,default=16)
    p.add_argument('--workers',nargs='+',type=int,default=[16,8,4,2])
    a=p.parse_args()
    output=[]
    for w in a.workers:
        os.environ['TM2020_PHYSICS_WORKERS']=str(w)
        with VectorPhysics(a.envs) as e:
            for i in range(a.envs):e.reset(i,1000+i)
            h=hashlib.sha256()
            start_cpu=time.process_time()
            start=time.perf_counter()
            for t in range(a.steps):
                controls=np.empty((a.envs,3),dtype=np.float32)
                controls[:,0]=1.
                controls[:,1]=0.
                controls[:,2]=np.sin(np.arange(a.envs)*.5+t*.02)*.7
                e.step(controls)
                h.update(C.string_at(C.addressof(e.states.contents),C.sizeof(State48)*a.envs))
                for i,state in enumerate(e.states[:a.envs]):
                    if state.terminated or state.truncated:
                        e.reset(i,1000+i+t*100)
            elapsed=time.perf_counter()-start
            cpu=time.process_time()-start_cpu
        result={'workers':w,'seconds':round(elapsed,4),
                 'envStepsPerSec':round(a.steps*a.envs/elapsed,1),
                 'cpuProcessSeconds':round(cpu,4),'sha256':h.hexdigest()}
        output.append(result)
        print(json.dumps(result),flush=True)
    print('PARITY',len({r['sha256'] for r in output})==1,flush=True)
if __name__=='__main__':main()
