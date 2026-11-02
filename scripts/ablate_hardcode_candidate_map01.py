#!/usr/bin/env python3
"""Matched-seed causal action-governor ablations for a map candidate."""
import argparse
import json
import struct
from pathlib import Path

import numpy as np

from hybrid_tracking import load_asset, save_asset
from prepare_fall_campaign import ROOT, save_json
from train_hardcode_recorded_inputs import (NativeEvaluator, NATIVE, PHYSICS,
    benchmark_cases, human_action_constraints)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--map',type=int,default=1)
    ap.add_argument('--candidate',type=Path,default=None)
    ap.add_argument('--output', type=Path, default=None)
    ap.add_argument('--cases', type=int, default=8)
    args = ap.parse_args()
    idx=args.map
    if args.output is None:args.output=ROOT/f'local/training/hardcode-inputs-0.72/{idx:02d}/bot-ablation.json'
    out=args.output.parent;out.mkdir(parents=True,exist_ok=True)
    meta=json.loads((ROOT/f'local/training/fall-campaign-0.52/{idx:02d}/map.json').read_text())
    board=json.loads((ROOT/f'local/training/fall-campaign-0.52/{idx:02d}/leaderboard.json').read_text())
    top10_target=int(next(x['time'] for x in board['tops'] if int(x['position'])==10))
    current=args.candidate or ROOT/f'local/training/hardcode-inputs-0.72/{idx:02d}/search-incumbent.tmhyb'
    historical=ROOT/f'local/training/hardcode-inputs-0.71/{idx:02d}/historical-champion.tmhyb'
    current_ref,gains,network=load_asset(current,map_path=meta['map'],uid=meta['mapUid'])
    hist_ref,_,_=load_asset(historical,map_path=meta['map'],uid=meta['mapUid'])
    raw=Path(current).read_bytes();version=struct.unpack_from('<I',raw,8)[0]
    nu,ns=struct.unpack_from('<II',raw,24);feedback=np.array([0.,0.,10.])
    if version in (3,5,6,7):
        off=32+nu+ns+(6+449)*8;feedback=np.frombuffer(raw,dtype='<f8',count=3,offset=off).copy()
    limits=human_action_constraints(idx)
    # A true permissive control must relax both the rolling window and all
    # route-local budgets. Keeping the contextual tail here made the previous
    # "permissive" arm a second constrained governor and confounded causality.
    unconstrained=np.r_[np.array([254,100,100,100,10,100,10,10,127],dtype=float),
                        np.full(20,10000,dtype=float)]
    variants={}
    def asset(name,reference,lim,format=7):
        p=out/f'ablation-{name}.tmhyb'
        save_asset(p,reference,gains,network,map_path=meta['map'],uid=meta['mapUid'],version=format,
                   feedback_filter=feedback,human_constraints=lim if format in (5,6,7) else None)
        variants[name]=p
    asset('incumbent-hard',current_ref,limits)
    for name,indices in {'pedals':[5,6,7],'step-and-amplitude':[0,8],
                         'steer-change-budget':[1],'rapid-reversal-budget':[2,3],
                         'hold-duration':[4,6,7],'context-budgets':list(range(9,29))}.items():
        lim=limits.copy()
        for i in indices:lim[i]=10000 if i>=9 else unconstrained[i]
        asset(name,current_ref,lim)
    for segment in range(5):
        lim=limits.copy();lim[9+segment*4:13+segment*4]=10000
        asset(f'context-segment-{segment}',current_ref,lim)
    for offset,name in enumerate(('steer-count','reversals','small-reversals','pedal-transitions')):
        lim=limits.copy();lim[9+3*4+offset]=10000
        asset(f'context-segment-3-{name}',current_ref,lim)
    for offset,name in enumerate(('steer-count','reversals','small-reversals','pedal-transitions')):
        lim=limits.copy();lim[9+offset:29:4]=10000
        asset(f'context-{name}',current_ref,lim)
    asset('incumbent-permissive',current_ref,unconstrained)
    asset('historical-ref-hard',hist_ref,limits)
    asset('historical-ref-permissive',hist_ref,unconstrained)
    v3=out/'ablation-incumbent-v3-format.tmhyb'
    save_asset(v3,current_ref,gains,network,map_path=meta['map'],uid=meta['mapUid'],
               version=3,feedback_filter=feedback)
    variants['same-reference-v3-format']=v3
    cases=benchmark_cases(idx,len(current_ref));families={k:v[:args.cases] for k,v in cases.items()}
    evaluator=NativeEvaluator(args.cases,current,api_path=NATIVE/'libtm2020_vector_physics.so',
        library=PHYSICS,map_path=meta['map'],horizon=len(current_ref)+600,fast_evaluation=True)
    result={}
    try:
        for name,p in variants.items():
            result[name]={}
            for family,trials in families.items():
                rows,elapsed=evaluator.evaluate(gains,trials,assets=[p]*args.cases)
                result[name][family]={'finishes':sum(r['finishMs'] is not None for r in rows),
                    'Top10':sum(r['finishMs'] is not None and r['finishMs']<=top10_target for r in rows),
                    'finishMs':[r['finishMs'] for r in rows],
                    'checkpoints':[r['checkpoints'] for r in rows],
                    'maximumReferenceIndex':[r.get('maximumReferenceIndex') for r in rows],
                    'elapsedSimulatorSeconds':elapsed}
    finally:evaluator.close()
    report={'map':idx,'casesPerArm':args.cases,'sameSeeds':True,'normalAndPerturbed':True,'actionEnvelopeVersion':7,
        'top10TargetMs':top10_target,'actionConstraints':limits.tolist(),'candidateSha256':__import__('hashlib').sha256(Path(current).read_bytes()).hexdigest(),
        'historicalReferenceSha256':__import__('hashlib').sha256(Path(historical).read_bytes()).hexdigest(),
        'results':result,'championModified':False,'clientGameAccessed':False}
    save_json(args.output,report)
    print(json.dumps({n:{k:{'finishes':v['finishes'],'Top10':v['Top10'],'cps':v['checkpoints']}
                      for k,v in arms.items()} for n,arms in result.items()},indent=2))
    print(f'report: {args.output}')


if __name__=='__main__':main()
