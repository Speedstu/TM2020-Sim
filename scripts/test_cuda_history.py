#!/usr/bin/env python3
"""Bit-exact native simulator + CUDA-frame history parity test."""
import os
import numpy as np
import torch
from compare_hybrid_ppo import Episodes
from cuda_history import CudaHistoryEpisodes

def main():
    os.environ['TM2020_PHYSICS_WORKERS']='8'
    normal=Episodes(16,73302)
    gpu=CudaHistoryEpisodes(16,73302)
    rng=np.random.default_rng(1777)
    try:
        for t in range(75):
            action=np.column_stack((rng.integers(0,2,16),
                                    rng.integers(0,2,16),rng.uniform(-1,1,16)))
            (reward_a,done_a)=normal.step(action)
            (reward_b,done_b)=gpu.step(action)
            assert np.array_equal(reward_a,reward_b),(t,'reward')
            assert np.array_equal(done_a,done_b),(t,'done')
            assert np.array_equal(normal.steps,gpu.steps),(t,'steps')
            history=gpu.cuda_history.cpu().numpy()
            assert np.array_equal(normal.history,history),(
                t,'history',float(np.max(np.abs(normal.history-history))))
        print('PASS: 75 steps x 16 envs; identical rewards, resets, done states and 240-feature histories')
    finally:
        normal.env.close();gpu.env.close()
if __name__=='__main__':main()
