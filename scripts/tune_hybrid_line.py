#!/usr/bin/env python3
"""Optimize small lateral line offsets using complete assisted native laps."""
import argparse
import json
from pathlib import Path
import numpy as np
from compare_hybrid_ppo import save_json
from hybrid_tracking import DIR,reference_asset,save_asset,cases
from tune_hybrid_tracking import NativeEvaluator
from run_fast_ppo import ROOT


def displaced(reference,parameters):
    result=reference.copy();time=np.arange(len(reference))
    centers=[650,1050,1450,1650,1800];widths=[100,100,100,80,70]
    offset=sum(p*np.exp(-.5*((time-c)/w)**2) for p,c,w in zip(parameters,centers,widths))
    result[:,9:12]+=offset[:,None]*reference[:,[0,3,6]]
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--generations',type=int,default=48)
    p.add_argument('--output',type=Path,default=DIR/'line-search')
    p.add_argument('--initial',type=Path);p.add_argument('--robust',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    ref=reference_asset();gains=json.loads((DIR/'diverse-candidate-gains.json').read_text())['gains']
    qualification=json.loads((DIR/'diverse-nominal64.json').read_text())
    failed=[r['seed'] for r in qualification['trials'] if r['finishMs'] is None]
    succeeded=[r['seed'] for r in qualification['trials'] if r['finishMs'] is not None]
    seeds=failed[:2]+succeeded[1:3]
    dev=[{'seed':s,'warm':0,'duration':0,'kick':0.} for s in seeds]
    if a.robust:
        previous=json.loads((DIR/'line-nominal64.json').read_text())
        hard=[r['seed'] for r in previous['trials'] if r['finishMs'] is None]
        dev=[{'seed':s,'warm':0,'duration':0,'kick':0.} for s in hard]
        dev+=cases(105261,16-len(dev),True)
    save_json(a.output/'development-cases.json',dev)
    base=a.output/'base.tmhyb';save_asset(base,ref,gains)
    evaluator=NativeEvaluator(64,base,api_path=ROOT/'native/build-hybrid2/libtm2020_vector_physics.so')
    mean=np.zeros(5);spread=np.array([.1,.1,.2,.4,.3]);rng=np.random.default_rng(105221);best=None
    if a.initial:mean=np.asarray(json.loads(a.initial.read_text())['offsets'])
    group=len(dev);population_size=64//group;assert population_size*group==64
    try:
        for gen in range(a.generations):
            population=mean+rng.normal(size=(population_size,5))*spread;population=np.clip(population,-1.5,1.5)
            population[0]=mean if best is None else best['offsets']
            if gen==0 and not a.initial:population[0]=0
            assets=[]
            for i,parameters in enumerate(population):
                asset=a.output/f'candidate-{i}.tmhyb';save_asset(asset,displaced(ref,parameters),gains);assets.extend([asset]*group)
            rows,seconds=evaluator.evaluate(gains,dev*population_size,assets=assets)
            ranked=[]
            for i,parameters in enumerate(population):
                trials=rows[i*group:(i+1)*group];finishes=sum(t['finishMs'] is not None for t in trials)
                cost=float(np.mean([t['finishMs'] or 40000 for t in trials]));score=(finishes,-cost)
                record={'generation':gen,'offsets':parameters.tolist(),'gains':gains,'finishes':finishes,'penalizedMeanMs':cost,'score':score,'trials':trials}
                ranked.append((score,i))
                if best is None or tuple(best['score'])<score:
                    best=record;save_json(a.output/'best.json',best);save_asset(a.output/'best.tmhyb',displaced(ref,parameters),gains)
            ranked.sort(reverse=True);elite=population[[i for _,i in ranked[:max(2,population_size//4)]]]
            mean=elite.mean(0);spread=np.maximum(elite.std(0),.015)
            print(json.dumps({'generation':gen,'seconds':seconds,'best':best}),flush=True)
            save_json(a.output/'status.json',{'generation':gen,'best':best})
        evaluator.asset=a.output/'best.tmhyb'
        final_seed=105271 if a.robust else 105231
        for name,trial_cases in [('nominal',cases(final_seed,64,False)),('perturbed',cases(final_seed+1,64,True))]:
            rows,seconds=evaluator.evaluate(gains,trial_cases);t=[r['finishMs'] for r in rows if r['finishMs']]
            report={'finishes':len(t),'count':64,'meanMs':float(np.mean(t)) if t else None,'bestMs':min(t) if t else None,'worstMs':max(t) if t else None,'trials':rows,'referenceAssisted':True,'realGameVerified':False}
            save_json(a.output/(name+'64.json'),report);print(json.dumps({k:v for k,v in report.items() if k!='trials'}),flush=True)
    finally:evaluator.close()


if __name__=='__main__':main()
