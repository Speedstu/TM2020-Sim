#!/usr/bin/env python3
"""Search a local geometric margin around a measured failed section.

Explicit simulator launch uncertainty represents the observed client mismatch.
No game physics edits, teleports, midrace resets or teacher forcing.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from hybrid_tracking import load_asset,save_asset
from tune_hybrid_tracking import NativeEvaluator
from optimize_fall_campaign import trial_cases,summary
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map-index',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--center',type=int,required=True)
    p.add_argument('--pedal-search',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    b=json.loads((ROOT/f'local/recon/campaign-play-0.60/bundle/{a.map_index:02d}/candidate.json').read_text())
    ref,g,net=load_asset(b['model'],map_path=b['map'],uid=b['mapUid']);t=np.arange(len(ref))
    api=ROOT/'native/build-transfer-0.64/libtm2020_vector_physics.so'
    lib=ROOT/'cache/transfer-uncertainty-0.63-target/release/libtm2020_speed.so'
    evaluator=NativeEvaluator(64,b['model'],api_path=api,map_path=b['map'],horizon=len(ref)+1200,
        library=lib,internal_controls=True,fast_evaluation=True)
    candidates=[(amp,a.center+shift,width) for amp in (-2.,-1.5,-1.,-.5,.5,1.,1.5,2.) for shift in (-60,-20,20,60) for width in (60,120)]
    candidates[0]=(0.,a.center,100);assets=[]
    if a.pedal_search:
        candidates=[(duration,start,brake) for duration in (1,2,3,5,8,12,20,30) for start in (1200,1350,1450,1550) for brake in (False,True)]
        candidates[0]=(0,1200,False)
    for i,(amp,center,width) in enumerate(candidates):
        r=ref.copy()
        if a.pedal_search:
            if width:r[center:center+amp,23]=1.
            else:r[center:center+amp,22]=0.
        else:
            offset=amp*np.exp(-.5*((t-center)/width)**2)
            r[:,9:12]+=offset[:,None]*ref[:,[0,3,6]]
        path=a.output/f'candidate-{i}.tmhyb';save_asset(path,r,g,net,map_path=b['map'],uid=b['mapUid']);assets.append(path)
    cases=trial_cases(64000+a.map_index,64,len(ref),False)
    for c in cases:c['launchDeltaMps']=-.01
    started=time.monotonic()
    try:
        rows,seconds=evaluator.evaluate(g,cases,assets=assets)
        ranked=[]
        for i,row in enumerate(rows):
            score=(int(row['finishMs'] is not None),row['checkpoints'],
                -row['finishMs'] if row['finishMs'] is not None else row.get('maximumReferenceIndex',0))
            ranked.append((score,i,row))
        ranked.sort(reverse=True)
        save_json(a.output/'grid.json',{'cases':cases,'candidates':candidates,'trials':rows,'seconds':seconds,
            'map':b,'launchDeltaMps':-.01,'simulationOnly':True,'pedalSearch':a.pedal_search})
        for score,i,row in ranked[:8]:print(json.dumps({'candidate':i,'parameters':candidates[i],'score':score,'trial':row}),flush=True)
        best=None
        for rank,(score,i,row) in enumerate(ranked[:4]):
            evaluator.asset=assets[i]
            cases=trial_cases(64900+a.map_index,64,len(ref),True);rng=np.random.default_rng(64009+a.map_index)
            for c in cases:c['launchDeltaMps']=float(rng.uniform(-.012,-.008))
            cases[0].update(launchDeltaMps=-.01,kick=0.)
            runs,seconds=evaluator.evaluate(g,cases);s=summary(runs,b['top10ThresholdMs'])
            record={'candidate':i,'parameters':candidates[i],'nominalDevelopment':row,'qualification':s,
                'cases':cases,'asset':str(assets[i]),'version':1,'actualClientFinishVerified':False}
            save_json(a.output/f'qualification-{rank}.json',record)
            key=(int(runs[0]['finishMs'] is not None),s['finishes'],-(s['meanMs'] or 10**9))
            if best is None or key>best[0]:best=(key,record)
            print(json.dumps({'rank':rank,'nominalMs':runs[0]['finishMs'],'finishes':s['finishes'],'meanMs':s['meanMs']}),flush=True)
        save_json(a.output/'best.json',best[1]);(a.output/'best.tmhyb').write_bytes(Path(best[1]['asset']).read_bytes())
        print(json.dumps({'wallSeconds':time.monotonic()-started,'best':best[1]['parameters']}),flush=True)
    finally:evaluator.close()


if __name__=='__main__':main()
