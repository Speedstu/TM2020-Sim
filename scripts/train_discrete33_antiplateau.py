#!/usr/bin/env python3
"""GPU PPO for 33 discrete steering bins, with guarded anti-plateau restarts.

Simulator-only. Never controls Trackmania or launches a virtual controller.
Work is saved atomically at every evaluation. STOP file or SIGTERM stops safely.
"""
import argparse
import json
import os
import signal
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F

from compare_hybrid_ppo import Policy, evaluate, update, cases, save_json
from cuda_history import CudaHistoryEpisodes
from gpu_ppo import Helpers, Checkpoint
from run_fast_ppo import ROOT
from vector_physics import VectorPhysics

STOP = False
def on_signal(signum, frame):
    global STOP
    STOP = True

def atomic_torch(path, data):
    tmp = path.with_suffix(path.suffix+'.tmp')
    torch.save(data, tmp)
    os.replace(tmp, path)

class AdaptiveDiscrete33(Policy):
    """Training temperature affects exploration; deterministic argmax is unchanged."""
    def __init__(self, prior):
        super().__init__(prior, 'discrete33')
        self.temperature = 1.0

    def action(self, x, deterministic=False):
        out = self.actor(x)
        pedals = (out[:,:2] >= 0).double() if deterministic else torch.bernoulli(torch.sigmoid(out[:,:2]))
        logits = out[:,2:] / self.temperature
        z = logits.argmax(-1) if deterministic else torch.multinomial(logits.softmax(-1),1).flatten()
        steer = -1.+2.*z.double()/32.
        actions = torch.cat((pedals,steer[:,None]),1)
        stored = torch.cat((pedals,z.double()[:,None]),1)
        return actions,stored,self.logp(x,stored),self.critic(x).flatten()

    def logp(self,x,stored):
        out = self.actor(x)
        p = -F.binary_cross_entropy_with_logits(out[:,:2],stored[:,:2],reduction='none').sum(-1)
        steer = F.log_softmax(out[:,2:]/self.temperature,-1).gather(1,stored[:,2].long()[:,None]).flatten()
        return p+steer

class CurriculumEpisodes(CudaHistoryEpisodes):
    def __init__(self,n,seed):
        self.level = 0
        super().__init__(n,seed)
    def reset(self,i):
        super().reset(i)
        episode=int(self.episodes[i])-1
        rng=np.random.default_rng((self.seed*100003+i*7919+episode*2654435761)%4294967295)
        probability=(.10,.16,.23,.30)[min(self.level,3)]
        if rng.random()<probability:
            self.perturb[i]={'warm':int(rng.integers(0,31)),
                             'duration':int(rng.integers(1,7)),
                             'steerKick':float(rng.choice([-1.,1.])*rng.uniform(.15,.5+.04*min(self.level,3)))}
        else:
            self.perturb[i]={'warm':0,'duration':0,'steerKick':0.}

def new_optimizer(model,cycle):
    actor_lrs=[3e-7,1e-6,2e-6,7e-7,3e-6,5e-7,1.5e-6]
    actor_lr=actor_lrs[cycle%len(actor_lrs)]
    return torch.optim.Adam([
        {'params':model.actor.parameters(),'lr':actor_lr},
        {'params':model.critic.parameters(),'lr':3e-5},
        {'params':[model.logstd],'lr':actor_lr},
    ],eps=1e-8),actor_lr

