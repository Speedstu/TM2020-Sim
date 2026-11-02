#!/usr/bin/env python3
"""Compare a real native PPO update to CUDA, including Adam and native RNG state."""
import argparse
import csv
import json
from pathlib import Path
import time
import numpy as np
import torch
from gpu_ppo import Helpers,Checkpoint,Optimizer


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--implementation',choices=['eager','graph'],default='eager')
    a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    a.output.mkdir(parents=True);helper=Helpers()
    initial=a.run/'initial.checkpoint';expected=Checkpoint.load(a.run/'update-0/training.checkpoint',helper)
    original=Checkpoint.load(initial,helper)
    # Native collection advances sampler RNG; optimization must preserve it.
    original.sampler=expected.sampler;fixture=a.output/'optimizer-input.checkpoint';original.save(fixture,helper)
    loaded=Checkpoint.load(fixture,helper)
    assert np.array_equal(loaded.parameters,original.parameters) and loaded.shuffle==original.shuffle
    if a.implementation=='graph':
        from gpu_ppo_graph import GraphOptimizer
        optimizer=GraphOptimizer('cuda')
    else:optimizer=Optimizer('cuda')
    rollout=a.run/'update-0/rollout.bin'
    if not rollout.exists():rollout=a.run/'update-0/rollout.csv'
    times=[];metrics={};parameter_error=0.
    for repeat in range(3):
        cp=Checkpoint.load(fixture,helper);metrics=optimizer.update(cp,rollout,16,helper)
        times.append(metrics['optimizerSeconds'])
        parameter_error=float(np.max(np.abs(cp.parameters-expected.parameters)))
        first_error=float(np.max(np.abs(cp.first-expected.first)));second_error=float(np.max(np.abs(cp.second-expected.second)))
        assert parameter_error<1e-7,(parameter_error,'parameters differ from native PPO')
        assert first_error<1e-7 and second_error<1e-8,(first_error,second_error,'Adam differs')
        assert cp.step==expected.step and cp.shuffle==expected.shuffle and cp.sampler==expected.sampler
        if repeat==0:
            cp.save(a.output/'cuda-updated.checkpoint',helper);cp.export_policy(a.output/'cuda-updated.tmppo',helper)
        print('CUDA_REFERENCE_MATCH',repeat,metrics,flush=True)
    cpu=Checkpoint.load(fixture,helper);cpu_time=Optimizer('cpu').update(cpu,rollout,16,helper)['optimizerSeconds']
    rows=list(csv.DictReader((a.run/'updates.csv').open()));native_time=float(rows[0]['train_seconds'])
    report={'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),
            'device':'cuda','dtype':'float64','implementation':a.implementation,'nativeSeconds':native_time,'cudaSeconds':times,
            'cudaSteadyMeanSeconds':sum(times[1:])/2,'torchCpuSeconds':cpu_time,
            'nativeVsCudaOptimizationSpeedup':native_time/(sum(times[1:])/2),
            'nativeParameterMaxError':parameter_error,'nativeAdamFirstMaxError':first_error,'nativeAdamSecondMaxError':second_error,
            'nativeAdamStepMatches':True,'nativeShuffleRngMatches':True,'nativeSamplerRngPreserved':True,
            'behaviorLogProbabilityMaxError':metrics['behaviorLogpMaxError'],'behaviorValueMaxError':metrics['behaviorValueMaxError']}
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
