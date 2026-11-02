#!/usr/bin/env python3
"""Local continuous black-box hybrid optimization. Never launches/posts to game."""
import argparse
import fcntl
import hashlib
import json
import os
import signal
import time
from pathlib import Path
import numpy as np
from compare_hybrid_ppo import save_json
from finish_evidence import verified_goal
from hybrid_tracking import reference_asset,save_asset,cases
from tune_hybrid_line import displaced
from tune_hybrid_tracking import NativeEvaluator
from run_fast_ppo import ROOT

STOP=False
def stop(*_):
    global STOP
    STOP=True


def summarize(rows):
    t=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    return {'finishes':len(t),'count':len(rows),'penalizedMeanMs':float(np.mean([r['finishMs'] or 40000 for r in rows])),
            'meanMs':float(np.mean(t)) if t else None,'medianMs':float(np.median(t)) if t else None,
            'bestMs':min(t) if t else None,'worstMs':max(t) if t else None,'trials':rows,
            'referenceAssisted':True,'measuredInGame':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--initial',type=Path,required=True);p.add_argument('--generations',type=int,default=0)
    p.add_argument('--seed',type=int,default=105301);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True);lock=(a.output/'RUN.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    ref=reference_asset();initial=json.loads(a.initial.read_text())
    # Jointly learn five smooth lateral offsets and four feedback gains.
    mean=np.array(initial['offsets']+initial['gains'][:4],dtype=np.float64)
    phase_bias=initial['gains'][4];spread=np.array([.04,.04,.05,.08,.08,.005,.005,.1,.05])
    rng=np.random.default_rng(a.seed);generation=0;stale=0;phase=0;best=None
    resume=a.output/'search-state.json'
    if resume.exists():
        s=json.loads(resume.read_text());mean=np.array(s['mean']);spread=np.array(s['spread']);generation=s['generation'];stale=s['stale'];phase=s['phase'];best=s['best'];rng.bit_generator.state=s['rng']
    dev=cases(a.seed+1,16,True)
    # Persist/declare these as development data, never fresh holdout proof.
    save_json(a.output/'development-cases.json',dev)
    base=a.output/'initial.tmhyb';save_asset(base,displaced(ref,mean[:5]),[*mean[5:],phase_bias,0.])
    native_api=Path(os.environ.get('TM2020_HYBRID_API',ROOT/'native/build-hybrid2/libtm2020_vector_physics.so'))
    evaluator=NativeEvaluator(64,base,api_path=native_api)
    protocol={'version':1,'seed':a.seed,'population':4,'developmentRaces':16,'maxGenerations':a.generations,
        'initialSha256':hashlib.sha256(a.initial.read_bytes()).hexdigest(),
        'reference':'public WR geometric state+commands; explicit assisted controller',
        'optimization':'joint smooth lateral offsets + four physical feedback gains; exact native full races',
        'stageBudget':'24 generations without improvement then broaden search around retained best',
        'algorithm':'cross-entropy population search; separate bounded PPO residual experiments',
        'learnerSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'nativeApiSha256':hashlib.sha256(native_api.read_bytes()).hexdigest(),
        'goalStop':'verified-game.json with fresh board/native zero-respawn replay and exact model evidence',
        'autoGameLaunch':False,'onlineSubmission':False,'hourlyMonitor':False}
    pp=a.output/'protocol.json'
    if pp.exists() and json.loads(pp.read_text())!=protocol:raise RuntimeError('Frozen search protocol changed')
    save_json(pp,protocol);started=time.monotonic()
    try:
        while not STOP and not (a.output/'STOP').exists() and (not a.generations or generation<a.generations):
            if verified_goal(a.output):save_json(a.output/'goal.json',{'realGameVerified':True});break
            population=np.clip(mean+rng.normal(size=(4,9))*spread,
                               [-1.5]*5+[-.5,-.5,-4.,-2.],[1.5]*5+[.5,.5,4.,2.])
            population[0]=mean if best is None else best['parameters']
            assets=[]
            for i,parameters in enumerate(population):
                asset=a.output/f'candidate-{i}.tmhyb'
                save_asset(asset,displaced(ref,parameters[:5]),[*parameters[5:],phase_bias,0.]);assets.extend([asset]*16)
            rows,seconds=evaluator.evaluate(np.repeat(np.c_[population[:,5:],np.full(4,phase_bias),np.zeros(4)],16,axis=0),dev*4,assets=assets)
            ranking=[];improved=False
            for i,parameters in enumerate(population):
                result=summarize(rows[i*16:(i+1)*16]);score=(result['finishes'],-result['penalizedMeanMs'])
                ranking.append((score,i))
                if best is None or score>tuple(best['score']):
                    best={'generation':generation+1,'parameters':parameters.tolist(),'score':score,'result':result};stale=0;improved=True
                    save_asset(a.output/'best.tmhyb',displaced(ref,parameters[:5]),[*parameters[5:],phase_bias,0.])
                    save_json(a.output/'best-score.json',best)
            generation+=1
            if not improved:stale+=1
            ranking.sort(reverse=True);elite=population[[i for _,i in ranking[:2]]];mean=elite.mean(0)
            spread=np.maximum(elite.std(0),[.01,.01,.015,.02,.02,.001,.001,.025,.01])
            if stale>=24:
                phase+=1;stale=0;mean=np.array(best['parameters'])
                spread=np.array([.08,.08,.12,.15,.15,.015,.02,.25,.15])*min(2.,1.+phase*.1)
            save_json(resume,{'generation':generation,'stale':stale,'phase':phase,'best':best,
                      'mean':mean.tolist(),'spread':spread.tolist(),'rng':rng.bit_generator.state})
            status={'state':'optimizing','generation':generation,'phase':phase,'stale':stale,
                'best':best,'physicalRacesGenerated':generation*64,'lastGenerationSeconds':seconds,
                'wallSeconds':time.monotonic()-started,'referenceAssisted':True,'realGameVerified':False,
                'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
            save_json(a.output/'status.json',status)
            if generation%4==0:print(json.dumps({k:v for k,v in status.items() if k!='best'}),flush=True)
            if generation%16==0:
                # Diagnostic suite rotates and is recorded; never use this as
                # an unseen-map or final game qualification claim.
                evaluator.asset=a.output/'best.tmhyb';params=np.array(best['parameters']);g=[*params[5:],phase_bias,0.]
                runs,elapsed=evaluator.evaluate(g,cases(a.seed+100+generation,64,True))
                save_json(a.output/f'diagnostic-{generation}.json',summarize(runs))
        goal=(a.output/'goal.json').exists()
        save_json(a.output/'stop.json',{'generation':generation,'reason':'goal' if goal else 'STOP/signal/budget','realGameVerified':goal})
        status_path=a.output/'status.json'
        final_status=json.loads(status_path.read_text()) if status_path.exists() else {'generation':generation}
        final_status.update({'state':'goal_verified' if goal else 'stopped','realGameVerified':goal})
        save_json(status_path,final_status)
    finally:evaluator.close();lock.close()


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
