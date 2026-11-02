#!/usr/bin/env python3
"""Robust feedback search for the upstream internal input path, in simulation.

Assisted per-map controller, not PPO. Real normal input history, four fixed
development seeds, then 64 disjoint seeds. Failure latches until reset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from hybrid_tracking import load_asset,save_asset
from tune_hybrid_tracking import NativeEvaluator
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def rank(rows):
    times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    if len(times)!=len(rows):
        return (len(times),sum(r['checkpoints'] for r in rows),sum(r.get('maximumReferenceIndex',0) for r in rows),-sum(times))
    return (len(times),-max(times),-float(np.mean(times)),0)


def gains(parameters):return np.r_[parameters[:4],10**parameters[4],0.]


def paired_baseline(out):
    path=out/'qualification.json';q=json.loads(path.read_text());m=q['map'];source=out/'source.tmhyb'
    ref,g,_=load_asset(source,map_path=m['map'],uid=m['mapUid'])
    ev=NativeEvaluator(8,source,api_path=ROOT/'native/build-replay-0.68/libtm2020_vector_physics.so',
        library=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so',map_path=m['map'],
        horizon=len(ref)+800,internal_controls=False,fast_evaluation=True)
    rows=[]
    try:
        for k in range(0,64,8):rows.extend(ev.evaluate(g,q['cases'][k:k+8])[0])
    finally:ev.close()
    times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    q['pairedBaseline']={'modelSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'finishes':len(times),'count':64,'bestMs':min(times) if times else None,
        'meanMs':float(np.mean(times)) if times else None,'medianMs':float(np.median(times)) if times else None,
        'targetFinishes':sum(t<=m['top10TargetMs'] for t in times),'trials':rows}
    pairs=[(a['finishMs'],b['finishMs']) for a,b in zip(q['trials'],rows)]
    q['pairedOutcomes']={'candidateOnlyFinishes':sum(a is not None and b is None for a,b in pairs),
        'baselineOnlyFinishes':sum(a is None and b is not None for a,b in pairs),
        'bothFinish':sum(a is not None and b is not None for a,b in pairs),
        'candidateFasterWhenBothFinish':sum(a<b for a,b in pairs if a is not None and b is not None)}
    q['automaticDeployment']=False;save_json(path,q)
    print(json.dumps({'pairedValidationMap':m['index'],'candidateFinishes':q['finishes'],
        'baselineFinishes':len(times),'candidateTop10Finishes':q['targetFinishes'],
        'baselineTop10Finishes':q['pairedBaseline']['targetFinishes']}),flush=True)


def tune(index,a):
    out=a.output/f'{index:02d}';out.mkdir(parents=True,exist_ok=False)
    state=json.loads((ROOT/f'local/training/fall-campaign-world-records-0.57/{index:02d}/pursuit.json').read_text());m=state['goal']
    source=out/'source.tmhyb';source.write_bytes(Path(state['bestAsset']).read_bytes())
    ref,g,nn=load_asset(source,map_path=m['map'],uid=m['mapUid'])
    rng=np.random.default_rng(690100+index)
    seeds=[int(x) for x in rng.integers(1,2**32-1,4,dtype=np.uint32)]
    dev=[{'seed':s,'warm':0,'duration':0,'kick':0.} for s in seeds]
    validation=[{'seed':int(s),'warm':0,'duration':0,'kick':0.} for s in rng.integers(1,2**32-1,64,dtype=np.uint32)]
    assert not set(seeds)&{c['seed'] for c in validation}
    center=np.r_[g[:4],np.log10(max(g[4],.0001))];spread=np.array([.2,.15,1.,.4,.5]);floor=np.array([.015,.01,.05,.02,.05])
    ev=NativeEvaluator(64,source,api_path=ROOT/'native/build-replay-0.68/libtm2020_vector_physics.so',
        library=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so',map_path=m['map'],
        horizon=len(ref)+800,internal_controls=False,fast_evaluation=True)
    best=None;stale=0
    save_json(out/'protocol.json',{'map':m,'algorithm':'CEM feedback gains','developmentCases':dev,'validationCases':validation,
        'normalInputHistory':True,'policyFailureLatched':True,'simulationOnly':True,'gameAccessed':False,
        'population':16,'developmentSeedsPerCandidate':4,'maximumGenerations':a.generations,'plateauGenerations':a.plateau})
    started=time.monotonic()
    try:
        for generation in range(a.generations):
            population=center+rng.normal(size=(16,5))*spread
            population[:,:2]=np.clip(population[:,:2],-2,2);population[:,2]=np.clip(population[:,2],-8,8)
            population[:,3]=np.clip(population[:,3],-2,2);population[:,4]=np.clip(population[:,4],-4,0)
            population[0]=center if best is None else best['parameters']
            if generation==0:
                population[1:5]=np.array([[.05,.03,1.,.1,-2],[-.05,-.03,1.,-.3,-2],[-.1,.1,1.,-.5,-2],[.1,-.1,1.,.5,-2]])
                population[5]=[0,0,0,0,-2]
            all_gains=np.repeat(np.array([gains(p) for p in population]),4,axis=0)
            rows,seconds=ev.evaluate(all_gains,dev*16)
            records=[{'parameters':p.tolist(),'gains':gains(p).tolist(),'trials':rows[k*4:k*4+4],
                      'key':rank(rows[k*4:k*4+4])} for k,p in enumerate(population)]
            records.sort(key=lambda r:r['key'],reverse=True)
            changed=best is None or tuple(records[0]['key'])>tuple(best['key'])
            if changed:
                best=dict(records[0],generation=generation);stale=0
                save_asset(out/'best.tmhyb',ref,best['gains'],nn,map_path=m['map'],uid=m['mapUid'])
                save_json(out/'best.json',best)
            else:stale+=1
            elite=np.array([r['parameters'] for r in records[:4]])
            center=elite.mean(axis=0)
            # The initial deterministic baselines are not a CEM sample.
            if generation:spread=np.maximum(elite.std(axis=0),floor)
            status={'mapIndex':index,'generation':generation,'seconds':seconds,'elapsedSeconds':time.monotonic()-started,
                'stale':stale,'best':best,'normalInputHistory':True,'simulationOnly':True}
            save_json(out/'status.json',status)
            print(json.dumps({'map':index,'generation':generation,'finishes':best['key'][0],
                'times':[r['finishMs'] for r in best['trials']],'stale':stale}),flush=True)
            if stale>=a.plateau:break
    finally:ev.close()
    ev=NativeEvaluator(8,out/'best.tmhyb',api_path=ROOT/'native/build-replay-0.68/libtm2020_vector_physics.so',
        library=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so',map_path=m['map'],
        horizon=len(ref)+800,internal_controls=False,fast_evaluation=True)
    rows=[]
    try:
        for k in range(0,64,8):rows.extend(ev.evaluate(best['gains'],validation[k:k+8])[0])
    finally:ev.close()
    times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    save_json(out/'qualification.json',{'map':m,'model':str((out/'best.tmhyb').resolve()),
        'modelSha256':hashlib.sha256((out/'best.tmhyb').read_bytes()).hexdigest(),'finishes':len(times),'count':64,
        'targetFinishes':sum(t<=m['top10TargetMs'] for t in times),'bestMs':min(times) if times else None,
        'meanMs':float(np.mean(times)) if times else None,'medianMs':float(np.median(times)) if times else None,
        'worstMs':max(times) if times else None,'cases':validation,'trials':rows,
        'normalInputHistory':True,'policyFailureLatched':True,'simulationOnly':True,'clientVerified':False})
    paired_baseline(out)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--maps',type=int,nargs='+',default=[3,6]);p.add_argument('--generations',type=int,default=128)
    p.add_argument('--qualify-existing',action='store_true',help='Add paired baseline evidence to completed qualifications')
    p.add_argument('--plateau',type=int,default=24);a=p.parse_args()
    if a.generations<1 or a.plateau<1:p.error('Positive generation and plateau limits required')
    for i in a.maps:
        if a.qualify_existing:paired_baseline(a.output/f'{i:02d}')
        else:tune(i,a)


if __name__=='__main__':main()