def summarize(result):
    return {k:v for k,v in result.items() if k!='trials'}

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--output',type=Path,required=True)
    a.add_argument('--source',type=Path,default=ROOT/'local/recon/internal-0.46/ppo-comparison/46602-discrete33/best.pt')
    a.add_argument('--prior',type=Path,default=ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint')
    a.add_argument('--updates',type=int,default=1536)
    a.add_argument('--eval-every',type=int,default=8)
    a.add_argument('--patience',type=int,default=4)
    a.add_argument('--max-recoveries',type=int,default=7)
    a.add_argument('--envs',type=int,default=16)
    a.add_argument('--rollout',type=int,default=1024)
    args=a.parse_args()
    if not torch.cuda.is_available():raise RuntimeError('CUDA missing: no CPU fallback')
    if args.updates<=0 or args.eval_every<=0 or args.patience<=0:raise ValueError('Invalid limits')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(73302)
    args.output.mkdir(parents=True,exist_ok=True)
    helpers=Helpers()
    prior=Checkpoint.load(args.prior,helpers)
    if (prior.nx,prior.na,prior.hidden)!=(240,1,512):raise ValueError('Wrong encoder dimensions')
    model=AdaptiveDiscrete33(prior)
    last_file=args.output/'last.pt'
    best_file=args.output/'best.pt'
    status_file=args.output/'status.json'
    eval_file=args.output/'evaluations.jsonl'
    update_number=0
    recoveries=0
    stale=0
    best_score=float('inf')
    if last_file.exists():
        d=torch.load(last_file,map_location='cpu',weights_only=True)
        model.load_state_dict(d['model'])
        update_number=int(d['updates'])
        recoveries=int(d['recoveries'])
        stale=int(d['stale'])
        best_score=float(d['bestScore'])
        model.temperature=float(d['temperature'])
        optimizer,actor_lr=new_optimizer(model,recoveries)
        optimizer.load_state_dict(d['optimizer'])
        print('RESUMED '+json.dumps({'update':update_number,'recoveries':recoveries,'temperature':model.temperature}),flush=True)
    else:
        model.load_state_dict(torch.load(args.source,map_location='cpu',weights_only=True))
        atomic_torch(best_file,model.state_dict())
        optimizer,actor_lr=new_optimizer(model,0)
        model.export(prior,args.output/'initial.tmppo',helpers)
        print('WARM_START '+json.dumps({'source':str(args.source),'gpu':torch.cuda.get_device_name()}),flush=True)
    episodes=CurriculumEpisodes(args.envs,73302)
    dev_env=VectorPhysics(41)
    dev_cases=[cases(46900),cases(47000)] # 82 development trials (shared across evaluations)
    # 47100 remains held-out: not used for checkpoint selection.
    holdout_cases=cases(47100)
    temperatures=(1.0,2.0,4.0,1.5,6.0,2.5,8.0,3.0)
    stopped='update budget'
    try:
        if not (args.output/'protocol.json').exists():
            save_json(args.output/'protocol.json',{
                'name':'Trackmania anti-plateau discrete33 CUDA PPO',
                'source':str(args.source),'seeds':{'train':73302,'dev':[46900,47000],'holdout':47100},
                'actionSpace':'binary gas, binary brake, 33 categorical steering bins',
                'curriculum':'random short early steering disturbance; probability .10 to .30',
                'antiPlateau':{'patience':args.patience,'maxRecoveries':args.max_recoveries,
                               'temperatures':temperatures,
                               'actorLearningRates':[3e-7,1e-6,2e-6,7e-7,3e-6,5e-7,1.5e-6],
                               'recovery':'restore best model, reset Adam, vary temperature, train curriculum'},
                'objective':'maximize dev completions, then lower mean time with DNF=40s; plateau tolerance 25ms',
                'gpuHistory':'CUDA-resident 240 feature frame history, 48 feature upload per simulation step',
                'nativeCpuWorkers':int(os.environ.get('TM2020_PHYSICS_WORKERS','16')),
                'gameFinishVerified':False})
        def check():
            outcomes=[evaluate(model,dev_env,trial) for trial in dev_cases]
            success=sum(x['finishes'] for x in outcomes)
            total=sum(x['count'] for x in outcomes)
            penalized=sum(x['meanWithDnf40sMs']*x['count'] for x in outcomes)/total
            times=[t['finishMs'] for x in outcomes for t in x['trials'] if t['finishMs'] is not None]
            return {'finishes':success,'count':total,'penalizedMeanMs':penalized,
                    'meanFinishMs':float(np.mean(times)) if times else None,
                    'bestMs':min(times) if times else None, 'measuredInGame':False}
        if not (args.output/'baseline.json').exists():
            baseline=check()
            save_json(args.output/'baseline.json',baseline)
            print('BASELINE '+json.dumps(baseline),flush=True)
            # Score includes DNF penalty, favoring both completion and speed.
            best_score=baseline['penalizedMeanMs']
            save_json(args.output/'best-score.json',baseline)
            if not (args.output/'best.tmppo').exists():
                model.export(prior,args.output/'best.tmppo',helpers)
        for u in range(update_number+1,args.updates+1):
            if STOP or (args.output/'STOP').exists():
                stopped='requested stop'
                break
            cycle_start=time.monotonic()
            metrics=update(model,episodes,optimizer,args.rollout)
            update_number=u
            if u%4==0:print('UPDATE '+json.dumps({
                'update':u,'transitions':u*args.envs*args.rollout,
                'sps':round(args.envs*args.rollout/(time.monotonic()-cycle_start)),
                'recoveries':recoveries,'temperature':model.temperature,
                'kl':metrics['kl']}),flush=True)
            if u%args.eval_every and u!=args.updates:continue
            evaluation=check()
            # Do not sacrifice too much consistency for a one-off fast lap.
            prev=json.loads((args.output/'best-score.json').read_text())
            improvement=(evaluation['penalizedMeanMs']<best_score-25 and
                         evaluation['finishes']>=prev['finishes']-1) or (
                            evaluation['finishes']>prev['finishes'] and
                            evaluation['penalizedMeanMs']<=best_score+100)
            if improvement:
                best_score=evaluation['penalizedMeanMs']
                stale=0
                atomic_torch(best_file,model.state_dict())
                save_json(args.output/'best-score.json',evaluation)
                tmppo_temp=args.output/'best-export.tmp'
                if tmppo_temp.exists():tmppo_temp.unlink()
                model.export(prior,tmppo_temp,helpers)
                os.replace(tmppo_temp,args.output/'best.tmppo')
            else:stale+=1
            event={'update':u,'transitions':u*args.envs*args.rollout,
                   'temperature':model.temperature,'recoveries':recoveries,
                   'improved':improvement,'stale':stale,'actorLr':actor_lr,**evaluation}
            with eval_file.open('a') as log:log.write(json.dumps(event)+'\n')
            print('EVAL '+json.dumps(event),flush=True)
            if stale>=args.patience:
                if recoveries>=args.max_recoveries:
                    stopped='plateau after recovery budget'
                else:
                    recoveries+=1
                    stale=0
                    model.load_state_dict(torch.load(best_file,map_location='cpu',weights_only=True))
                    model.temperature=temperatures[recoveries%len(temperatures)]
                    episodes.level=min(recoveries,3)
                    optimizer,actor_lr=new_optimizer(model,recoveries)
                    # Escape sharp categorical peaks without losing best known weights.
                    with torch.no_grad():
                        model.actor[2].bias[2:].add_(torch.randn_like(model.actor[2].bias[2:])*.10*recoveries)
                    print('ANTI_PLATEAU_RECOVERY '+json.dumps({
                        'recovery':recoveries,'temperature':model.temperature,
                        'curriculumLevel':episodes.level,'actorLr':actor_lr,
                        'bestPenalizedMeanMs':best_score}),flush=True)
            atomic_torch(last_file,{'model':model.state_dict(),
                       'optimizer':optimizer.state_dict(),
                       'cudaRng':torch.cuda.get_rng_state().cpu(),
                       'updates':u,'recoveries':recoveries,'stale':stale,
                       'bestScore':best_score,'temperature':model.temperature})
            state={'state':'training','update':u,'transitions':u*args.envs*args.rollout,
                   'bestPenalizedMeanMs':best_score,
                   'bestFinishes':json.loads((args.output/'best-score.json').read_text())['finishes'],
                   'latestFinishes':evaluation['finishes'],'latestBestMs':evaluation['bestMs'],
                   'recoveries':recoveries,'temperature':model.temperature,
                   'stale':stale,'source':str(args.source),
                   'gpu':torch.cuda.get_device_name(),'realGameFinishVerified':False,
                   'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
            save_json(status_file,state)
            if stopped!='update budget':break
        else:
            stopped='update budget complete'
        with torch.no_grad():
            original=model.state_dict()
            model.load_state_dict(torch.load(best_file,map_location='cpu',weights_only=True))
            held=evaluate(model,dev_env,holdout_cases)
            model.load_state_dict(original)
        save_json(args.output/'holdout.json',held)
        final=json.loads(status_file.read_text()) if status_file.exists() else {}
        final.update({'state':'stopped','reason':stopped,'stoppedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                      'holdoutFinishes':held['finishes'],'holdoutTrials':held['count'],
                      'realGameFinishVerified':False})
        save_json(status_file,final)
        print('TRAINING_STOP '+json.dumps(final),flush=True)
    finally:
        episodes.env.close()
        dev_env.close()

if __name__=='__main__':
    signal.signal(signal.SIGINT,on_signal)
    signal.signal(signal.SIGTERM,on_signal)
    main()
