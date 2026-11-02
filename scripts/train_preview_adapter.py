#!/usr/bin/env python3
"""Learn new preview inputs while retaining all original actor coefficients."""
import hashlib
from pathlib import Path
import signal
import torch
import train_adaptive_ppo as runner
from preview_ppo import PreviewPolicy


def main():
    config={'preview':True,'bank':.25,'temperature':.5,'freezeOriginalActor':True,
            'adapterSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    runner.PROFILES['preview-adapter']=config
    original=runner.make_model
    def make_model(prior,source,profile):
        if not profile.get('freezeOriginalActor'):return original(prior,source,profile)
        model=PreviewPolicy(prior,source,pedal_temperature=profile['temperature'])
        mask=torch.zeros_like(model.actor[0].weight)
        for f in range(5):mask[:,f*72+48:(f+1)*72]=1.
        model.actor[0].weight.register_hook(lambda gradient:gradient*mask)
        model.actor[0].bias.requires_grad_(False)
        for p in model.actor[2].parameters():p.requires_grad_(False)
        return model
    runner.make_model=make_model
    signal.signal(signal.SIGTERM,runner.stop);signal.signal(signal.SIGINT,runner.stop);runner.main()


if __name__=='__main__':main()
