#!/usr/bin/env python3
"""Summarize paired held-out simulator trials without claiming game results."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from run_fast_ppo import ROOT
from compare_hybrid_ppo import ARMS,save_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    report=json.loads((a.experiment/'report.json').read_text());runs=report['runs']
    if len(runs)!=len(report['protocol']['seeds']):raise RuntimeError('Experiment is incomplete')
    summary={'seeds':[],'arms':{},'pairedVsContinuous':{},'measuredInGame':False,'gameFinishVerified':False,
             'limits':['One map and one common pretrained encoder; results do not establish unseen-map strength.',
                       'Three training seeds, 41 shared held-out cases per seed; repeated cases are not 123 independent maps.',
                       'Early steering disturbances perturb departures; initial pose is not randomized.',
                       'Best checkpoints use development trials only. Warm-start and action-head parameterization affect results.',
                       'Equal policy-transition budgets within each seed; early physics termination can change actual tick counts.']}
    arrays={};candidates=[]
    for run in runs:
        budgets={arm:run['transitionsPerArm'] for arm in ARMS};selected={}
        for arm in ARMS:
            evaluations=[e for e in run['evaluations'] if e['arm']==arm];best=evaluations[0]
            for e in evaluations[1:]:
                if e['finishes']>best['finishes'] or (e['finishes']==best['finishes'] and e['meanWithDnf40sMs']<best['meanWithDnf40sMs']-50):best=e
            selected[arm]={'update':best['update'],'developmentFinishes':best['finishes'],'developmentMeanWithDnf40sMs':best['meanWithDnf40sMs']}
            candidates.append((best['finishes'],-best['meanWithDnf40sMs'],run['seed'],arm,best['update']))
        summary['seeds'].append({'seed':run['seed'],'matchedTransitionsPerArm':budgets,'updates':run['updates'],'stopReason':run['stopReason'],'selected':selected})
    for arm in ARMS:
        matrix=np.array([[float(t['finishMs']) if t['finishMs'] is not None else np.nan for t in run['holdout'][arm]['trials']] for run in runs])
        arrays[arm]=matrix;finite=matrix[np.isfinite(matrix)];penalized=np.nan_to_num(matrix,nan=40000.)
        summary['arms'][arm]={'finishes':int(len(finite)),'trials':int(matrix.size),'finishRate':float(len(finite)/matrix.size),
                              'meanMs':float(finite.mean()),'medianMs':float(np.median(finite)),'bestMs':float(finite.min()),
                              'meanWithDnf40sMs':float(penalized.mean()),'meanNominalMs':float(np.nanmean(matrix[:,0]))}
    rng=np.random.default_rng(46900);seeds,cases=arrays['continuous'].shape
    for arm in ARMS[1:]:
        finish_delta=np.isfinite(arrays[arm]).astype(float)-np.isfinite(arrays['continuous']).astype(float)
        time_delta=np.nan_to_num(arrays[arm],nan=40000.)-np.nan_to_num(arrays['continuous'],nan=40000.)
        boot=[]
        for _ in range(10000):
            s=rng.integers(0,seeds,seeds);c=rng.integers(0,cases,cases)
            boot.append((finish_delta[np.ix_(s,c)].mean(),time_delta[np.ix_(s,c)].mean()))
        ci=np.quantile(boot,[.025,.975],axis=0)
        summary['pairedVsContinuous'][arm]={'finishRateDelta':float(finish_delta.mean()),'finishRateDelta95ci':ci[:,0].tolist(),
                                            'meanWithDnf40sDeltaMs':float(time_delta.mean()),'timeDelta95ciMs':ci[:,1].tolist(),
                                            'bootstrap':'paired hierarchical resampling of 3 seeds and 41 cases, 10000 draws'}
    # This choice sees development scores only, never holdout outcomes.
    _,_,seed,arm,update=max(candidates);source=a.experiment/f'{seed}-{arm}/best.tmppo'
    deployment=ROOT/'local/recon/deployment-0.46';shutil.copy2(source,deployment/'candidate.tmppo')
    summary['candidate']={'source':str(source),'seed':seed,'distribution':arm,'selectedUpdate':update,
                          'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'selection':'best development finish count then penalized mean',
                          'readyForQualifiedOfflineTrial':True,'gameFinishVerified':False}
    save_json(deployment/'candidate.json',summary['candidate']);save_json(a.experiment/'summary.json',summary)
    lines=['# Matched hybrid PPO experiment 0.46','',
           'Simulator only: Fall 2026-01. Three seeds, 41 held-out departure cases per seed (40 perturbed, one nominal).',
           'Same map, pure time reward, encoder prior, seed schedule, transition budget and PPO settings within each seed.','',
           '| Policy | Finishes | Mean (s) | Median (s) | Best (s) | Mean with DNF = 40 s |',
           '|---|---:|---:|---:|---:|---:|']
    for arm,r in summary['arms'].items():lines.append(f"| {arm} | {r['finishes']}/{r['trials']} | {r['meanMs']/1000:.3f} | {r['medianMs']/1000:.3f} | {r['bestMs']/1000:.3f} | {r['meanWithDnf40sMs']/1000:.3f} |")
    lines+=['','Means/medians/bests use successful finishes. The last column includes every trial.','',
            'Budgets and selected development checkpoints:','']
    for run in summary['seeds']:lines.append(f"- Seed {run['seed']}: {run['updates']} updates, {next(iter(run['matchedTransitionsPerArm'].values())):,} transitions per arm; {run['stopReason']}. Selected updates: "+', '.join(f"{arm}={v['update']}" for arm,v in run['selected'].items())+'.')
    lines+=['','Limits:','']+['- '+s for s in summary['limits']]
    lines+=['','No verified arrival in the actual client is included. See summary.json for paired uncertainty intervals and candidate provenance.','']
    (a.experiment/'summary.md').write_text('\n'.join(lines));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
