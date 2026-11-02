#!/usr/bin/env python3
"""Offline upper-bound diagnostic: replay one verified ghost on matched seeds."""
import argparse, json
from pathlib import Path
import numpy as np
from diagnose_human_01_feasibility import read_human_inputs
from prepare_fall_campaign import ROOT, save_json
from train_hardcode_recorded_inputs import benchmark_cases, NATIVE, PHYSICS
from vector_physics import VectorPhysics


def run(map_index, rank, family, count=64):
    meta, analysis, timeline, decoded, controls=read_human_inputs(map_index,rank)
    cases=benchmark_cases(map_index,len(controls))[family][:count]
    rows=[]
    for offset in range(0,len(cases),8):
        batch=cases[offset:offset+8]; n=len(batch)
        with VectorPhysics(n,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',
                           library=PHYSICS,map_path=meta['map'],horizon=len(controls)+700,
                           normal_inputs=True) as env:
            for i,c in enumerate(batch):env.reset(i,int(c['seed']))
            for t in range(len(controls)):
                act=np.repeat(controls[t:t+1],n,axis=0).copy()
                for i,c in enumerate(batch):
                    if c['warm']<=t<c['warm']+c['duration']:
                        act[i,2]=np.clip(act[i,2]+c['kick'],-1,1)
                act[:,2]=np.sign(act[:,2])*np.floor(np.abs(act[:,2])*127+.5)/127
                env.step(act)
                if all(s.terminated or s.truncated for s in env.states[:n]):break
            rows.extend([dict(c,finishMs=int(s.finish_ms) if s.finish_ms>=0 else None,
                              checkpoints=int(s.checkpoints),ticks=int(s.tick))
                         for c,s in zip(batch,env.states[:n])])
    ts=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    return {'count':len(rows),'finishes':len(ts),'finishRate':len(ts)/len(rows),
            'meanMs':float(np.mean(ts)) if ts else None,'medianMs':float(np.median(ts)) if ts else None,
            'bestMs':min(ts) if ts else None,'checkpointHistogram':{
                str(k):sum(r['checkpoints']==k for r in rows) for k in sorted({r['checkpoints'] for r in rows})},
            'trials':rows}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--map',type=int,default=3)
    ap.add_argument('--rank',type=int,default=1);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();out={family:run(a.map,a.rank,family) for family in ('normal64','perturbed64')}
    save_json(a.output,{'map':a.map,'ghostRank':a.rank,'sameSeedsAsQualification':True,
        'sourceIsVerifiedRawGhost':True,'botPolicyTested':False,'results':out})
    print(json.dumps({k:{x:v[x] for x in ('finishes','count','meanMs','bestMs','checkpointHistogram')}
                      for k,v in out.items()},indent=2));print(f'report: {a.output}')

if __name__=='__main__':main()
