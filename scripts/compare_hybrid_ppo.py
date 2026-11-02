#!/usr/bin/env python3
"""Matched finite-budget CUDA PPO experiment. No timer or game input backend.

Three action distributions share the same frozen prior, map, pure time reward,
episode seed schedule, perturbations, rollout/optimizer settings and budget.
Results are simulator evidence only; game results require a separate live log.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import time
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from gpu_ppo import Checkpoint, Helpers
from generalist_engine import SCHEMA
from vector_physics import VectorPhysics
from run_fast_ppo import ROOT

ARMS=('continuous','discrete17','discrete33')
MASK=[frame*48+channel for frame in range(5) for channel in (13,14)]

def save_json(path,value):
    tmp=Path(str(path)+'.tmp');tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');tmp.replace(path)

class Policy(nn.Module):
    def __init__(self,prior,arm):
        super().__init__();self.arm=arm;self.bins=0 if arm=='continuous' else int(arm[8:]);self.outputs=self.bins+2 if self.bins else 3
        self.pedal_temperature=1.
        self.actor=nn.Sequential(nn.Linear(240,512),nn.Tanh(),nn.Linear(512,self.outputs))
        self.critic=nn.Sequential(nn.Linear(240,512),nn.Tanh(),nn.Linear(512,1))
        self.logstd=nn.Parameter(torch.tensor(math.log(.025),dtype=torch.float64),requires_grad=not self.bins)
        self.double()
        p=prior.parameters;bias=512*240;head=bias+512;tail=head+512
        with torch.no_grad():
            self.actor[0].weight.copy_(torch.from_numpy(p[:bias].reshape(512,240)))
            self.actor[0].bias.copy_(torch.from_numpy(p[bias:head]))
            self.actor[2].weight.zero_();self.actor[2].bias.zero_()
            self.actor[2].bias[:2].copy_(torch.tensor([5.3,-5.3]))
            if self.bins:
                latent=np.arctanh(np.clip(np.linspace(-1,1,self.bins),-.995,.995))
                self.actor[2].weight[2:].copy_(torch.from_numpy(latent[:,None]*p[head:tail][None,:]/.025**2))
                self.actor[2].bias[2:].copy_(torch.from_numpy((latent*p[tail]-.5*latent**2)/.025**2))
            else:
                self.actor[2].weight[2].copy_(torch.from_numpy(p[head:tail]))
                self.actor[2].bias[2]=float(p[tail])
            self.critic[0].weight.copy_(self.actor[0].weight);self.critic[0].bias.copy_(self.actor[0].bias)
            self.critic[2].weight.zero_();self.critic[2].bias.fill_(.7)
        self.to('cuda')

    def action(self,x,deterministic=False):
        out=self.actor(x);pedals=(out[:,:2]>=0).double() if deterministic else torch.bernoulli(torch.sigmoid(out[:,:2]/self.pedal_temperature))
        if self.bins:
            logits=out[:,2:];z=logits.argmax(-1) if deterministic else torch.multinomial(torch.softmax(logits,-1),1).flatten()
            steer=-1+2*z.double()/(self.bins-1)
        else:
            z=out[:,2] if deterministic else out[:,2]+torch.randn_like(out[:,2])*self.logstd.exp()
            steer=z.tanh()
        action=torch.cat((pedals,steer[:,None]),1)
        stored=torch.cat((pedals,z.double()[:,None]),1)
        return action,stored,self.logp(x,stored),self.critic(x).flatten()

    def logp(self,x,stored):
        out=self.actor(x);pedal=-F.binary_cross_entropy_with_logits(out[:,:2]/self.pedal_temperature,stored[:,:2],reduction='none').sum(-1)
        z=stored[:,2]
        if self.bins:steer=torch.log_softmax(out[:,2:],-1).gather(1,z.long()[:,None]).flatten()
        else:
            jac=2*(math.log(2)-z-F.softplus(-2*z))
            steer=-.5*((z-out[:,2])*torch.exp(-self.logstd)).square()-.5*math.log(2*math.pi)-self.logstd-jac
        return pedal+steer

    def export(self,prior,path,helpers,decision_ticks=5,schema=None):
        if decision_ticks not in (1,5):raise ValueError('Unsupported policy decision interval')
        cp=copy.copy(prior);cp.nx=self.actor[0].in_features;cp.na=self.outputs;cp.schema=(schema or SCHEMA)+'|history=5|policy_actions=hybrid_'+self.arm+'_v1'
        if decision_ticks==1:cp.schema=cp.schema.replace('tm2020_generalist48_v1','tm2020_generalist48_100hz_v1',1)
        values=[]
        for net in (self.actor,self.critic):
            for layer in (net[0],net[2]):values.extend((layer.weight.detach().cpu().numpy().ravel(),layer.bias.detach().cpu().numpy()))
        ls=np.zeros(self.outputs);ls[-1]=self.logstd.item()
        cp.parameters=np.concatenate((*values,ls));cp.export_policy(path,helpers)

def cases(seed,count=41):
    rng=np.random.default_rng(seed);result=[]
    for i in range(count):
        result.append({'seed':int(seed*100+i),'warm':int(rng.integers(0,21)),
                       'duration':int(rng.integers(1,6)),
                       'steerKick':0. if i==0 else float(rng.choice([-1,1])*rng.uniform(.15,.5))})
    return result

def frame(observations):
    x=observations.copy();x[:,13:15]=0.;return x

def quantized(actions):
    controls=actions.copy();s=controls[:,2]
    controls[:,2]=np.sign(s)*np.floor(np.abs(s)*127.+.5)/127.
    return controls.astype(np.float32)

class Episodes:
    def __init__(self,n,seed,physics=None):
        self.env=physics if physics is not None else VectorPhysics(n);self.n=n;self.seed=seed;self.episodes=np.zeros(n,dtype=np.int64)
        self.history=np.zeros((n,240));self.steps=np.zeros(n,dtype=np.int64);self.perturb=[None]*n
        for i in range(n):self.reset(i)
    def reset(self,i):
        episode=int(self.episodes[i]);self.episodes[i]+=1
        seed=(self.seed*1000003+i*10007+episode*31337)%4294967295
        self.env.reset(i,seed);self.history[i]=np.tile(frame(self.env.observations[i:i+1])[0],5);self.steps[i]=0
        rng=np.random.default_rng(seed)
        self.perturb[i]={'warm':int(rng.integers(0,21)),'duration':int(rng.integers(1,6)),
                         'steerKick':float(rng.choice([-1,1])*rng.uniform(.15,.5)) if rng.random()<.1 else 0.}
    def step(self,actions):
        controls=actions.copy()
        for i,c in enumerate(self.perturb):
            if c['warm']<=self.steps[i]<c['warm']+c['duration']:controls[i,2]=np.clip(controls[i,2]+c['steerKick'],-1,1)
        self.env.step(quantized(controls));self.steps+=1
        reward=np.array([s.reward for s in self.env.states[:self.n]])*.01
        done=np.array([bool(s.terminated or s.truncated) for s in self.env.states[:self.n]])
        self.history[:,:-48]=self.history[:,48:];self.history[:,-48:]=frame(self.env.observations)
        for i in np.flatnonzero(done):self.reset(int(i))
        return reward,done

@torch.no_grad()
def evaluate(policy,environment,trial_cases):
    n=len(trial_cases);assert environment.n==n
    for i,c in enumerate(trial_cases):environment.reset(i,c['seed'])
    history=np.tile(frame(environment.observations),(1,5));steps=0;active=np.ones(n,dtype=bool)
    while active.any() and steps<4000//getattr(environment,'decision_ticks',5):
        x=torch.as_tensor(history,device='cuda');actions=policy.action(x,True)[0].cpu().numpy()
        for i,c in enumerate(trial_cases):
            if c['warm']<=steps<c['warm']+c['duration']:actions[i,2]=np.clip(actions[i,2]+c['steerKick'],-1,1)
        environment.step(quantized(actions));steps+=1
        history[:,:-48]=history[:,48:];history[:,-48:]=frame(environment.observations)
        active=np.array([not(s.terminated or s.truncated) for s in environment.states[:n]])
    trials=[dict(c,finishMs=s.finish_ms if s.finish_ms>=0 else None,checkpoints=s.checkpoints,physicsTicks=s.tick)
            for c,s in zip(trial_cases,environment.states[:n])]
    finished=[t['finishMs'] for t in trials if t['finishMs'] is not None]
    return {'trials':trials,'finishes':len(finished),'count':n,'finishRate':len(finished)/n,
            'meanMs':float(np.mean(finished)) if finished else None,
            'medianMs':float(np.median(finished)) if finished else None,
            'bestMs':min(finished) if finished else None,
            'meanWithDnf40sMs':float(np.mean([t['finishMs'] if t['finishMs'] is not None else 40000 for t in trials])),
            'measuredInGame':False}

def update(policy,episodes,optimizer,rollout):
    n=episodes.n;fields={k:[] for k in ('x','z','logp','value','reward','done')};start=time.monotonic()
    for _ in range(rollout):
        x=episodes.cuda_history if hasattr(episodes,'cuda_history') else torch.as_tensor(episodes.history.copy(),device='cuda')
        with torch.no_grad():action,z,lp,value=policy.action(x)
        reward,done=episodes.step(action.cpu().numpy())
        for key,val in (('x',x),('z',z),('logp',lp),('value',value),('reward',torch.tensor(reward,device='cuda')),('done',torch.tensor(done,device='cuda'))):fields[key].append(val)
    data={k:torch.stack(v) for k,v in fields.items()}
    with torch.no_grad():
        value=policy.critic(episodes.cuda_history if hasattr(episodes,'cuda_history') else torch.as_tensor(episodes.history,device='cuda')).flatten();carry=torch.zeros(n,device='cuda',dtype=torch.float64)
        advantages=torch.empty_like(data['reward'])
        for t in range(rollout-1,-1,-1):
            alive=(~data['done'][t]).double();delta=data['reward'][t]+alive*value-data['value'][t]
            carry=delta+.995*alive*carry;advantages[t]=carry;value=data['value'][t]
        target=advantages+data['value'];advantages=(advantages-advantages.mean())/(advantages.std(unbiased=False)+1e-8)
    x=data['x'].flatten(0,1);z=data['z'].flatten(0,1);old=data['logp'].flatten();adv=advantages.flatten();target=target.flatten();count=n*rollout
    with torch.no_grad():identity=(policy.logp(x,z)-old).abs().max().item()
    if identity>1e-7:raise RuntimeError(f'Behavior identity error {identity}')
    kl=0.;minibatches=0
    for epoch in range(4):
        with torch.no_grad():
            diff=policy.logp(x,z)-old;kl=(diff.exp()-1-diff).mean().item()
        if kl>.0045:break
        for indices in torch.randperm(count,device='cuda').split(1024):
            ratio=(policy.logp(x[indices],z[indices])-old[indices]).clamp(-60,60).exp()
            actor=-torch.minimum(ratio*adv[indices],ratio.clamp(.9,1.1)*adv[indices]).mean()
            critic=.5*(policy.critic(x[indices]).flatten()-target[indices]).square().mean()
            loss=actor+.5*critic;optimizer.zero_grad(set_to_none=True);loss.backward()
            norm=nn.utils.clip_grad_norm_(policy.parameters(),.5)
            if not torch.isfinite(norm):raise RuntimeError('Nonfinite PPO gradient')
            optimizer.step();minibatches+=1
            with torch.no_grad():policy.logstd.clamp_(-5,0)
    return {'seconds':time.monotonic()-start,'transitions':count,'behaviorLogpError':identity,'kl':kl,'minibatches':minibatches}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prior',type=Path,default=ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint')
    p.add_argument('--seeds',type=int,nargs='+',default=[46601,46602,46603]);p.add_argument('--updates',type=int,default=32)
    p.add_argument('--rollout',type=int,default=1024);p.add_argument('--envs',type=int,default=16);p.add_argument('--eval-every',type=int,default=8)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    if not torch.cuda.is_available():raise RuntimeError('CUDA required, no implicit CPU fallback')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    helpers=Helpers();prior=Checkpoint.load(args.prior,helpers)
    if (prior.nx,prior.na,prior.hidden)!=(240,1,512):raise ValueError('Expected common 240x512 steering prior')
    if np.any(prior.parameters[:240*512].reshape(512,240)[:,MASK]):raise ValueError('Prior consumes unqualified channels')
    dev=cases(46700);holdout=cases(46800)
    protocol={'arms':ARMS,'seeds':args.seeds,'updatesMax':args.updates,'transitionsPerUpdate':args.envs*args.rollout,
              'device':torch.cuda.get_device_name(),'dtype':'float64','priorSha256':hashlib.sha256(args.prior.read_bytes()).hexdigest(),
              'reward':'v3 pure minimum time: finish 100-seconds, DNF -140; scale .01; gamma 1; lambda .995',
              'architecture':'240 -> 512 tanh -> head; critic same; zero ground/turbo channels',
              'optimizer':{'epochs':4,'minibatch':1024,'actorLr':3e-7,'criticLr':3e-5,'clip':.1,'targetKl':.003,'entropy':0},
              'initialPrior':'same encoder and continuous Gaussian mean, sigma .025; categorical logits from Gaussian density on atanh(grid)',
              'perturbations':'early applied steering kicks, 50ms decisions; no partial resets, expert, replay, controller or route in observations',
              'developmentCases':dev,'holdoutCases':holdout,'gameFinishVerified':False}
    save_json(args.output/'protocol.json',protocol);report={'protocol':protocol,'runs':[]}
    for seed in args.seeds:
        models={};envs={};optimizers={};best={};plateaus={};stopped='budget';run={'seed':seed,'evaluations':[]}
        evaluation=VectorPhysics(41)
        try:
            for arm in ARMS:
                torch.manual_seed(seed);model=Policy(prior,arm);models[arm]=model;envs[arm]=Episodes(args.envs,seed)
                optimizers[arm]=torch.optim.Adam([{'params':model.actor.parameters(),'lr':3e-7},
                    {'params':model.critic.parameters(),'lr':3e-5},{'params':[model.logstd],'lr':3e-7}],eps=1e-8)
                folder=args.output/f'{seed}-{arm}';folder.mkdir();model.export(prior,folder/'initial.tmppo',helpers)
                result=evaluate(model,evaluation,dev);run['evaluations'].append({'arm':arm,'update':0,**result})
                best[arm]=(result['finishes'],-result['meanWithDnf40sMs']);plateaus[arm]=0
                torch.save(model.state_dict(),folder/'best.pt');save_json(folder/'initial.json',result)
                print(json.dumps({'seed':seed,'arm':arm,'update':0,**{k:v for k,v in result.items() if k!='trials'}}),flush=True)
            # Isolate each arm's CUDA RNG so round-robin ordering cannot change
            # the sampling stream used by another distribution.
            rng={arm:torch.Generator(device='cuda').manual_seed(seed).get_state() for arm in ARMS}
            updates=0
            for u in range(1,args.updates+1):
                for arm in ARMS:
                    torch.cuda.set_rng_state(rng[arm]);metrics=update(models[arm],envs[arm],optimizers[arm],args.rollout);rng[arm]=torch.cuda.get_rng_state()
                    print(json.dumps({'seed':seed,'arm':arm,'update':u,**metrics}),flush=True)
                updates=u
                if u%args.eval_every==0 or u==args.updates:
                    for arm in ARMS:
                        result=evaluate(models[arm],evaluation,dev);run['evaluations'].append({'arm':arm,'update':u,**result})
                        score=(result['finishes'],-result['meanWithDnf40sMs']);old=best[arm]
                        improved=score[0]>old[0] or (score[0]==old[0] and score[1]>old[1]+50)
                        plateaus[arm]=0 if improved else plateaus[arm]+1
                        folder=args.output/f'{seed}-{arm}';models[arm].export(prior,folder/f'update-{u}.tmppo',helpers)
                        if improved:best[arm]=score;torch.save(models[arm].state_dict(),folder/'best.pt')
                        print(json.dumps({'seed':seed,'arm':arm,'evaluationUpdate':u,**{k:v for k,v in result.items() if k!='trials'}}),flush=True)
                    save_json(args.output/'report.partial.json',{'completed':report['runs'],'current':run})
                    # Stop all arms together at a matched budget if any plateaus.
                    if max(plateaus.values())>=3:stopped='shared plateau cutoff';break
                if (args.output/'STOP').exists():stopped='explicit STOP';break
            run.update({'updates':updates,'transitionsPerArm':updates*args.envs*args.rollout,'stopReason':stopped,'holdout':{}})
            for arm in ARMS:
                model=models[arm];folder=args.output/f'{seed}-{arm}'
                torch.save({'model':model.state_dict(),'optimizer':optimizers[arm].state_dict(),'cudaRng':rng[arm],'updates':updates},folder/'last.pt')
                model.load_state_dict(torch.load(folder/'best.pt',weights_only=True));model.export(prior,folder/'best.tmppo',helpers)
                result=evaluate(model,evaluation,holdout);run['holdout'][arm]=result;save_json(folder/'holdout.json',result)
                print(json.dumps({'seed':seed,'arm':arm,'holdout':{k:v for k,v in result.items() if k!='trials'}}),flush=True)
            report['runs'].append(run);save_json(args.output/'report.json',report)
        finally:
            evaluation.close()
            for env in envs.values():env.env.close()
        if (args.output/'STOP').exists():break

if __name__=='__main__':main()
