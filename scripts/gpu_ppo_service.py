#!/usr/bin/env python3
"""Owned local file service: native rollout collector -> CUDA PPO -> SDK checkpoint."""
import argparse
import json
import os
from pathlib import Path
import time
import traceback
import torch
from gpu_ppo import Checkpoint,Helpers,Optimizer


def atomic_text(path,text):
    temporary=Path(str(path)+'.tmp')
    with temporary.open('x') as out:out.write(text);out.flush()
    temporary.rename(path)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--parent-pid',type=int)
    p.add_argument('--optimizer',choices=['eager','graph'],default='graph')
    a=p.parse_args();a.directory.mkdir(parents=True,exist_ok=True)
    if (a.directory/'ready.txt').exists():p.error('Service directory already initialized')
    helper=Helpers()
    if a.optimizer=='graph':
        from gpu_ppo_graph import GraphOptimizer
        optimizer=GraphOptimizer('cuda')
    else:optimizer=Optimizer('cuda')
    # Initialize kernels/context before advertising readiness.
    x=torch.eye(16,device='cuda',dtype=torch.float64);_=x@x;torch.cuda.synchronize()
    info={'schema':'tm2020_cuda_ppo_service_v1','pid':os.getpid(),'torch':torch.__version__,
          'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'dtype':'float64','device':'cuda','optimizerImplementation':a.optimizer}
    atomic_text(a.directory/'device.json',json.dumps(info,indent=2)+'\n')
    atomic_text(a.directory/'ready.txt','TM2020_CUDA_PPO_V1\n')
    print(json.dumps(info),flush=True)
    seq=0
    while not (a.directory/'STOP').exists():
        if a.parent_pid:
            try:os.kill(a.parent_pid,0)
            except ProcessLookupError:break
        request=a.directory/f'request-{seq}.txt';response=a.directory/f'response-{seq}.txt'
        if not request.exists():time.sleep(.01);continue
        try:
            lines=request.read_text().splitlines()
            if len(lines)!=7 or lines[0]!='TM2020_GPU_UPDATE_V1' or int(lines[1])!=seq:raise ValueError('Invalid GPU request protocol')
            checkpoint,rollout,envs,output,metrics_file=lines[2:]
            cp=Checkpoint.load(checkpoint,helper)
            metrics=optimizer.update(cp,rollout,int(envs),helper)
            cp.save(output,helper)
            atomic_text(Path(metrics_file),json.dumps(metrics,indent=2)+'\n')
            text='TM2020_GPU_UPDATE_RESULT_V1\n'+str(seq)+'\n0\n'
            values=[metrics[k] for k in ('policy_loss','value_loss','approx_kl','gradient_norm','clip_fraction','minibatches','epochs','kl_stopped')]
            text+=' '.join(str(int(x)) if isinstance(x,bool) else repr(x) for x in values)+'\n'
            atomic_text(response,text);print('CUDA_PPO',seq,json.dumps(metrics),flush=True)
        except Exception as error:
            atomic_text(response,f'TM2020_GPU_UPDATE_RESULT_V1\n{seq}\n1\n{str(error).replace(chr(10)," ")}\n')
            traceback.print_exc();raise
        seq+=1

if __name__=='__main__':main()
