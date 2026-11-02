#!/usr/bin/env python3
"""Audit the executed hardcode commands, normal-history acknowledgement and human rhythm.

Local simulator evidence only. Stored feedforward similarity is diagnostic and
does not substitute for comparison of the commands actually emitted by feedback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np
from hybrid_tracking import Hybrid, load_asset
from vector_physics import VectorPhysics
from tune_hybrid_tracking import NativeEvaluator
from train_hardcode_recorded_inputs import benchmark_cases, summarize, PHYSICS
from compare_human_sim_inputs import summarize_human_cohort, summarize_rows, human_style_proxy

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--map',type=int,required=True)
    p.add_argument('--asset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    native=Path(os.environ.get('TM2020_HARDCODE_NATIVE',ROOT/'native/build-hardcode-0.72'))
    meta=json.loads((ROOT/f'local/training/fall-campaign-0.52/{a.map:02d}/map.json').read_text())
    ref,g,_=load_asset(a.asset,map_path=meta['map'],uid=meta['mapUid'])
    case_sets=benchmark_cases(a.map,len(ref));human,_=summarize_human_cohort(a.map)
    boards=json.loads((ROOT/f'local/training/human-rework-0.70/top100-cohort/{a.map:02d}/leaderboard-top100.json').read_text())
    targets={r:int(next(v['time'] for v in boards['tops'] if v['position']==r)) for r in (10,100)}
    results={};ev=NativeEvaluator(16,a.asset,api_path=native/'libtm2020_vector_physics.so',
        map_path=meta['map'],library=PHYSICS,horizon=len(ref)+600,fast_evaluation=True)
    try:
        for family,cases in case_sets.items():
            rows=[]
            for off in range(0,64,16):rows.extend(ev.evaluate(g,cases[off:off+16])[0])
            results[family]=summarize(rows,targets[10],targets[100])
            for rank in (100,10):
                stats=summarize_rows(rows,targets[rank],label=f'top{rank}')
                results[family][f'humanTop{rank}']=human_style_proxy(stats,human)
                results[family][f'inputSummaryTop{rank}']=stats
                eligible=[r for r in rows if r['finishMs'] is not None and r['finishMs']<=targets[rank]]
                checks=[human_style_proxy(summarize_rows([r],targets[rank],label=f'top{rank}'),human) for r in eligible]
                results[family][f'perRunHumanTop{rank}']={'qualifyingRuns':len(eligible),
                    'observedRangePasses':sum(c['passes'] for c in checks),
                    'commonStylePasses':sum(c['commonStylePasses'] for c in checks),
                    'failures':[{'seed':r['seed'],'criteria':c['failedCriteria']} for r,c in zip(eligible,checks) if not c['passes']]}
    finally:ev.close()
    # Four paired full-race traces: exact commands, simulator acknowledgement,
    # physical states and localization index. No replay data is modified.
    pairs=[case_sets[f][i] for f in ('normal64','perturbed64') for i in range(4)]
    traces=[[] for _ in pairs];ack_mismatches=0;active=np.ones(8,dtype=bool)
    with VectorPhysics(8,decision_ticks=1,api_path=native/'libtm2020_vector_physics.so',library=PHYSICS,
            map_path=meta['map'],horizon=len(ref)+600,normal_inputs=True) as env,Hybrid(a.asset,8) as driver:
        for i,c in enumerate(pairs):env.reset(i,c['seed'])
        for t in range(len(ref)+600):
            if not active.any():break
            commands=driver.act(env);applied=commands.copy()
            was_active=active.copy()
            for i,c in enumerate(pairs):
                if not active[i]:continue
                if c['warm']<=t<c['warm']+c['duration']:applied[i,2]=np.clip(applied[i,2]+c['kick'],-1,1)
                applied[i,2]=np.rint(applied[i,2]*127)/127
                traces[i].append((commands[i].copy(),applied[i].copy(),driver.cursor_index(i),
                                  np.array(env.states[i].rigid_words,dtype=np.uint32)))
            VectorPhysics.validate_recorded_actions(applied)
            env.step(applied)
            for i in range(8):
                if not was_active[i]:continue
                if not np.allclose(list(env.states[i].controls),applied[i],rtol=0,atol=1e-6):ack_mismatches+=1
                active[i]=not(env.states[i].terminated or env.states[i].truncated)
        outcomes=[{'seed':c['seed'],'finishMs':int(env.states[i].finish_ms),'ticks':len(traces[i])} for i,c in enumerate(pairs)]
    corpus=ROOT/f'local/training/human-rework-0.70/top100-cohort/{a.map:02d}'
    raw=np.load(corpus/'leaderboard-rank001/timeline.npz')['controls']
    comparisons=[];saved={}
    for i,tr in enumerate(traces):
        commands=np.array([r[0] for r in tr]);applied=np.array([r[1] for r in tr]);n=min(len(raw),len(commands))
        exact=np.all(np.rint(commands[:n]*127)==np.rint(raw[:n]*127),axis=1)
        comparisons.append({'lane':i,'ticksCompared':n,'exactAllChannelTickFractionToTop1':float(exact.mean()),
            'steerMeanAbsDifferenceToTop1':float(np.abs(commands[:n,2]-raw[:n,2]).mean()),
            'allCommandsIdenticalToTop1':bool(exact.all())})
        saved[f'commands{i}']=commands;saved[f'applied{i}']=applied
        saved[f'phase{i}']=np.array([r[2] for r in tr]);saved[f'rigid{i}']=np.array([r[3] for r in tr])
    responses=[]
    for i in range(4):
        normal=saved[f'commands{i}'];pert=saved[f'commands{i+4}'];c=pairs[i+4];lo=c['warm']+c['duration'];n=min(len(normal),len(pert))
        changes=np.flatnonzero(np.any(normal[lo:n]!=pert[lo:n],axis=1))
        responses.append({'seed':c['seed'],'kickTick':c['warm'],'changedPolicyTicksAfterKick':len(changes),
            'firstDifferentPolicyTickAfterKick':int(lo+changes[0]) if len(changes) else None})
    np.savez_compressed(a.output/'executed-traces.npz',**saved)
    report={'map':a.map,'asset':str(a.asset.resolve()),'assetSha256':hashlib.sha256(a.asset.read_bytes()).hexdigest(),
        'normalHistory':True,'inputHz':100,'quantization':'binary pedals; signed i8/127 steer',
        'acknowledgementMismatchTicks':ack_mismatches,'acknowledgementScope':'normal input interface acknowledgement; not a client replay proof',
        'pairedTraceOutcomes':outcomes,'executedSimilarityToTop1':comparisons,'physicalFeedbackResponse':responses,
        'benchmark':results,'humanCohort':human,'targetsMs':targets,'clientVerified':False,'championReplaced':False}
    (a.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'map':a.map,'ackMismatches':ack_mismatches,'response':responses,
        'benchmark':{f:{k:v[k] for k in ('finishes','top100Finishes','top10Finishes','bestMs','medianMs','humanTop100','humanTop10')} for f,v in results.items()}},indent=2),flush=True)

if __name__=='__main__':main()
