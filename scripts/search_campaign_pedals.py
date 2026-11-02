#!/usr/bin/env python3
"""Full-start brake/gas timing grid; fixed physics, steering and feedback."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset,save_asset
from tune_hybrid_tracking import NativeEvaluator
from optimize_fall_campaign import trial_cases,summary
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def retime(ref,brake_ticks,gas_ticks,start=20,end=None):
    r=ref.copy();end=len(ref) if end is None else min(end,len(ref));t=np.arange(start,end)
    for column,offset in ((23,brake_ticks),(22,gas_ticks)):
        r[start:end,column]=ref[np.clip(t-int(offset),0,len(ref)-1),column]
    return r


def search(index,source,output):
    state=json.loads((source/f'{index:02d}/pursuit.json').read_text());m=dict(state['goal'])
    m.update(targetRank=10,targetMs=m['top10TargetMs'],targetExclusive=False)
    ref,g,network=load_asset(state['bestAsset'],map_path=m['map'],uid=m['mapUid'])
    d=output/f'{index:02d}';d.mkdir(parents=True,exist_ok=True)
    grid=[(b,gas) for b in range(-8,8) for gas in (-2,-1,0,1)];grid[0]=(0,0);assets=[]
    for i,(b,gas) in enumerate(grid):
        p=d/f'candidate-{i}.tmhyb';save_asset(p,retime(ref,b,gas),g,network,map_path=m['map'],uid=m['mapUid']);assets.append(p)
    native=ROOT/'local/training/campaign-speed-0.66/native'
    ev=NativeEvaluator(64,assets[0],api_path=native/'libtm2020_vector_physics.so',
        library=native/'libtm2020_speed.so',map_path=m['map'],horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
    try:
        cases=trial_cases(67000+index,64,len(ref),False);rows,seconds=ev.evaluate(g,cases,assets=assets)
        ranked=sorted(range(64),key=lambda i:(rows[i]['finishMs'] is not None,
            -(rows[i]['finishMs'] or 10**9),rows[i]['checkpoints'],rows[i].get('maximumReferenceIndex',0)),reverse=True)
        save_json(d/'grid.json',{'parameters':grid,'trials':rows,'seconds':seconds,'originalModel':state['bestAsset'],
            'originalSha256':hashlib.sha256(Path(state['bestAsset']).read_bytes()).hexdigest(),'simulationOnly':True})
        winner=ranked[0];best=d/'best.tmhyb';best.write_bytes(assets[winner].read_bytes());ev.asset=best
        dev=trial_cases(52000+index*100+1,64,len(ref),False)
        dev[1].update(warm=5,duration=2,kick=.02);dev[2].update(duration=2,kick=-.02);dev[3].update(warm=15,duration=2,kick=-.02)
        runs,_=ev.evaluate(g,dev)
        result={'map':m,'model':str(best.resolve()),'modelSha256':hashlib.sha256(best.read_bytes()).hexdigest(),
            'referenceReproduction':json.loads((source/f'{index:02d}/reference.json').read_text()),
            'development':summary(runs[:4],m['targetMs']),'assisted':True,'gameVerified':False,
            'generation':0,'stopReason':'pedal_timing_grid','pedalOffsetsTicks':grid[winner]}
        for name,perturbed in (('nominal64',False),('perturbed64',True)):
            c=trial_cases(67900+index+int(perturbed),64,len(ref),perturbed);runs,_=ev.evaluate(g,c)
            q=summary(runs,m['targetMs']);save_json(d/f'{name}.json',q)
            q.update(internalPhysicalControls=True,launchRandomization=False)
            if not perturbed:q['effectiveDistinctNominalConditions']=1
            result[name]={k:v for k,v in q.items() if k!='trials'}
        result['simGoalPassed']=result['nominal64']['targetFinishes']==64
        save_json(d/'result.json',result)
        print(json.dumps({'map':index,'pedalOffsets':grid[winner],'baselineMs':rows[0]['finishMs'],
            'bestMs':rows[winner]['finishMs'],'nominal64':result['nominal64'],'perturbed64':result['perturbed64']}),flush=True)
        for path in assets:path.unlink()
        return result
    finally:ev.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--maps',type=int,nargs='+',required=True)
    p.add_argument('--source',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    for index in a.maps:search(index,a.source.resolve(),a.output.resolve())


if __name__=='__main__':main()
