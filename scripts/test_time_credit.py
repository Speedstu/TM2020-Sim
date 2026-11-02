#!/usr/bin/env python3
"""Reward invariants, episodic credit, and historical CUDA update equivalence."""
import copy
from pathlib import Path
import unittest
import numpy as np
import torch
from compare_hybrid_ppo import Policy, update as historical_update
from ppo_time_credit import potential, shape_reward, gae, update
from gpu_ppo import Checkpoint, Helpers
from run_fast_ppo import ROOT


class TimeCreditTests(unittest.TestCase):
    def test_shaping_cannot_reward_stalling_or_loops(self):
        for seconds,finish in [(22.,True),(25.,True),(4.,False),(40.,False)]:
            rng=np.random.default_rng(47901)
            observation=rng.uniform(-4,4,(400,48))
            phis=potential(observation)
            raw=np.full(399,-seconds/399*.01)
            raw[-1]+=(100. if finish else -100.-(40.-seconds))*.01
            done=np.zeros(399,dtype=bool);done[-1]=True
            shaped=shape_reward(raw,phis[:-1],phis[1:],done)
            self.assertAlmostEqual(float(shaped.sum()+.01*phis[0]),float(raw.sum()),places=12)
            self.assertAlmostEqual(float(raw.sum()),(100.-seconds)*.01 if finish else -1.4,places=12)
        # Arbitrary back-and-forth distance changes have no net reward gain.
        self.assertAlmostEqual(float(shape_reward(np.array([-.01,-.01]),
                                                 np.array([-5.,-1.]),np.array([-1.,-5.]),
                                                 np.array([False,False])).sum()),-.02)

    def test_full_credit_and_terminal_boundaries(self):
        reward=torch.tensor([[1.,4.],[2.,5.],[3.,6.]],dtype=torch.float64)
        done=torch.tensor([[False,True],[True,False],[False,True]])
        values=torch.tensor([[.2,.3],[.4,.5],[.6,.7]],dtype=torch.float64)
        boot=torch.tensor([8.,9.],dtype=torch.float64)
        _,target=gae(reward,done,values,boot,1.)
        torch.testing.assert_close(target,torch.tensor([[3.,4.],[2.,11.],[11.,6.]],dtype=torch.float64),rtol=0,atol=1e-14)
        steps=480
        rewards=torch.zeros((steps,1),dtype=torch.float64);rewards[-1]=1.
        endings=torch.zeros_like(rewards,dtype=torch.bool);endings[-1]=True
        values=torch.zeros_like(rewards);boot=torch.zeros(1,dtype=torch.float64)
        short,_=gae(rewards,endings,values,boot,.995)
        full,_=gae(rewards,endings,values,boot,1.)
        self.assertLess(short[0].item(),.1)
        self.assertEqual(full[0].item(),1.)

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA not available')
    def test_default_update_is_bit_identical_to_historical(self):
        torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
        prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',Helpers())
        torch.manual_seed(47901);a=Policy(prior,'continuous');b=copy.deepcopy(a)
        def optimizer(model):
            return torch.optim.Adam(model.parameters(),lr=3e-7,eps=1e-8)
        class Episodes:
            def __init__(self):
                self.n=4;self.t=0;self.history=np.zeros((4,240))
            def step(self,actions):
                self.t+=1
                self.history[:]=np.sin(self.t*.1)*.01
                return np.full(4,-.0005),np.array([self.t%5==0,self.t%7==0,False,self.t%3==0])
        oa=optimizer(a);ob=optimizer(b);rng=torch.cuda.get_rng_state()
        historical_update(a,Episodes(),oa,16)
        torch.cuda.set_rng_state(rng);update(b,Episodes(),ob,16,gae_lambda=.995)
        for name,p in a.state_dict().items():
            self.assertTrue(torch.equal(p,b.state_dict()[name]),name)


if __name__=='__main__':unittest.main()
