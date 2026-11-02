#!/usr/bin/env python3
"""CUDA-resident five-frame PPO observation history with native CPU physics.

Only the 48 new observation features/env per step cross CPU->CUDA, rather than
all 240 historical features. Physics stays in qualified native CPU code.
"""
import numpy as np
import torch
from compare_hybrid_ppo import Episodes, frame, quantized

class CudaHistoryEpisodes(Episodes):
    def __init__(self,n,seed,physics=None):
        super().__init__(n,seed,physics=physics)
        self.cuda_history=torch.as_tensor(self.history.copy(),device='cuda')

    def step(self,actions):
        controls=actions.copy()
        for i,c in enumerate(self.perturb):
            if c['warm'] <= self.steps[i] < c['warm']+c['duration']:
                controls[i,2]=np.clip(controls[i,2]+c['steerKick'],-1,1)
        self.env.step(quantized(controls))
        self.steps+=1
        reward=np.array([s.reward for s in self.env.states[:self.n]])*.01
        done=np.array([bool(s.terminated or s.truncated) for s in self.env.states[:self.n]])
        for i in np.flatnonzero(done):
            self.reset(int(i))
        # The simulator only emits new 48-feature frames. Retain the history
        # in GPU memory; detach from prior rollout references via torch.cat.
        next_frame=torch.as_tensor(frame(self.env.observations.copy()),device='cuda')
        self.cuda_history=torch.cat((self.cuda_history[:,48:],next_frame),dim=1)
        if done.any():
            idx=torch.as_tensor(np.flatnonzero(done),device='cuda')
            self.cuda_history[idx]=next_frame[idx].repeat(1,5)
        return reward,done
