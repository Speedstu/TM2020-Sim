#!/usr/bin/env python3
"""Compare simulated applied commands to a saved real physics-consumer trace.

Recorded controls are replayed without state correction. This tests dynamics /
actuation semantics, not an autonomous policy's finish rate.
"""
import argparse
import csv
import ctypes as C
import json
from pathlib import Path
import numpy as np
from run_fast_ppo import ROOT
from vector_physics import VectorPhysics
from prepare_fall_campaign import save_json

API=ROOT/'native/build-internal-0.54/libtm2020_vector_physics.so'
LIB=ROOT/'cache/internal-control-0.54-target/release/libtm2020_speed.so'
FIELDS=('r00','r01','r02','r10','r11','r12','r20','r21','r22','x','y','z','qw','qx','qy','qz','vx','vy','vz','wx','wy','wz')


def compare(trace,internal,seed,*,map_path=None,max_ms=None,launch_delta=None):
    rows={};race_start=None
    for r in csv.DictReader(Path(trace).open()):
        if not int(r['wrote']) or int(r['fault'])!=0:continue
        start=int(r['race_start_ms']);ms=int(r['tick_ms'])-start
        if ms<0:continue
        if race_start is None:race_start=start
        if start!=race_start:continue # Never splice together different resets.
        if max_ms is None or ms<=max_ms:rows.setdefault(ms,r)
    if not rows or 0 not in rows:raise ValueError('Trace must start at race zero')
    errors=[]
    with VectorPhysics(1,decision_ticks=1,api_path=API,library=LIB,map_path=map_path,internal_controls=internal) as env:
        if launch_delta is not None:
            value=np.asarray([launch_delta],dtype=np.float32)
            env.api.tmvec_launch_uncertainty.argtypes=[C.c_void_p,C.POINTER(C.c_float)]
            env.check(env.api.tmvec_launch_uncertainty(env.handle,value.ctypes.data_as(C.POINTER(C.c_float))))
        env.reset(0,seed)
        sim=C.CDLL(str(LIB));sim.tmfast_input_adjustments.argtypes=[C.c_void_p];sim.tmfast_input_adjustments.restype=C.c_uint32
        for tick in range(max(rows)//10+1):
            ms=tick*10
            if ms not in rows:break
            r=rows[ms];actual=np.array([float(r[k]) for k in FIELDS],dtype=np.float32)
            predicted=np.array(env.states[0].rigid_words,dtype=np.uint32).view(np.float32)
            difference=predicted.astype(np.float64)-actual
            errors.append({'ms':ms,'positionErrorM':float(np.linalg.norm(difference[9:12])),
                'velocityErrorMps':float(np.linalg.norm(difference[16:19])),
                'rotationMaxError':float(np.max(np.abs(difference[:9]))),
                'gameVelocity':actual[16:19].tolist(),'simVelocity':predicted[16:19].tolist()})
            if env.states[0].terminated or env.states[0].truncated:break
            env.step([[float(r[k]) for k in ('gas','brake','steer')]])
        result={'mode':'internal_frozen_input_history' if internal else 'legacy_device_input_history',
            'seed':seed,'stepsCompared':len(errors),'finishMs':int(env.states[0].finish_ms),
            'simulatorOnlyLaunchDeltaMps':launch_delta,
            'raceStartMs':race_start,'map':str(env.map),'firstPositionErrorOver1mm':next((e for e in errors if e['positionErrorM']>.001),None),
            'firstVelocityErrorOver1mmps':next((e for e in errors if e['velocityErrorMps']>.001),None),
            'meanPositionErrorM':float(np.mean([e['positionErrorM'] for e in errors])),
            'maxPositionErrorM':max(e['positionErrorM'] for e in errors),
            'samples':[e for e in errors if e['ms']<100 or e['ms']%1000==0]+errors[-1:],
            'recordedActionsOnly':True,'autonomousPolicyQualified':False}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,default=ROOT/'local/recon/campaign-fall01-user/attempt-001/control/physics.csv')
    p.add_argument('--map',type=Path);p.add_argument('--max-ms',type=int)
    p.add_argument('--seed',type=int,default=36139877)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    results=[compare(a.trace,False,a.seed,map_path=a.map,max_ms=a.max_ms),compare(a.trace,True,a.seed,map_path=a.map,max_ms=a.max_ms)]
    save_json(a.output,{'trace':str(a.trace),'results':results,'gameAccessed':False})
    print(json.dumps([{k:v for k,v in r.items() if k!='samples'} for r in results]),flush=True)


if __name__=='__main__':main()
