#!/usr/bin/env python3
"""Independently replay native vector PPO collection on the correct map per env."""
import argparse
import ctypes as C
import csv
import hashlib
import json
import math
from pathlib import Path
from fast_engine import State48
from generalist_engine import GeneralistEngine
from owned_ppo import OwnedPolicy
from run_fast_ppo import steam_packs

class Row(C.Structure):
    _fields_=[('env',C.c_uint32),('episode',C.c_uint32),('bank',C.c_uint32),('reserved',C.c_uint32),
              ('before',State48),('after',State48),('action',C.c_double*3)]
assert C.sizeof(Row)==1128

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--packs',type=Path)
    p.add_argument('--environments',help='Optional comma-separated environment indices; default audits all')
    a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    a.output.mkdir(parents=True);config=json.loads((a.run/'config.json').read_text())
    maps=(a.run/'maps.txt').read_text().splitlines();folder=a.run/'update-0';data=(folder/'physics.bin').read_bytes()
    assert data[:8]==b'TMFAST03' and (len(data)-8)%C.sizeof(Row)==0
    events=[Row.from_buffer_copy(data,k) for k in range(8,len(data),C.sizeof(Row))]
    selected = {int(x) for x in a.environments.split(',')} if a.environments else None
    if selected is not None:
        assert selected and selected <= {r.env for r in events}, 'unknown environment index'
    policy=OwnedPolicy(Path(__file__).resolve().parents[1]/'native/build-linux/libtm2020_policy.so',folder/'behavior.tmppo',config['schema'],48,3)
    environments={};roots={};episodes={};count=0;ticks=0;max_observation_error=0.
    try:
        for row in events:
            if selected is not None and row.env not in selected:
                continue
            assert row.bank==0 and row.reserved==0
            if row.env not in environments:
                key=row.env%len(maps)
                if key not in roots:
                    roots[key]=GeneralistEngine(config['library'],maps[key],a.packs or steam_packs(),config['horizon'])
                environments[row.env]=GeneralistEngine(config['library'],clone=roots[key])
            e=environments[row.env]
            if episodes.get(row.env)!=row.episode:
                e.reset(config['seed']+row.env+row.episode*config['environments']);episodes[row.env]=row.episode
            assert bytes(e.state)==bytes(row.before),(row.env,count,'before state mismatch')
            result=e.step(row.action,config['repeat'])
            assert bytes(result)==bytes(row.after),(row.env,count,'after state mismatch')
            ticks+=result.advanced_ticks;count+=1
        samples=list(csv.DictReader((folder/'rollout.csv').open()));assert len(samples)==len(events)
        for i,row in enumerate(samples):
            x=[float(row[f'observation_{k}']) for k in range(48)]
            _,value=policy.predict(x);assert abs(value-float(row['old_value']))<1e-10
            assert abs(float(row['reward'])-events[i].after.reward*.01)<1e-12
        report={'physicallyReplayedTransitions':count,'physicsTicks':ticks,'physicallyReplayedMaps':len(roots),
                'behaviorValuesChecked':len(samples),'mapsInTrainingRun':len(maps),'rigidStateControlsFeaturesRewardReplayExact':True,
                'behaviorValuesMatch':True,'physicsSha256':hashlib.sha256(data).hexdigest(),
                'originalClientFullPhysicsParityClaimed':False}
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:
        policy.close()
        for e in environments.values():e.close()
        for e in roots.values():e.close()

if __name__=='__main__':main()
