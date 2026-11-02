"""72-feature PPO and complete checkpoints drawn only from the agent's laps."""
import copy
import os
from pathlib import Path
import numpy as np
import torch
from torch import nn
from compare_hybrid_ppo import Policy,quantized
from run_fast_ppo import ROOT
from vector_physics import VectorPhysics

SCHEMA='tm2020_preview72_v1|controls=binary_pedals_i8_steer|perception=static_goal_preview_omega_v1'
LIBRARY=Path(os.environ.get('TM2020_PREVIEW_LIBRARY',ROOT/'cache/preview-0.50-target/release/libtm2020_internal_perception.so'))
API=Path(os.environ.get('TM2020_PREVIEW_API',ROOT/'native/build-preview/libtm2020_vector_physics.so'))


class PreviewPolicy(Policy):
    def __init__(self,prior,source=None,pedal_temperature=1.):
        super().__init__(prior,'continuous')
        if source is not None:
            state=torch.load(source,map_location='cuda',weights_only=True)
            if 'model' in state:state=state['model']
            # Existing preview checkpoints already have the expanded width.
            if state['actor.0.weight'].shape[1]==360:
                for net in (self.actor,self.critic):net[0]=nn.Linear(360,512,device='cuda',dtype=torch.float64)
                self.load_state_dict(state)
            else:
                self.load_state_dict(state)
                for net in (self.actor,self.critic):
                    previous=net[0];layer=nn.Linear(360,512,device='cuda',dtype=torch.float64)
                    with torch.no_grad():
                        layer.weight.zero_();layer.bias.copy_(previous.bias)
                        for frame in range(5):layer.weight[:,frame*72:frame*72+48].copy_(previous.weight[:,frame*48:(frame+1)*48])
                    net[0]=layer
        else:
            for net in (self.actor,self.critic):
                old=net[0];new=nn.Linear(360,512,device='cuda',dtype=torch.float64)
                with torch.no_grad():
                    new.weight.zero_();new.bias.copy_(old.bias)
                    for f in range(5):new.weight[:,f*72:f*72+48].copy_(old.weight[:,f*48:(f+1)*48])
                net[0]=new
        if not .25<=pedal_temperature<=2.:raise ValueError('Pedal temperature outside tested range')
        self.pedal_temperature=pedal_temperature

    def export(self,prior,path,helpers,decision_ticks=5):
        if decision_ticks!=5:raise ValueError('Preview schema requires 50ms decisions')
        super().export(prior,path,helpers,decision_ticks=5,schema=SCHEMA)


def physics(n):return VectorPhysics(n,api_path=API,library=LIBRARY)


