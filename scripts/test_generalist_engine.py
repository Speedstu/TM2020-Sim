#!/usr/bin/env python3
"""Physics isolation, exact shared perception, invalid-input and horizon checks."""
import argparse
import ctypes as C
import json
from pathlib import Path
from generalist_engine import GeneralistEngine


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library',type=Path,required=True);p.add_argument('--map',type=Path,required=True)
    p.add_argument('--packs',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    result={}
    with GeneralistEngine(a.library,a.map,a.packs,horizon=503) as e:
        minimum_time=hasattr(e.lib,'tmgen_reward_version') and e.lib.tmgen_reward_version()>=2
        initial=tuple(e.reset().observation);raw=e.raw()
        assert initial==e.observe(raw,True)
        with GeneralistEngine(a.library,clone=e) as copy:
            copy.step([1,-1,.2],5);assert e.raw()==raw
        result['independentClone']=True
        for step in range(100):
            state=e.step([1,-1,.1],5);before=e.raw()
            expected=tuple(state.observation);actual=e.observe(before)
            assert expected==actual and e.raw()==before
        result['exactSharedPerceptionTransitions']=100
        before=e.raw();expected=e.observe(before)
        for index,value in [(0,float('nan')),(3,2.),(14,float('inf'))]:
            invalid=list(before);invalid[index]=value
            try:e.observe(invalid)
            except RuntimeError:pass
            else:raise AssertionError('invalid telemetry accepted')
            assert e.raw()==before and e.observe(before)==expected
        result['invalidTelemetryDoesNotChangePhysicsOrTracker']=True
        try:e.step([float('nan'),0,0],5)
        except RuntimeError:pass
        else:raise AssertionError('NaN action accepted')
        assert e.raw()==before
        state=e.step([1,-1,0],5)
        assert state.advanced_ticks==3 and state.tick==503
        assert (bool(state.terminated),bool(state.truncated))==((True,False) if minimum_time else (False,True))
        result['partialHorizonUsesActualDuration']=True
        try:e.step([1,-1,0],5)
        except RuntimeError:pass
        else:raise AssertionError('step after horizon accepted')
        assert tuple(e.reset().observation)==initial
        result['completeResetExact']=True
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
