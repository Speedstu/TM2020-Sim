#!/usr/bin/env python3
"""Owned decoder/consumer sweep, independent bitstream decode and physics replay.

The envelope is an explicit owned test format, never a fabricated client GBX.
"""
import argparse,csv,json,subprocess
from pathlib import Path
import numpy as np
from vector_physics import VectorPhysics
from prepare_fall_campaign import ROOT,save_json


def encode_owned(actions):
    bits=[]
    def number(value,n):bits.extend((value>>i)&1 for i in range(n))
    previous=None
    for i,a in enumerate(actions):
        if i==0:number(0,1);number(0,1);number(2,34)
        else:number(1,1)
        number(1,1) # no extra state word
        current=(int(round(a[2]*127)),int(a[0]),int(a[1]))
        same=current==previous;number(int(same),1)
        if not same:number(current[0]&255,8);number(current[1],1);number(current[2],1)
        previous=current
    data=bytearray((len(bits)+7)//8)
    for k,b in enumerate(bits):data[k//8]|=b<<(k%8)
    return {'kind':'owned-input-capture','ticks':len(actions),'data':list(data),'clientReplay':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--owned',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=list(csv.DictReader((a.owned/'owned-pipeline.args.causal.csv').open()))
    source={int(r['tick_ms']):r for r in rows if r['input_stage']=='1' and int(r['tick_ms'])<1000}
    physical={int(r['tick_ms']):r for r in rows if r['input_stage']=='0' and int(r['tick_ms'])<1000}
    if sorted(source)!=list(range(0,1000,10)) or source.keys()!=physical.keys():raise RuntimeError('Missing causal ticks')
    actions=[]
    for t,r in sorted(source.items()):
        cmd=np.array([float(r['record_'+k]) for k in ('gas','brake','steer')],dtype=np.float32);f=physical[t]
        if f['consumer_verified']!='1' or f['physical_write']!='0' or r['physical_write']!='0':raise RuntimeError('Physical overwrite masks the decoder')
        if not np.array_equal(cmd,np.array([float(f[k+'_before']) for k in ('gas','brake','steer')],dtype=np.float32)):raise RuntimeError('Source and original consumer differ')
        actions.append(cmd)
    actions=np.asarray(actions);a.output.mkdir(exist_ok=True,parents=True)
    envelope=a.output/'owned.inputstream.json';save_json(envelope,encode_owned(actions))
    decoder=ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'
    decoded=json.loads(subprocess.check_output([str(decoder),'decode-owned',str(envelope)],text=True))
    if decoded['decoded']['truncated_at'] is not None:raise RuntimeError('Truncated roundtrip')
    restored=np.array([[float(t['gas']),float(t['brake']),max(-1,t['steer']/127)] for t in decoded['decoded']['ticks']],dtype=np.float32)
    if not np.array_equal(restored,actions):raise RuntimeError('Independent Rust input decoder changed the commands')
    native=ROOT/'local/training/human-rework-0.70/frozen/native-43ca3da0f65b3be1ddc1'
    with VectorPhysics(2,decision_ticks=1,api_path=native/'libtm2020_vector_physics.so',
        library=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so',normal_inputs=True) as env:
        for i in range(2):env.reset(i,700031)
        matches=0
        for original,replayed in zip(actions,restored):
            env.step(np.array([original,replayed]));matches+=int(list(env.states[0].rigid_words)==list(env.states[1].rigid_words))
        if matches!=len(actions):raise RuntimeError('Recorded controls do not reproduce complete rigid physics')
    report={'ownedOnly':True,'clientReplayVerified':False,'ticks':len(actions),'allThreeInputChannelsExercised':True,
        'rawInputsEqualOriginalDecoderAndPhysicalConsumer':True,'nonNeutralPhysicalWrites':0,
        'independentRustBitstreamRoundTripExact':True,'normalHistoryPhysicsRigid22BitExactTicks':matches,
        'inputRateHz':100,'syntheticSweepNotHumanReplay':True}
    save_json(a.output/'proof.json',report);print(json.dumps(report))


if __name__=='__main__':main()
