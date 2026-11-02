#!/usr/bin/env python3
"""Bounded PPO residual on a disclosed map-specific native trajectory tracker."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import signal
import time
import numpy as np
import torch
from torch import nn
import torch.nn.functional as F
from compare_hybrid_ppo import save_json
from ppo_time_credit import update
from hybrid_tracking import DIR,API,PHYSICS,Hybrid,load_asset,save_asset,cases
from tune_hybrid_tracking import NativeEvaluator
from robust_ppo import atomic_torch
from vector_physics import VectorPhysics

STOP=False
def stop(*_):
    global STOP
    STOP=True


class ResidualPolicy(nn.Module):
    def __init__(self):
        super().__init__()
        self.actor=nn.Sequential(nn.Linear(12,32),nn.Tanh(),nn.Linear(32,1))
        self.critic=nn.Sequential(nn.Linear(12,32),nn.Tanh(),nn.Linear(32,1))
        self.logstd=nn.Parameter(torch.tensor(math.log(.08),dtype=torch.float64))
        self.double().cuda()
        with torch.no_grad():self.actor[2].weight.zero_();self.actor[2].bias.zero_();self.critic[2].weight.zero_();self.critic[2].bias.fill_(.8)
    def logp(self,x,z):
        mean=self.actor(x).flatten();latent=z[:,2]
        jac=2*(math.log(2)-latent-F.softplus(-2*latent))
        return -.5*((latent-mean)*torch.exp(-self.logstd)).square()-.5*math.log(2*math.pi)-self.logstd-jac
    def action(self,x,deterministic=False):
        mean=self.actor(x).flatten();z=mean if deterministic else mean+torch.randn_like(mean)*self.logstd.exp()
        action=torch.stack((torch.ones_like(z),torch.zeros_like(z),z.tanh()),1)
        stored=torch.stack((torch.ones_like(z),torch.zeros_like(z),z),1)
        return action,stored,self.logp(x,stored),self.critic(x).flatten()
    def export(self,path,reference,gains):
        w=[]
        for layer in (self.actor[0],self.actor[2]):w.extend([layer.weight.detach().cpu().numpy().ravel(),layer.bias.detach().cpu().numpy()])
        save_asset(path,reference,gains,np.concatenate(w))


class Episodes:
    def __init__(self,n,seed,asset,scale):
        self.n=n;self.seed=seed;self.scale=scale;self.episodes=np.zeros(n,dtype=np.int64)
        self.env=VectorPhysics(n,decision_ticks=1,api_path=API,library=PHYSICS);self.controller=Hybrid(asset,n)
        for i in range(n):self.reset(i)
        self.controller.act(self.env);self.history=self.controller.features.copy()
        self.cuda_history=torch.as_tensor(self.history.copy(),device='cuda')
    def reset(self,i):
        seed=(self.seed*100003+i*10007+int(self.episodes[i])*31337)%4294967295;self.episodes[i]+=1
        self.env.reset(i,int(seed));self.controller.reset(i)
    def step(self,action):
        controls=self.controller.act(self.env,self.scale*action[:,2]);self.env.step(controls)
        rewards=np.array([s.reward for s in self.env.states[:self.n]])*.01
        done=np.array([bool(s.terminated or s.truncated) for s in self.env.states[:self.n]])
        for i in np.flatnonzero(done):self.reset(int(i))
        self.controller.act(self.env);self.history=self.controller.features.copy()
        self.cuda_history=torch.as_tensor(self.history.copy(),device='cuda')
        return rewards,done
    def close(self):self.controller.close();self.env.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--asset',type=Path,required=True)
    p.add_argument('--gains',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--updates',type=int,default=48);p.add_argument('--seed',type=int,default=105201)
    p.add_argument('--sigma',type=float,default=.08)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1);torch.manual_seed(a.seed);torch.use_deterministic_algorithms(True)
    gains=json.loads(a.gains.read_text())['gains'];gains[5]=.05;ref,_,_=load_asset(a.asset)
    teacher=a.output/'base.tmhyb';save_asset(teacher,ref,gains)
    model=ResidualPolicy()
    with torch.no_grad():model.logstd.fill_(math.log(a.sigma))
    optim=torch.optim.Adam([{'params':model.actor.parameters(),'lr':1e-5},
                {'params':model.critic.parameters(),'lr':1e-4},{'params':[model.logstd],'lr':1e-5}],eps=1e-8)
    episodes=Episodes(16,a.seed,teacher,gains[5]);evaluator=NativeEvaluator(32,teacher)
    dev=cases(105202,32,True);best=None;best_update=0;stale=0;start=time.monotonic()
    save_json(a.output/'protocol.json',{'seed':a.seed,'envs':16,'rollout':1024,'updates':a.updates,
        'decisionMs':10,'gains':gains,'residualBound':gains[5],'architecture':'12->32 tanh->1 tanh',
        'reward':'native minimum-time v3 unchanged','gaeLambda':.995**.2,'referenceAssisted':True,
        'goal':'speed and completion across complete perturbed races','realGameVerified':False})
    try:
        for u in range(a.updates+1):
            if STOP or (a.output/'STOP').exists():break
            metrics=update(model,episodes,optim,1024,gae_lambda=.995**.2) if u else None
            if u%4==0:
                exported=a.output/'next.tmhyb';model.export(exported,ref,gains)
                evaluator.asset=exported;trials,seconds=evaluator.evaluate(gains,dev)
                times=[r['finishMs'] or 40000 for r in trials];finishes=sum(r['finishMs'] is not None for r in trials)
                score=(finishes,-float(np.mean(times)));improved=best is None or score>best
                if improved:
                    best=score;best_update=u;stale=0;atomic_torch(a.output/'best.pt',model.state_dict())
                    model.export(a.output/'best.tmhyb',ref,gains)
                else:stale+=1
                record={'update':u,'finishes':finishes,'count':32,'penalizedMeanMs':float(np.mean(times)),
                        'bestUpdate':best_update,'improved':improved,'trials':trials,'referenceAssisted':True,'realGameVerified':False}
                with (a.output/'evaluations.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
                save_json(a.output/'status.json',record);print(json.dumps({k:v for k,v in record.items() if k!='trials'}),flush=True)
                if stale>=6:break
            atomic_torch(a.output/'last.pt',{'model':model.state_dict(),'optimizer':optim.state_dict(),'update':u,
                 'cpuRng':torch.get_rng_state(),'cudaRng':torch.cuda.get_rng_state().cpu()})
        save_json(a.output/'completed.json',{'updates':u,'bestUpdate':best_update,'seconds':time.monotonic()-start,'state':'stopped','realGameVerified':False})
    finally:episodes.close();evaluator.close()


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
