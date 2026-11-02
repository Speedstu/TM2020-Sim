#!/usr/bin/env python3
"""Matched full-state parity and wall-clock benchmark; no client access."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import statistics
import time
import numpy as np
from hybrid_tracking import load_asset,save_asset,asset_checksum
from tune_hybrid_tracking import NativeEvaluator
from optimize_fall_campaign import trial_cases
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def python_checksum(data):
    value=14695981039346656037
    for b in data:value=((value^b)*1099511628211)&((1<<64)-1)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--map-index',type=int,default=2);p.add_argument('--workers',type=int,default=6)
    p.add_argument('--repeats',type=int,default=3);a=p.parse_args();a.output.mkdir(exist_ok=True,parents=True)
    os.environ['TM2020_PHYSICS_WORKERS']=str(a.workers)
    source=ROOT/f'local/training/fall-campaign-internal-0.55/{a.map_index:02d}'
    m=json.loads((source/'map.json').read_text());model=source/'best.tmhyb'
    ref,g,net=load_asset(model,map_path=m['map'],uid=m['mapUid'])
    assets=[]
    for i in range(16):
        r=ref.copy();r[:,24]=np.clip(r[:,24]+(i%4-1.5)*.002,-1,1)
        r[:,24]=np.round(r[:,24]*127)/127
        path=a.output/f'asset-{i}.tmhyb';save_asset(path,r,g,net,map_path=m['map'],uid=m['mapUid']);assets.extend([path]*4)
    cases=trial_cases(58001,64,len(ref),True)
    # Early and mid-lap disturbances, mixed lengths, different assets per case.
    cases[0].update(kick=0.);cases[1].update(warm=0,duration=7,kick=.1)
    timings={'baseline':[],'fast':[]};parity=True
    api=ROOT/'native/build-speed-0.58/libtm2020_vector_physics.so'
    physics=ROOT/'local/training/fall-campaign-world-records-0.57/frozen/native/libtm2020_speed.so'
    env=NativeEvaluator(64,model,api_path=api,map_path=m['map'],horizon=len(ref)+1000,library=physics,internal_controls=True)
    try:
        for repeat in range(a.repeats+1):
            snapshots={};rows_by_mode={}
            order=('baseline','fast') if repeat%2==0 else ('fast','baseline')
            for mode in order:
                env.fast_evaluation=mode=='fast';rows,seconds=env.evaluate(g,cases,assets=assets)
                snapshots[mode]=C.string_at(env.env.states,64*C.sizeof(env.env.states[0]));rows_by_mode[mode]=rows
                if repeat:timings[mode].append(seconds)
            if snapshots['baseline']!=snapshots['fast'] or rows_by_mode['baseline']!=rows_by_mode['fast']:
                raise RuntimeError('Fast whole-race evaluation changed complete physical output bytes')
        ticks=sum(r['tick'] for r in rows_by_mode['fast'])
        baseline=statistics.median(timings['baseline']);fast=statistics.median(timings['fast'])
    finally:env.close()
    data=model.read_bytes();start=time.perf_counter();expected=python_checksum(data);python_sec=time.perf_counter()-start
    start=time.perf_counter();actual=asset_checksum(data);native_sec=time.perf_counter()-start
    assert expected==actual
    result={'mapIndex':a.map_index,'workers':a.workers,'cases':64,'repeats':a.repeats,
        'completeOutputByteParity':parity,'timingsSeconds':timings,'baselineMedianSeconds':baseline,
        'fastMedianSeconds':fast,'nativeSpeedup':baseline/fast,'simulatedTicks':ticks,
        'baselineStepsPerSecond':ticks/baseline,'fastStepsPerSecond':ticks/fast,
        'checksumEqual':True,'pythonChecksumSeconds':python_sec,'nativeChecksumSeconds':native_sec,
        'apiSha256':hashlib.sha256(api.read_bytes()).hexdigest(),
        'physicsSha256':hashlib.sha256(physics.read_bytes()).hexdigest(),'gameAccessed':False}
    save_json(a.output/'report.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
