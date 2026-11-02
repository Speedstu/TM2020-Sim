#!/usr/bin/env python3
"""Initialize physical route targets with genuine normal-input full rollouts.

Human actions are demonstration seeds, not deployed playback. The exported
hardcode localizes on live physical state, applies feedback and a hard human
governor, and is subsequently optimized on lap time and low-median rhythm.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset,save_asset
from train_hardcode_recorded_inputs import ROOT,BASE,NATIVE,PHYSICS,human_action_constraints,benchmark_cases,rank
from vector_physics import VectorPhysics
from tune_hybrid_tracking import NativeEvaluator
from prepare_fall_campaign import save_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--map',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--ranks',type=int,nargs='+',default=[1,2,3,5,10]);a=p.parse_args()
    m=json.loads((ROOT/f'local/training/fall-campaign-0.52/{a.map:02d}/map.json').read_text())
    folder=a.output/f'{a.map:02d}';out=folder/'normal-route-bootstrap';out.mkdir(parents=True,exist_ok=True)
    constraints=human_action_constraints(a.map)
    retained=folder/'historical-champion.tmhyb'
    if not retained.exists():
        import shutil
        sources=[ROOT/f'local/training/hardcode-human-0.74/{a.map:02d}/historical-champion.tmhyb',
                 *list((BASE/f'preserved/{a.map:02d}').glob('*.tmhyb'))]
        shutil.copy2(next(p for p in sources if p.exists()),retained)
    _,original_g,_=load_asset(retained,map_path=m['map'],uid=m['mapUid'])
    cohort=BASE/f'top100-cohort/{a.map:02d}';sources=[]
    for r in a.ranks:
        d=cohort/f'leaderboard-rank{r:03d}'
        if (d/'analysis.json').exists() and (d/'timeline.npz').exists():sources.append((r,d))
    n=len(sources)
    if not n:raise ValueError('No decoded human sources')
    data=[]
    for r,d in sources:
        with np.load(d/'timeline.npz') as z:commands=z['controls'].astype(np.float32)
        meta=json.loads((d/'analysis.json').read_text());data.append((r,commands,meta))
    horizon=max(len(c) for _,c,_ in data)+80
    traces=[[] for _ in range(n)];active=np.ones(n,dtype=bool);outcomes=[]
    with VectorPhysics(n,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
            map_path=m['map'],horizon=horizon,normal_inputs=True) as env:
        for lane,(_,c,meta) in enumerate(data):env.reset(lane,int(meta['validationSeed']))
        for tick in range(horizon):
            if not active.any():break
            actions=np.zeros((n,3),dtype=np.float32)
            for lane,(_,c,meta) in enumerate(data):
                if not active[lane]:continue
                s=env.states[lane]
                if s.terminated or s.truncated:active[lane]=False;continue
                action=c[min(tick,len(c)-1)].copy()
                rigid=np.asarray(s.rigid_words,dtype=np.uint32).view(np.float32).copy()
                traces[lane].append(np.concatenate((rigid,action)).astype(np.float32));actions[lane]=action
            env.step(actions)
        for lane,(r,c,meta) in enumerate(data):
            s=env.states[lane];outcomes.append({'rank':r,'seed':meta['validationSeed'],
                'declaredMs':meta['declaredMs'],'normalSimFinishMs':int(s.finish_ms),'checkpoints':int(s.checkpoints),
                'tailHoldTicks':max(0,len(traces[lane])-len(c)),'referenceWrittenIntoPhysics':False})
    assets=[]
    for lane,result in enumerate(outcomes):
        if result['normalSimFinishMs']<0:continue
        ref=np.asarray(traces[lane]);ref_path=out/f"rank{result['rank']:03d}-physical-route.npy";np.save(ref_path,ref)
        for label,g in [('retained-feedback',original_g),('zero',np.array([0,0,0,0,.001,0])),
                ('light',np.array([-.03,-.02,.8,-.15,.001,0]))]:
            g=g.copy();g[5]=0;asset=out/f"rank{result['rank']:03d}-{label}.tmhyb"
            save_asset(asset,ref,g,map_path=m['map'],uid=m['mapUid'],version=7,
                feedback_filter=np.array([0.,0.,10.]),human_constraints=constraints)
            assets.append(asset)
    report={'map':a.map,'sourceOutcomes':outcomes,'candidates':[],'normalHistory':True,'clientVerified':False}
    if assets:
        cases=benchmark_cases(a.map,horizon);trials=cases['normal64'][:8]+cases['perturbed64'][:8]
        ev=NativeEvaluator(16,assets[0],api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
            map_path=m['map'],horizon=horizon+600,fast_evaluation=True)
        ranked=[]
        try:
            for asset in assets:
                _,g,_=load_asset(asset,map_path=m['map'],uid=m['mapUid'])
                rows,_=ev.evaluate(g,trials,assets=[asset]*16)
                key=rank(rows,None,m['targetMs']);ranked.append((key,asset))
                report['candidates'].append({'asset':str(asset.resolve()),'finishes':sum(r['finishMs'] is not None for r in rows),
                    'top10':sum(r['finishMs'] is not None and r['finishMs']<=m['targetMs'] for r in rows),'rows':rows})
        finally:ev.close()
        ranked.sort(key=lambda x:x[0],reverse=True);best=ranked[0][1]
        report['bestAsset']=str(best.resolve());report['bestFinishes']=next(c['finishes'] for c in report['candidates'] if c['asset']==str(best.resolve()))
    save_json(out/'report.json',report)
    print(json.dumps({'map':a.map,'sourceOutcomes':outcomes,'screen':[{k:c[k] for k in ('asset','finishes','top10')} for c in report['candidates']],
        'bestAsset':report.get('bestAsset'),'bestFinishes':report.get('bestFinishes',0)},indent=2),flush=True)

if __name__=='__main__':main()
