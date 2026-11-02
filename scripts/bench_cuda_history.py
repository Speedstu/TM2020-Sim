#!/usr/bin/env python3
"""One PPO update CUDA-resident history versus original host-staged history."""
import os
import time
import numpy as np
import torch
from compare_hybrid_ppo import Policy, Episodes, update
from cuda_history import CudaHistoryEpisodes
from gpu_ppo import Helpers,Checkpoint
from run_fast_ppo import ROOT

def test(impl):
    prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',Helpers())
    policy=Policy(prior,'discrete33')
    policy.load_state_dict(torch.load(ROOT/'local/recon/internal-0.46/ppo-comparison/46602-discrete33/best.pt',weights_only=True,map_location='cpu'))
    optim=torch.optim.Adam([{'params':policy.actor.parameters(),'lr':3e-7},
                           {'params':policy.critic.parameters(),'lr':3e-5},
                           {'params':[policy.logstd],'lr':3e-7}],eps=1e-8)
    env=impl(16,73302)
    torch.manual_seed(19999)
    try:
        torch.cuda.synchronize()
        a=time.perf_counter()
        metric=update(policy,env,optim,512)
        torch.cuda.synchronize()
        elapsed=time.perf_counter()-a
        values=np.concatenate([p.detach().cpu().numpy().ravel() for p in policy.parameters()])
        return {'impl':impl.__name__,'seconds':round(elapsed,3),
                'sps':round(8192/elapsed),'kl':metric['kl'],
                'params':values,'minibatches':metric['minibatches']}
    finally:env.env.close()
def main():
    os.environ['TM2020_PHYSICS_WORKERS']='8'
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    results=[test(x) for x in (Episodes,CudaHistoryEpisodes)]
    for r in results:
        print({k:v for k,v in r.items() if k!='params'},flush=True)
    diff=np.max(np.abs(results[0]['params']-results[1]['params']))
    print('CUDA parameter parity max absolute difference',float(diff),flush=True)
    assert diff < 1e-10
if __name__=='__main__':main()
