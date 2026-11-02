#!/usr/bin/env python3
"""Test a physics-reconstructed human route anchor with live hardcode feedback."""
import argparse, json, struct
from pathlib import Path
import numpy as np
from diagnose_human_01_feasibility import read_human_inputs
from hybrid_tracking import load_asset, save_asset
from prepare_fall_campaign import ROOT, save_json
from train_hardcode_recorded_inputs import NativeEvaluator, benchmark_cases, human_action_constraints, NATIVE, PHYSICS
from vector_physics import VectorPhysics


def build_reference(index, rank, meta, controls):
    ref=np.zeros((len(controls),25),dtype=np.float32)
    with VectorPhysics(1,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',
                       library=PHYSICS,map_path=meta['map'],horizon=len(controls)+700,
                       normal_inputs=True) as env:
        env.reset(0,36139877 if index==1 else int(json.loads((ROOT/f'local/training/human-rework-0.70/corpus/{index:02d}/leaderboard-rank{rank}/analysis.json').read_text())['validationSeed']))
        for t,command in enumerate(controls):
            state=env.states[0]
            rigid=np.asarray(list(state.rigid_words),dtype=np.uint32).view(np.float32)
            ref[t,:22]=rigid[:22]
            ref[t,22:25]=command
            if state.terminated or state.truncated:
                ref[t+1:,:22]=rigid[:22]
                ref[t+1:,22:25]=controls[t+1:]
                break
            env.step(command[None,:])
    return ref


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--map',type=int,default=3)
    ap.add_argument('--rank',type=int,default=1);ap.add_argument('--cases',type=int,default=8)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();idx=args.map
    meta,analysis,timeline,decoded,controls=read_human_inputs(idx,args.rank)
    info=json.loads((ROOT/f'local/training/fall-campaign-0.52/{idx:02d}/map.json').read_text())
    folder=ROOT/f'local/training/hardcode-inputs-0.72/{idx:02d}';source=folder/'search-incumbent.tmhyb'
    _,current_g,current_net=load_asset(source,map_path=info['map'],uid=info['mapUid'])
    raw=Path(source).read_bytes();_,_,_,_,nu,ns=struct.unpack_from('<6I',raw,8)
    feedback=np.array([0.,0.,10.]);version=struct.unpack_from('<I',raw,8)[0]
    if version in (3,5,6,7):feedback=np.frombuffer(raw,dtype='<f8',count=3,offset=32+nu+ns+(6+449)*8).copy()
    ref=build_reference(idx,args.rank,meta,controls)
    constraints=human_action_constraints(idx);cases=benchmark_cases(idx,len(controls))
    variants={}
    variants['existing-controller']=(source,current_g.copy())
    for name,scale,filter_values in (
        ('zero',0.,np.array([0.,0.,10.])),('half',.5,feedback),('current',1.,feedback),('double',2.,feedback)):
        gains=current_g.copy();gains[:4]*=scale;gains[5]=0.
        asset=folder/f'human-anchor-{name}.tmhyb'
        save_asset(asset,ref,gains,np.zeros(449),map_path=info['map'],uid=info['mapUid'],version=7,
                   feedback_filter=filter_values,human_constraints=constraints)
        gains_to_test=current_g.copy();gains_to_test[:4]*=scale;gains_to_test[5]=0.
        if scale==0.:gains_to_test[:4]=0.
        variants[name]=(asset,gains_to_test)
    evaluator=NativeEvaluator(8,next(iter(variants.values())),api_path=NATIVE/'libtm2020_vector_physics.so',
        library=PHYSICS,map_path=info['map'],horizon=len(controls)+600,fast_evaluation=True)
    results={}
    try:
        for name,(asset,gains_to_test) in variants.items():
            results[name]={}
            for family in ('normal64','perturbed64'):
                batch=cases[family][:args.cases]
                rows,elapsed=evaluator.evaluate(gains_to_test,batch,assets=[asset]*len(batch))
                results[name][family]={'finishes':sum(r['finishMs'] is not None for r in rows),
                    'Top10':sum(r['finishMs'] is not None and r['finishMs']<=int(next(x['time'] for x in json.loads((ROOT/f'local/training/fall-campaign-0.52/{idx:02d}/leaderboard.json').read_text())['tops'] if int(x['position'])==10)) for r in rows),
                    'finishMs':[r['finishMs'] for r in rows],'checkpoints':[r['checkpoints'] for r in rows],
                    'elapsedSimulatorSeconds':elapsed,'inputs':[r.get('inputs') for r in rows]}
    finally:evaluator.close()
    report={'map':idx,'ghostRank':args.rank,'verifiedGhostSeed':analysis['validationSeed'],
        'anchorBuiltByReplayingExactRawGhostThroughSamePhysics':True,'actionsOptimizedAfterAnchor':True,
        'feedbackScales':['zero','half','current','double'],'constraints':constraints.tolist(),
        'casesPerArm':args.cases,'sameSeeds':True,'results':results,'sourceChampionModified':False}
    save_json(args.output,report)
    print(json.dumps({n:{f:{k:v[k] for k in ('finishes','Top10','finishMs','checkpoints')} for f,v in fs.items()} for n,fs in results.items()},indent=2))
    print(f'report: {args.output}')

if __name__=='__main__':main()
