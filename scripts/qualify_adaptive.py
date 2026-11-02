#!/usr/bin/env python3
"""Fresh full-race qualification against the unmodified source, no training."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from compare_hybrid_ppo import Policy,save_json,quantized
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights,trial_suite,qualifies_for_trial
from preview_ppo import PreviewPolicy,physics,evaluate
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--preview',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);torch.set_num_threads(1)
    helpers=Helpers();prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',helpers)
    reference=Policy(prior,'continuous');load_weights(reference,a.source)
    candidate=PreviewPolicy(prior,a.candidate) if a.preview else Policy(prior,'continuous')
    load_weights(candidate,a.candidate)
    suite=trial_suite(a.seed,64);save_json(a.output/'cases.json',suite)
    with physics(64) as env:
        source=evaluate(reference,env,suite,preview=False)
        result=evaluate(candidate,env,suite,preview=a.preview)
    candidate.export(prior,a.output/'candidate.tmppo',helpers)
    x=np.random.default_rng(a.seed).normal(0,.3,(256,candidate.actor[0].in_features))
    width=72 if a.preview else 48
    for f in range(5):x[:,f*width+13:f*width+15]=0.
    x.astype('<f8').tofile(a.output/'observations.f64')
    import subprocess
    subprocess.run([str(ROOT/'native/build-preview/tm2020_internal_policy_probe'),str(a.output/'candidate.tmppo'),
                    str(a.output/'observations.f64'),str(a.output/'controls.f32')],check=True)
    with torch.no_grad():
        out=candidate.actor(torch.as_tensor(x,device='cuda'))
        expected=quantized(torch.cat(((out[:,:2]>=0).double(),out[:,2:3].tanh()),1).cpu().numpy())
    actual=np.fromfile(a.output/'controls.f32',dtype='<f4').reshape(-1,3)
    if not np.array_equal(actual,expected):raise RuntimeError('Export controls differ from CUDA')
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report={'source':source,'candidate':result,'qualifiedForGameTrial':qualifies_for_trial(result,source),
            'independentQualificationSeed':a.seed,'sourceWeightsSha256':digest(a.source),
            'candidateWeightsSha256':digest(a.candidate),'exportSha256':digest(a.output/'candidate.tmppo'),
            'nativeControlsBitExactToCuda':True,'realGameVerified':False}
    save_json(a.output/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('source','candidate')}))
    print(json.dumps({'sourceMean':source['meanWithDnf40sMs'],'candidateMean':result['meanWithDnf40sMs'],
                      'sourceFinishes':source['finishes'],'candidateFinishes':result['finishes']}))


if __name__=='__main__':main()
