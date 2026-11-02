#!/usr/bin/env python3
"""Measure feedback filtering from complete race resets, without live access."""
import argparse
import json
from pathlib import Path
import numpy as np
from audit_replay_controls import metrics
from hybrid_tracking import Hybrid,load_asset,save_asset,cases
from tune_hybrid_tracking import NativeEvaluator
from vector_physics import VectorPhysics
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT

NATIVE=ROOT/'native/build-replay-0.68'
PHYSICS=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so'


def rollout(asset,m,limit):
    controls=[];fault=False
    with VectorPhysics(1,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
            map_path=m['map'],horizon=limit,internal_controls=True) as env,Hybrid(asset,1) as policy:
        env.reset(0,68000+m['index'])
        for t in range(limit):
            s=env.states[0]
            if s.reserved or s.terminated or s.truncated:break
            a=policy.act(env)[0]
            if policy.features[0,11]==0:fault=True
            controls.append(a);env.step(a[None,:])
        s=env.states[0];finish=int(s.finish_ms) if s.finish_ms>=0 else None
    return {'finishMs':finish,'guardObserved':fault,'controls':metrics(controls)}


def screen(index,out,source):
    state=json.loads((source/f'{index:02d}/pursuit.json').read_text());m=state['goal'];d=out/f'{index:02d}';d.mkdir(parents=True,exist_ok=True)
    baseline=d/'baseline.tmhyb';baseline.write_bytes(Path(state['bestAsset']).read_bytes())
    ref,g,nn=load_asset(baseline,map_path=m['map'],uid=m['mapUid'])
    variants=[('baseline',baseline,None)]
    for raw,interval in ((.5,10),(1,10),(2,10),(3,10),(1,20),(2,20),(3,20),(1,30),(2,30)):
        f=[raw/127,0.,interval];p=d/f'deadband{raw}-hold{interval}.tmhyb'
        save_asset(p,ref,g,nn,map_path=m['map'],uid=m['mapUid'],version=3,feedback_filter=f)
        variants.append((p.stem,p,f))
    records=[]
    for name,asset,f in variants:
        r=rollout(asset,m,len(ref)+1000);r.update(name=name,asset=str(asset),feedbackFilter=f)
        records.append(r);save_json(d/'screen.json',{'mapIndex':index,'variants':records,'simulationOnly':True})
        print(json.dumps({'map':index,'name':name,'finishMs':r['finishMs'],'reversals':r['controls']['directionReversalsOfSteeringChanges'],'guard':r['guardObserved']}),flush=True)
    original=records[0];eligible=[r for r in records[1:] if r['finishMs'] is not None and not r['guardObserved'] and
        r['finishMs']<=m['top10TargetMs'] and r['finishMs']<=original['finishMs']+10 and
        r['controls']['directionReversalsOfSteeringChanges']<original['controls']['directionReversalsOfSteeringChanges']]
    if not eligible:return
    winner=min(eligible,key=lambda r:(r['controls']['directionReversalsOfSteeringChanges'],r['finishMs']))
    trials=cases(68000+index,64,True);results={}
    # Paired conditions and bounded eight-environment chunks to leave RAM for
    # the campaign search and official client. No fresh seed selection.
    with_eval=[]
    try:
        for record in (original,winner):
            ev=NativeEvaluator(8,record['asset'],api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
                map_path=m['map'],horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
            with_eval.append(ev);rows=[]
            for k in range(0,len(trials),8):rows.extend(ev.evaluate(g,trials[k:k+8])[0])
            times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
            results[record['name']]={'finishes':len(times),'count':len(rows),'meanMs':float(np.mean(times)) if times else None,
                'medianMs':float(np.median(times)) if times else None,'bestMs':min(times) if times else None,'trials':rows}
            ev.close();with_eval.remove(ev)
    finally:
        for ev in with_eval:ev.close()
    save_json(d/'paired-qualification.json',{'cases':trials,'baseline':original,'candidate':winner,
        'results':results,'simulationOnly':True,'gameValidated':False,'replayInputRecordingFixed':False})
    print(json.dumps({'map':index,'candidate':winner['name'],'pairedFinishes':{n:r['finishes'] for n,r in results.items()}}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--maps',type=int,nargs='+',default=[3,6]);p.add_argument('--source',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    a=p.parse_args()
    for i in a.maps:screen(i,a.output.resolve(),a.source)


if __name__=='__main__':main()