class OwnEpisodes:
    def __init__(self,n,seed,bank_fraction=.5,preview=True,snapshots_per_bin=16):
        if not 1<=snapshots_per_bin<=16:raise ValueError('Snapshots per time bin outside 1..16')
        self.snapshots_per_bin=snapshots_per_bin
        self.n=n;self.seed=seed;self.bank_fraction=bank_fraction;self.use_preview=preview
        self.width=72 if preview else 48;self.env=physics(n)
        self.episodes=np.zeros(n,dtype=np.int64);self.steps=np.zeros(n,dtype=np.int64)
        self.from_bank=np.zeros(n,dtype=bool);self.records={};self.seen=np.zeros(16,dtype=np.int64)
        self.bank_restores=0;self.saved=0
        self.rng=np.random.default_rng(seed);self.perturb=[None]*n
        self.history=np.zeros((n,self.width*5),dtype=np.float64)
        for i in range(n):self.reset(i)
        self.cuda_history=torch.as_tensor(self.history.copy(),device='cuda')

    def frames(self):
        x=self.env.preview() if self.use_preview else self.env.observations.copy()
        x[:,13:15]=0.;return x

    def reset(self,i):
        episode=int(self.episodes[i]);self.episodes[i]+=1
        seed=(self.seed*1000003+i*10007+episode*31337)%4294967295
        rng=np.random.default_rng(seed)
        bank_rng=np.random.default_rng(seed^0x5097)
        if self.records and bank_rng.random()<self.bank_fraction:
            bins=sorted({slot//16 for slot in self.records})
            group=int(bank_rng.choice(bins));slot=int(bank_rng.choice([s for s in self.records if s//16==group]))
            self.env.restore_checkpoint(i,slot,int(seed));self.history[i]=self.records[slot].copy()
            self.from_bank[i]=True;self.bank_restores+=1
        else:
            self.env.reset(i,int(seed))
            x=self.env.preview_one(i) if self.use_preview else self.env.observations[i].copy();x[13:15]=0.
            self.history[i]=np.tile(x,5);self.from_bank[i]=False
        self.steps[i]=0
        self.perturb[i]={'warm':int(rng.integers(0,101)),'duration':int(rng.integers(1,6)),
                         'steerKick':float(rng.uniform(-.12,.12)) if rng.random()<.1 else 0.}

    def remember(self,i):
        state=self.env.states[i]
        # Reservoirs stratified by two seconds of game time prevent a tail-only
        # curriculum. Only full-start rollouts supply checkpoints: no nesting.
        if self.bank_fraction<=0 or self.from_bank[i] or state.terminated or state.truncated or state.tick<100 or state.speed<10:return
        if self.steps[i]%20:return
        group=min(15,int(state.tick)//200);self.seen[group]+=1
        rank=int(self.rng.integers(int(self.seen[group])))
        if rank>=self.snapshots_per_bin:return
        slot=group*16+rank;self.env.save_checkpoint(i,slot)
        self.records[slot]=self.history[i].copy();self.saved+=1

    def step(self,actions):
        controls=actions.copy()
        for i,c in enumerate(self.perturb):
            if c['warm']<=self.steps[i]<c['warm']+c['duration']:controls[i,2]=np.clip(controls[i,2]+c['steerKick'],-1,1)
        self.env.step(quantized(controls));self.steps+=1
        reward=np.array([s.reward for s in self.env.states[:self.n]])*.01
        done=np.array([bool(s.terminated or s.truncated) for s in self.env.states[:self.n]])
        next_frame=self.frames()
        self.history[:,:-self.width]=self.history[:,self.width:];self.history[:,-self.width:]=next_frame
        for i in range(self.n):self.remember(i)
        self.cuda_history=torch.cat((self.cuda_history[:,self.width:],torch.as_tensor(next_frame,device='cuda')),1)
        indices=np.flatnonzero(done)
        for i in indices:self.reset(int(i))
        if len(indices):self.cuda_history[torch.as_tensor(indices,device='cuda')]=torch.as_tensor(self.history[indices],device='cuda')
        return reward,done


@torch.no_grad()
def evaluate(model,env,cases,preview=True):
    for i,c in enumerate(cases):env.reset(i,c['seed'])
    def frames():
        x=env.preview() if preview else env.observations.copy();x[:,13:15]=0.;return x
    width=72 if preview else 48;history=np.tile(frames(),(1,5));active=np.ones(env.n,dtype=bool)
    for step in range(800):
        if not active.any():break
        out=model.actor(torch.as_tensor(history,device='cuda'))
        actions=torch.cat(((out[:,:2]>=0).double(),out[:,2:3].tanh()),1).cpu().numpy()
        for i,c in enumerate(cases):
            if c['warm']<=step<c['warm']+c['duration']:actions[i,2]=np.clip(actions[i,2]+c['steerKick'],-1,1)
        env.step(quantized(actions));history[:,:-width]=history[:,width:];history[:,-width:]=frames()
        active=np.array([not(s.terminated or s.truncated) for s in env.states[:env.n]])
    from robust_ppo import summarize_trials
    trials=[dict(c,finishMs=int(s.finish_ms) if s.finish_ms>=0 else None,
                 checkpoints=int(s.checkpoints)) for c,s in zip(cases,env.states[:env.n])]
    return dict(summarize_trials(trials),trials=trials)
