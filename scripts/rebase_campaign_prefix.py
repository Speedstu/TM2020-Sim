#!/usr/bin/env python3
"""Repair a reference discontinuity after a physically recorded good prefix.

All candidates run from race zero. A recorded prefix is a control target, not
a simulator state reset. Only genuine arrivals or strictly more checkpoints
may be submitted to the campaign; index padding cannot count as improvement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import Hybrid,load_asset,save_asset
from vector_physics import VectorPhysics
from tune_hybrid_tracking import NativeEvaluator
from optimize_fall_campaign import trial_cases,summary
from prepare_fall_campaign import save_json
from distill_campaign_run import NATIVE
from run_fast_ppo import ROOT


def extend_terminal(reference,count=200):
    extension=np.repeat(reference[-1:],count,axis=0)
    seconds=np.arange(1,count+1,dtype=np.float32)*.01
    extension[:,9:12]+=seconds[:,None]*reference[-1,16:19]
    return np.concatenate((reference,extension))


def make_reference(reference,rows,cut,blend,scale=1.):
    original_index=int(rows[cut,2]);tail=reference[original_index:].copy()
    actual=rows[cut,3:25].astype(np.float32)
    u=np.minimum(np.arange(len(tail),dtype=np.float32)/float(blend),1.)
    weight=1.-u*u*(3.-2.*u)
    for part in (slice(9,12),slice(16,19),slice(19,22)):
        tail[:,part]+=scale*weight[:,None]*(actual[part]-tail[0,part])
    prefix=rows[:cut,3:28].astype(np.float32)
    return extend_terminal(np.concatenate((prefix,tail))),original_index


def verify_prefix(model,m,rows,cut):
    with VectorPhysics(1,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',
            library=NATIVE/'libtm2020_speed.so',map_path=m['map'],horizon=cut+1,internal_controls=True) as env,Hybrid(model,1) as tracker:
        env.reset(0,36139877)
        for t in range(cut):
            actual=np.asarray(env.states[0].rigid_words,dtype=np.uint32)
            expected=rows[t,3:25].astype(np.float32).view(np.uint32)
            if not np.array_equal(actual,expected):raise RuntimeError(f'Prefix physics diverged at {t*10} ms')
            controls=tracker.act(env);env.step(controls)


def evaluate_cases(ev,g,cases):
    result=[]
    for start in range(0,len(cases),ev.n):
        part=cases[start:start+ev.n]
        if len(part)!=ev.n:raise ValueError('Qualification cases must fill the batch')
        rows,_=ev.evaluate(g,part);result.extend(rows)
    return result


def repair(index,diagnoses,output,campaign):
    source=diagnoses/f'{index:02d}';diag=json.loads((source/'diagnosis.json').read_text());m=dict(diag['map'])
    m.update(targetRank=10,targetMs=m['top10TargetMs'],targetExclusive=False)
    ref,g,net=load_asset(diag['model'],map_path=m['map'],uid=m['mapUid']);rows=np.load(source/'rollout.npz')['rows']
    guard=diag.get('firstControllerNeutralGuard');anchors=[]
    if guard:anchors.append(guard['ms']//10)
    speeds=np.linalg.norm(ref[:,16:19],axis=1)
    for e in diag['events']:
        if e['event']!='abrupt_speed_loss' or e['lossMps']<5:continue
        k=min(max(1,e['cursor']),len(ref)-1)
        if speeds[k-1]-speeds[k]<e['lossMps']*.3:anchors.append(e['ms']//10);break
    if not anchors:
        actual_speed=np.linalg.norm(rows[:,19:22],axis=1)
        for t in range(200,len(rows)):
            k=min(int(rows[t,2]),len(ref)-1)
            if actual_speed[t]<5 and speeds[k]>20 and rows[t,2]-rows[t-50,2]<5:
                anchors.append(t);break
    if not anchors:raise RuntimeError('No measured divergence or collision anchor')
    cuts=sorted({max(20,a-offset) for a in anchors for offset in (30,100,200) if a-offset<len(rows)-1})
    plans=[(cut,blend,scale) for cut in cuts for blend in (100,300) for scale in (-1.,0.,1.)]
    d=output/f'{index:02d}';d.mkdir(parents=True,exist_ok=True);paths=[];canonical=[]
    for i,(cut,blend,scale) in enumerate(plans):
        new_ref,k=make_reference(ref,rows,cut,blend,scale)
        if len(new_ref)>10000:raise RuntimeError('Rebased reference exceeds controller capacity')
        path=d/f'candidate-{i}.tmhyb';save_asset(path,new_ref,g,net,map_path=m['map'],uid=m['mapUid']);paths.append(path);canonical.append(k)
    count=len(paths);ev=NativeEvaluator(min(16,count),paths[0],api_path=NATIVE/'libtm2020_vector_physics.so',
        library=NATIVE/'libtm2020_speed.so',map_path=m['map'],horizon=min(10000,len(ref)+1400),internal_controls=True,fast_evaluation=True)
    try:
        cases=[dict(seed=36139877,warm=0,duration=0,kick=0.) for _ in range(ev.n)]
        trials=[];seconds=0.
        for start in range(0,count,ev.n):
            chunk=paths[start:start+ev.n];size=len(chunk);chunk+=chunk[-1:]*(ev.n-size)
            runs,elapsed=ev.evaluate(g,cases,assets=chunk);trials.extend(runs[:size]);seconds+=elapsed
    finally:ev.close()
    for i,r in enumerate(trials):
        cut,_,_=plans[i];p=r.get('maximumReferenceIndex',0)
        r['canonicalReferenceProgress']=min(len(ref)-1,canonical[i]+p-cut) if p>=cut else int(rows[min(p,len(rows)-1),2])
    ranked=sorted(range(count),key=lambda i:(trials[i]['finishMs'] is not None,trials[i]['checkpoints'],
        -(trials[i]['finishMs'] or 10**9),trials[i]['canonicalReferenceProgress']),reverse=True)
    save_json(d/'grid.json',{'plans':plans,'trials':trials,'seconds':seconds,'sourceModel':diag['model']})
    winner=ranked[0];trial=trials[winner];old=json.loads((campaign/f'{index:02d}/pursuit.json').read_text())
    previous=old['selected']['development']['trials'][0]
    baseline_cp=max(previous['checkpoints'],diag['finalCheckpoints'])
    improved=trial['finishMs'] is not None or trial['checkpoints']>baseline_cp or (
        trial['checkpoints']==baseline_cp and
        trial['canonicalReferenceProgress']>max(previous.get('maximumReferenceIndex',0),diag['maximumReferenceIndex'])+50)
    print(json.dumps({'map':index,'best':trial,'plan':plans[winner],'measuredProgressImprovement':improved}),flush=True)
    if not improved:return None
    asset=d/'best.tmhyb';asset.write_bytes(paths[winner].read_bytes());cut,_,_=plans[winner]
    verify_prefix(asset,m,rows,cut)
    new_ref,_,_=load_asset(asset,map_path=m['map'],uid=m['mapUid'])
    ev=NativeEvaluator(16,asset,api_path=NATIVE/'libtm2020_vector_physics.so',library=NATIVE/'libtm2020_speed.so',
        map_path=m['map'],horizon=min(10000,len(new_ref)+1000),internal_controls=True,fast_evaluation=True)
    try:
        cases=trial_cases(52000+index*100+1,16,len(new_ref),False)
        cases[0].update(seed=36139877);cases[1].update(warm=5,duration=2,kick=.02)
        cases[2].update(duration=2,kick=-.02);cases[3].update(warm=15,duration=2,kick=-.02)
        runs=evaluate_cases(ev,g,cases)
        result={'map':m,'model':str(asset),'modelSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
            'development':summary(runs[:4],m['targetMs']),'generation':0,'stopReason':'feasible_prefix_rebase',
            'assisted':True,'gameVerified':False,'verifiedPrefixTicks':cut,'stateCorrections':False,
            'prefixPhysicsBitExact':True,'sourceModel':diag['model'],'rebasePlan':plans[winner],
            'canonicalReferenceProgress':trial['canonicalReferenceProgress']}
        for name,perturbed in (('nominal64',False),('perturbed64',True)):
            cases=trial_cases(67500+index+int(perturbed),64,len(new_ref),perturbed)
            runs=evaluate_cases(ev,g,cases);q=summary(runs,m['targetMs']);save_json(d/f'{name}.json',q)
            q.update(internalPhysicalControls=True,launchRandomization=False)
            if not perturbed:q['effectiveDistinctNominalConditions']=1
            result[name]={k:v for k,v in q.items() if k!='trials'}
        result['simGoalPassed']=result['nominal64']['targetFinishes']==64;save_json(d/'result.json',result)
        print(json.dumps({'map':index,'nominal64':result['nominal64'],'prefixBitExactTicks':cut}),flush=True)
        return result
    finally:ev.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--maps',type=int,nargs='+',required=True)
    p.add_argument('--diagnoses',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--campaign',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    a=p.parse_args()
    for index in a.maps:repair(index,a.diagnoses.resolve(),a.output.resolve(),a.campaign.resolve())


if __name__=='__main__':main()
