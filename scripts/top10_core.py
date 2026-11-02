"""100 Hz map-relative policy, real-world snapshot curriculum and race evaluation."""
import math
import numpy as np
import torch
from compare_hybrid_ppo import frame, quantized
from cuda_history import CudaHistoryEpisodes
from vector_physics import VectorPhysics
from run_fast_ppo import ROOT

DIRECTORY=ROOT/'local/training/top10-20261030'
API=DIRECTORY/'native/libtm2020_vector_physics.so'
CURRICULUM=ROOT/'cache/curriculum-training-target/release/libtm2020_curriculum.so'
REFERENCE=DIRECTORY/'wr-reference.Ghost.Gbx'


def histories(rows):
    x=frame(rows[:,:48]);return np.concatenate([x[np.maximum(0,np.arange(len(x))-lag)] for lag in (4,3,2,1,0)],axis=1)


@torch.no_grad()
def actions(model,history,quantize=True):
    out=model.actor(torch.as_tensor(history,device='cuda'))
    control=torch.cat(((out[:,:2]>=0).double(),out[:,2:3].tanh()),1).cpu().numpy()
    return quantized(control) if quantize else control


@torch.no_grad()
def evaluate(model,env,seeds,perturbations=None):
    assert env.n==len(seeds) and env.decision_ticks in (1,5)
    if perturbations is not None and len(perturbations)!=env.n:raise ValueError('One disturbance per evaluation world required')
    for i,seed in enumerate(seeds):env.reset(i,int(seed))
    history=np.tile(frame(env.observations),(1,5));active=np.ones(env.n,dtype=bool)
    for step in range(4000//env.decision_ticks):
        if not active.any():break
        control=actions(model,history,quantize=False)
        if perturbations is not None:
            for i,c in enumerate(perturbations):
                if c['warmMs']<=step*env.decision_ticks*10<c['warmMs']+c['durationMs']:
                    control[i,2]=np.clip(control[i,2]+c['steerKick'],-1,1)
        env.step(quantized(control))
        history[:,:-48]=history[:,48:];history[:,-48:]=frame(env.observations)
        active=np.array([not(s.terminated or s.truncated) for s in env.states[:env.n]])
    trials=[{'seed':int(seed),'finishMs':int(s.finish_ms) if s.finish_ms>=0 else None,
             'checkpoints':int(s.checkpoints),'physicsTicks':int(s.tick)} for seed,s in zip(seeds,env.states[:env.n])]
    times=[t['finishMs'] for t in trials if t['finishMs'] is not None]
    penalized=[t['finishMs'] if t['finishMs'] is not None else 40000 for t in trials]
    return {'finishes':len(times),'count':len(seeds),'meanMs':float(np.mean(times)) if times else None,
            'medianMs':float(np.median(times)) if times else None,'bestMs':min(times) if times else None,
            'penalizedMeanMs':float(np.mean(penalized)),'trials':trials,'measuredInGame':False}


def score(result):
    # Reliability first; no faster subset may displace a model that finishes more races.
    return (result['finishes'],-result['penalizedMeanMs'],
            sum(t['checkpoints'] for t in result['trials']))


class BankEpisodes(CudaHistoryEpisodes):
    def __init__(self,n,seed,bank_fraction=.7,bank_min=1,decision_ticks=1):
        self.bank_fraction=bank_fraction
        self.bank_min=bank_min
        self.active_banks=[None]*n
        self.section_results=[]
        self.reference=np.load(DIRECTORY/'wr-100hz-demonstration.npy')[:,48:51]
        self.bank_resets=0
        physics=VectorPhysics(n,decision_ticks=decision_ticks,api_path=API,library=CURRICULUM,replay=REFERENCE)
        if physics.banks<2:physics.close();raise RuntimeError('Complete reference snapshot banks unavailable')
        self.bank_min=max(1,min(self.bank_min,physics.banks-1))
        super().__init__(n,seed,physics=physics)

    def reset(self,i):
        if self.active_banks[i] is not None and self.active_banks[i]>0:
            state=self.env.states[i]
            if state.terminated or state.truncated:
                self.section_results.append(bool(0<=state.finish_ms<=21000));self.section_results=self.section_results[-128:]
        episode=int(self.episodes[i]);self.episodes[i]+=1
        seed=(self.seed*1000003+i*10007+episode*31337)%4294967295
        rng=np.random.default_rng(seed)
        bank=int(rng.integers(self.bank_min,self.env.banks)) if rng.random()<self.bank_fraction else 0
        self.active_banks[i]=bank
        self.env.reset_bank(i,int(seed),bank)
        self.history[i]=np.tile(frame(self.env.observations[i:i+1])[0],5)
        if bank:
            self.bank_resets+=1
            # Warm only this clone for four real decision periods. No fabricated history,
            # and no accidental advancement of the other vector environments.
            for _ in range(4):
                for _ in range(self.env.decision_ticks):
                    tick=int(self.env.states[i].tick)
                    self.env.step_one(i,self.reference[min(tick,len(self.reference)-1)])
                self.history[i,:-48]=self.history[i,48:];self.history[i,-48:]=frame(self.env.observations[i:i+1])[0]
        self.steps[i]=0
        # Mild, short training disturbance; amplitudes/period are explicit.
        self.perturb[i]={'warm':int(rng.integers(0,101)),'duration':int(rng.integers(1,11)),
                         'steerKick':float(rng.uniform(-.12,.12)) if rng.random()<.1 else 0.}

    def step(self,controls):
        reward,done=super().step(controls)
        if done.any():
            indices=np.flatnonzero(done)
            self.cuda_history[torch.as_tensor(indices,device='cuda')]=torch.as_tensor(self.history[indices],device='cuda')
        return reward,done
