#!/usr/bin/env python3
"""Explicit Fall01 specialization: both public fast references use full gas.

Same 72-input internal policy, with gas/brake fixed by its exported neural head.
This profile is deliberately not a general-purpose policy for other maps.
"""
import hashlib
import math
from pathlib import Path
import signal
import numpy as np
import torch
import torch.nn.functional as F
import train_adaptive_ppo as runner
from preview_ppo import PreviewPolicy


class SpecialistPolicy(PreviewPolicy):
    def __init__(self,prior,source):
        super().__init__(prior,source,pedal_temperature=1.)
        with torch.no_grad():
            self.actor[2].weight[:2].zero_()
            self.actor[2].bias[:2].copy_(torch.tensor([16.,-16.],device='cuda',dtype=torch.float64))

    def action(self,x,deterministic=False):
        mean=self.actor(x)[:,2]
        z=mean if deterministic else mean+torch.randn_like(mean)*self.logstd.exp()
        pedals=torch.stack((torch.ones_like(z),torch.zeros_like(z)),1)
        return (torch.cat((pedals,z.tanh()[:,None]),1),torch.cat((pedals,z[:,None]),1),
                self.steering_logp(mean,z),self.critic(x).flatten())

    def steering_logp(self,mean,z):
        jac=2*(math.log(2)-z-F.softplus(-2*z))
        return -.5*((z-mean)*torch.exp(-self.logstd)).square()-.5*math.log(2*math.pi)-self.logstd-jac

    def logp(self,x,stored):return self.steering_logp(self.actor(x)[:,2],stored[:,2])


def main():
    profile={'preview':True,'bank':.5,'temperature':1.,'sigma':.05,'fixedPedals':[1,0],
             'scope':'Fall01 only; both WR and tenth-place references have no brake/gas-off ticks',
             'adapterSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    runner.PROFILES['specialist']=profile
    original=runner.make_model
    def make_model(prior,source,config):
        if 'fixedPedals' not in config:return original(prior,source,config)
        model=SpecialistPolicy(prior,source)
        with torch.no_grad():model.logstd.fill_(np.log(config['sigma']))
        return model
    runner.make_model=make_model
    signal.signal(signal.SIGTERM,runner.stop);signal.signal(signal.SIGINT,runner.stop);runner.main()


if __name__=='__main__':main()
