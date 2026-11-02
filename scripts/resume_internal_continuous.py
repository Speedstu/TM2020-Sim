#!/usr/bin/env python3
"""Continue the selected internal continuous PPO policy on CUDA.

Simulator-only: does not start Trackmania, the hourly monitor, or a virtual controller.
STOP file or SIGTERM saves the latest weights at the next update boundary.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import time
import torch
import numpy as np
from compare_hybrid_ppo import Policy, Episodes, evaluate, update, cases, save_json
from gpu_ppo import Checkpoint, Helpers
from run_fast_ppo import ROOT

stop_requested = False

def request_stop(signum, frame):
    global stop_requested
    stop_requested = True

def save_torch(path, value):
    temp = path.with_name(path.name + '.tmp')
    torch.save(value, temp)
    os.replace(temp, path)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path,default=ROOT/'local/recon/internal-0.46/ppo-comparison/46602-continuous/best.pt')
    parser.add_argument('--prior',type=Path,default=ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint')
    parser.add_argument('--max-updates',type=int,default=512)
    parser.add_argument('--eval-every',type=int,default=8)
    parser.add_argument('--patience',type=int,default=10)
    parser.add_argument('--envs',type=int,default=16)
    parser.add_argument('--rollout',type=int,default=1024)
    parser.add_argument('--actor-lr',type=float,default=3e-7)
    parser.add_argument('--cases',type=int,default=41)
    parser.add_argument('--min-gain-ms',type=float,default=50)
    args=parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; refusing CPU fallback')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(56602)
    args.output.mkdir(parents=True,exist_ok=True)
    helpers=Helpers()
    prior=Checkpoint.load(args.prior,helpers)
    if (prior.nx,prior.na,prior.hidden)!=(240,1,512):
        raise ValueError('Wrong prior model')
    policy=Policy(prior,'continuous')
    optim=torch.optim.Adam([{'params':policy.actor.parameters(),'lr':args.actor_lr},
                          {'params':policy.critic.parameters(),'lr':3e-5},
                          {'params':[policy.logstd],'lr':args.actor_lr}],eps=1e-8)
    last=args.output/'last.pt'
    best=args.output/'best.pt'
    start_update=0
    no_gain=0
    if last.exists():
        state=torch.load(last,map_location='cpu',weights_only=True)
        policy.load_state_dict(state['model'])
        optim.load_state_dict(state['optimizer'])
        torch.cuda.set_rng_state(state['cudaRng'])
        start_update=int(state['update'])
        no_gain=int(state.get('noGain',0))
        print(f'RESUMED update={start_update}',flush=True)
    else:
        policy.load_state_dict(torch.load(args.source,map_location='cpu',weights_only=True))
        save_torch(best,policy.state_dict())
        policy.export(prior,args.output/'initial.tmppo',helpers)
        print(f'WARM-START source={args.source} device={torch.cuda.get_device_name()} ',flush=True)
    dev=cases(46900,args.cases)
    environment=Episodes(args.envs,56602)
    evaluator=environment.env.__class__(args.cases)
    report_path=args.output/'status.json'
    history_path=args.output/'evaluations.jsonl'
    try:
        baseline=evaluate(policy,evaluator,dev)
        metric=(baseline['finishes'],-baseline['meanWithDnf40sMs'])
        if (args.output/'best-score.json').exists():
            d=json.loads((args.output/'best-score.json').read_text())
            metric=(int(d['finishes']),-float(d['meanWithDnf40sMs']))
        else:
            save_json(args.output/'best-score.json',baseline)
        print('BASELINE '+json.dumps({k:v for k,v in baseline.items() if k!='trials'}),flush=True)
        last_status={}
        u=start_update
        for u in range(start_update+1,args.max_updates+1):
            if stop_requested or (args.output/'STOP').exists():
                break
            t0=time.monotonic()
            metrics=update(policy,environment,optim,args.rollout)
            if u%args.eval_every==0 or u==args.max_updates:
                score=evaluate(policy,evaluator,dev)
                current=(score['finishes'],-score['meanWithDnf40sMs'])
                improved=current[0]>metric[0] or (current[0]==metric[0] and current[1]>metric[1]+args.min_gain_ms)
                if improved:
                    metric=current;no_gain=0
                    save_torch(best,policy.state_dict())
                    save_json(args.output/'best-score.json',score)
                    temp=args.output/'best-new.tmppo'
                    if temp.exists():temp.unlink()
                    policy.export(prior,temp,helpers)
                    os.replace(temp,args.output/'best.tmppo')
                else:
                    no_gain+=1
                event={'update':u,'improved':improved,'noGain':no_gain,
                       **{k:v for k,v in score.items() if k!='trials'}}
                with history_path.open('a') as f:
                    f.write(json.dumps(event)+'\n')
                save_torch(last,{'model':policy.state_dict(),'optimizer':optim.state_dict(),
                                 'cudaRng':torch.cuda.get_rng_state().cpu(),'update':u,'noGain':no_gain})
                last_status={'state':'training','updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                             'update':u,'transitions':u*args.envs*args.rollout,
                             'seed':56602,'arm':'continuous','trainingSource':str(args.source),
                             'finishes':score['finishes'],'trials':score['count'],
                             'meanMs':score['meanMs'],'bestMs':score['bestMs'],
                             'bestFinishes':metric[0],'bestPenalizedMeanMs':-metric[1],
                             'noGainEvaluations':no_gain,'gpu':torch.cuda.get_device_name(),
                             'realGameFinishVerified':False}
                save_json(report_path,last_status)
                print('EVAL '+json.dumps({k:v for k,v in last_status.items() if k not in ('trainingSource','gpu')}),flush=True)
                if no_gain>=args.patience:
                    print(f'STOP plateau {no_gain} evaluations without improvement',flush=True)
                    break
            elif u%4==0:
                print(f'UPDATE {u}, transitions={u*args.envs*args.rollout}, SPS={int(args.envs*args.rollout/(time.monotonic()-t0))}',flush=True)
        if not last.exists() or (last_status.get('update',0)<u):
            save_torch(last,{'model':policy.state_dict(),'optimizer':optim.state_dict(),
                             'cudaRng':torch.cuda.get_rng_state().cpu(),'update':u,'noGain':no_gain})
        last_status.update(state='stopped',stoppedAt=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        save_json(report_path,last_status)
        print('TRAINING STOPPED '+json.dumps(last_status),flush=True)
    finally:
        evaluator.close();environment.env.close()

if __name__=='__main__':
    signal.signal(signal.SIGTERM,request_stop)
    signal.signal(signal.SIGINT,request_stop)
    main()
