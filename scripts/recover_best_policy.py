#!/usr/bin/env python3
"""Restore the champion actor while retaining the latest learned value network."""
import argparse
from pathlib import Path
import numpy as np
from gpu_ppo import Helpers,Checkpoint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--best',type=Path,required=True);p.add_argument('--latest',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();h=Helpers()
    best=Checkpoint.load(a.best,h);latest=Checkpoint.load(a.latest,h)
    if (best.nx,best.na,best.hidden,best.schema)!=(latest.nx,latest.na,latest.hidden,latest.schema):raise ValueError('Recovery architectures differ')
    # The actor is rolled back, but value learning must continue even when a
    # cycle has no champion. Reset Adam for the combined networks: their
    # moments came from different parameter histories and share one step.
    critic=slice(best.actor_count,best.actor_count+best.critic_count)
    best.parameters[critic]=latest.parameters[critic]
    best.first.fill(0.);best.second.fill(0.);best.step=0
    best.shuffle=latest.shuffle;best.sampler=latest.sampler;best.save(a.output,h)
    recovered=Checkpoint.load(a.output,h)
    assert np.array_equal(recovered.parameters,best.parameters) and np.array_equal(recovered.first,best.first) and np.array_equal(recovered.second,best.second)
    assert recovered.step==best.step and recovered.sampler==latest.sampler and recovered.shuffle==latest.shuffle
    assert np.array_equal(recovered.parameters[critic],latest.parameters[critic])

if __name__=='__main__':main()
