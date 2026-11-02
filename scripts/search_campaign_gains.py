#!/usr/bin/env python3
"""Screen feedback gains on a fixed reference; qualify actual full-start runs."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset,save_asset
from tune_hybrid_tracking import NativeEvaluator
from optimize_fall_campaign import trial_cases,summary
from rebase_campaign_prefix import evaluate_cases
from distill_campaign_run import distill,NATIVE
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map-index',type=int,required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--campaign',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    a=p.parse_args();d=a.output.resolve();d.mkdir(parents=True,exist_ok=True)
    state=json.loads((a.campaign/f'{a.map_index:02d}/pursuit.json').read_text());m=dict(state['goal']);m.update(targetRank=10,targetMs=m['top10TargetMs'],targetExclusive=False)
    ref,g,net=load_asset(a.model,map_path=m['map'],uid=m['mapUid']);source=d/'source.tmhyb';source.write_bytes(a.model.read_bytes())
    gains=np.asarray([[g[0]*scale,g[1]*scale,heading,g[3]*.5,phase,0.]
        for scale in (.5,1.,1.5,2.) for heading in (.15,.5,1.,2.) for phase in (.0001,.01,.1,1.)]);gains[0]=g
    ev=NativeEvaluator(16,source,api_path=NATIVE/'libtm2020_vector_physics.so',library=NATIVE/'libtm2020_speed.so',
        map_path=m['map'],horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
    try:
        cases=[dict(seed=36139877,warm=0,duration=0,kick=0.) for _ in range(16)];trials=[]
        for start in range(0,64,16):
            runs,_=ev.evaluate(gains[start:start+16],cases);trials.extend(runs)
        ranking=sorted(range(64),key=lambda i:(trials[i]['finishMs'] is not None,trials[i]['checkpoints'],
            -(trials[i]['finishMs'] or 10**9),trials[i].get('maximumReferenceIndex',0)),reverse=True)
        save_json(d/'grid.json',{'gains':gains.tolist(),'trials':trials,'source':str(source)})
        index=ranking[0];chosen=gains[index];asset=d/'best.tmhyb';save_asset(asset,ref,chosen,net,map_path=m['map'],uid=m['mapUid'])
        print(json.dumps({'map':a.map_index,'baseline':trials[0],'best':trials[index],'gains':chosen.tolist()}),flush=True)
        if trials[index]['finishMs'] is not None:
            ev.close();distill(asset,m,cases[0],d/'distilled');return
        ev.asset=asset
        dev=trial_cases(52000+a.map_index*100+1,16,len(ref),False)
        dev[0].update(seed=36139877);dev[1].update(warm=5,duration=2,kick=.02)
        dev[2].update(duration=2,kick=-.02);dev[3].update(warm=15,duration=2,kick=-.02)
        rows=evaluate_cases(ev,chosen,dev)
        result={'map':m,'model':str(asset),'modelSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
            'development':summary(rows[:4],m['targetMs']),'generation':0,'stopReason':'feedback_grid',
            'assisted':True,'gameVerified':False}
        for name,perturbed in (('nominal64',False),('perturbed64',True)):
            cases=trial_cases(67600+a.map_index+int(perturbed),64,len(ref),perturbed);rows=evaluate_cases(ev,chosen,cases)
            q=summary(rows,m['targetMs']);save_json(d/f'{name}.json',q);q.update(internalPhysicalControls=True,launchRandomization=False)
            if not perturbed:q['effectiveDistinctNominalConditions']=1
            result[name]={k:v for k,v in q.items() if k!='trials'}
        result['simGoalPassed']=result['nominal64']['targetFinishes']==64;save_json(d/'result.json',result)
    finally:ev.close()


if __name__=='__main__':main()
