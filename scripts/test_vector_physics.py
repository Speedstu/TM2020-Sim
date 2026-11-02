#!/usr/bin/env python3
"""Byte parity with individual physics, reset isolation, and input rejection."""
import numpy as np
from vector_physics import VectorPhysics
from generalist_engine import GeneralistEngine
from run_fast_ppo import steam_packs

def main():
    for n in (1,4,17):
        with VectorPhysics(n) as batch,GeneralistEngine(batch.library,batch.map,steam_packs(),horizon=4000) as single:
            for i in range(n):batch.reset(i,46100+i)
            single.reset(46100);rng=np.random.default_rng(46100)
            for t in range(100):
                controls=np.zeros((n,3),dtype=np.float32);controls[:,0]=1
                controls[:,2]=rng.integers(-64,65,size=n)/127.
                batch.step(controls);individual=single.step_controls(controls[0])
                assert bytes(batch.states[0])==bytes(individual),(n,t)
            if n>1:
                untouched=bytes(batch.states[0]);batch.reset(n-1,99)
                assert bytes(batch.states[0])==untouched,'Reset changed another clone'
            before=bytes(batch.states[0])
            try:batch.step(np.full((n,3),np.nan));raise AssertionError('Nonfinite batch accepted')
            except ValueError:pass
            assert bytes(batch.states[0])==before,'Rejected batch advanced physics'
            print(f'PASS vector n={n}: 100 byte-identical transitions, reset isolation, rejected actions do not step')
if __name__=='__main__':main()
