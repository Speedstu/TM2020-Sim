#!/usr/bin/env python3
"""Bake a successful simulated control perturbation into a standalone tracker.

Reference states are targets recorded from genuine full-start physics. Nothing
is written to the simulated state. The exported policy must reproduce the run
with no external perturbation before qualification is accepted.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import Hybrid,load_asset,save_asset
from vector_physics import VectorPhysics
from tune_hybrid_tracking import NativeEvaluator
from optimize_fall_campaign import trial_cases,summary
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT

NATIVE=ROOT/'local/training/campaign-speed-0.66/native'


def capture(model,m,case):
    ref,g,_=load_asset(model,map_path=m['map'],uid=m['mapUid']);rows=[]
    with VectorPhysics(1,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',
            library=NATIVE/'libtm2020_speed.so',map_path=m['map'],horizon=len(ref)+1000,internal_controls=True) as env,Hybrid(model,1) as controller:
        env.reset(0,case['seed'])
        while not env.states[0].terminated and not env.states[0].truncated:
            state=env.states[0]
            if state.reserved:break
            rigid=np.asarray(state.rigid_words,dtype=np.uint32).view(np.float32).copy()
            controls=controller.act(env)[0];tick=int(state.tick)
            if case['warm']<=tick<case['warm']+case['duration']:
                value=np.float32(np.clip(controls[2]+np.float32(case['kick']),-1.,1.))
                controls[2]=np.copysign(np.floor(abs(value)*np.float32(127)+np.float32(.5)),value)/np.float32(127)
            rows.append(np.concatenate((rigid,controls)).astype(np.float32));env.step(controls[None,:])
        finish=int(env.states[0].finish_ms)
        final=np.array(env.states[0].rigid_words,dtype=np.uint32).copy()
    if finish<0:raise RuntimeError('Distillation requires a complete, genuine simulated arrival')
    return np.asarray(rows,dtype=np.float32),g,finish,final


def distill(model,m,case,output):
    output.mkdir(parents=True,exist_ok=True);ref,g,finish,final=capture(model,m,case)
    g[5]=0.;asset=output/'best.tmhyb';save_asset(asset,ref,g,map_path=m['map'],uid=m['mapUid'])
    check=NativeEvaluator(1,asset,api_path=NATIVE/'libtm2020_vector_physics.so',library=NATIVE/'libtm2020_speed.so',
        map_path=m['map'],horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
    try:
        rows,_=check.evaluate(g,[dict(seed=case['seed'],warm=0,duration=0,kick=0.)])
        if rows[0]['finishMs']!=finish or not np.array_equal(np.array(check.env.states[0].rigid_words),final):
            raise RuntimeError('Unperturbed exported policy does not reproduce the original full-start physical result')
    finally:check.close()
    ev=NativeEvaluator(64,asset,api_path=NATIVE/'libtm2020_vector_physics.so',library=NATIVE/'libtm2020_speed.so',
        map_path=m['map'],horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
    try:
        cases=trial_cases(52000+m['index']*100+1,64,len(ref),False)
        cases[0].update(seed=case['seed']);cases[1].update(warm=5,duration=2,kick=.02)
        cases[2].update(duration=2,kick=-.02);cases[3].update(warm=15,duration=2,kick=-.02)
        rows,_=ev.evaluate(g,cases)
        result={'map':m,'model':str(asset.resolve()),'modelSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
            'development':summary(rows[:4],m['targetMs']),'generation':0,'stopReason':'feasible_rollout_distillation',
            'assisted':True,'gameVerified':False,'sourceModel':str(Path(model).resolve()),'sourceCase':case,
            'autonomousReplayFinishMs':finish,'autonomousFinalRigidBitExact':True,'referenceFrames':len(ref),
            'stateCorrections':False,'externalKickAtDeployment':False}
        for name,perturbed in (('nominal64',False),('perturbed64',True)):
            c=trial_cases(67100+m['index']+int(perturbed),64,len(ref),perturbed);rows,_=ev.evaluate(g,c)
            q=summary(rows,m['targetMs']);save_json(output/f'{name}.json',q)
            q.update(internalPhysicalControls=True,launchRandomization=False)
            if not perturbed:q['effectiveDistinctNominalConditions']=1
            result[name]={k:v for k,v in q.items() if k!='trials'}
        result['simGoalPassed']=result['nominal64']['targetFinishes']==64;save_json(output/'result.json',result)
        print(json.dumps({'map':m['index'],'finishMs':finish,'nominal64':result['nominal64'],
            'perturbed64':result['perturbed64'],'autonomousFinalRigidBitExact':True}),flush=True)
        return result
    finally:ev.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map-index',type=int,required=True)
    p.add_argument('--source',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    p.add_argument('--model',type=Path);p.add_argument('--case',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();s=json.loads((a.source/f'{a.map_index:02d}/pursuit.json').read_text());m=dict(s['goal'])
    m.update(targetRank=10,targetMs=m['top10TargetMs'],targetExclusive=False)
    distill(a.model or s['bestAsset'],m,json.loads(a.case.read_text()),a.output.resolve())


if __name__=='__main__':main()
