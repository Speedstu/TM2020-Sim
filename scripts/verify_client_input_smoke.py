#!/usr/bin/env python3
"""Verify original client replay input ticks against a bounded live diagnostic.

Accepts an unfinished replay with multiple attempts; never invents a finish,
rewrites inputs, or fits a temporal shift. Uses the GBX group's declared offset.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True);a=p.parse_args()
    control=a.trial/'control';report=json.loads((control/'report.json').read_text())
    if not report['workerReturnedNormally'] or not report['inputRecordingRequested']:
        raise ValueError('Completed normal-input control trial required')
    if a.replay.stat().st_mtime_ns<report['startedUnixNs']:raise ValueError('Replay predates trial')
    decoded=json.loads(subprocess.check_output([str(ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'),
        'inputs',str(a.replay)],text=True))
    if decoded['mapUid']!=report['mapUid']:raise ValueError('Replay map mismatch')
    rows=list(csv.DictReader((control/'physics.csv').open()))
    source={int(r['tick_ms'])-int(r['race_start_ms']):r for r in rows if r.get('input_stage')=='1' and int(r['wrote'])}
    consumed={int(r['tick_ms'])-int(r['race_start_ms']):r for r in rows if r.get('input_stage')=='0' and r.get('consumer_verified')=='1'}
    times=list(range(0,3000,10))
    if sorted(source)!=times:raise ValueError('Expected 300 contiguous diagnostic input ticks')
    expected={}
    for ms in times:
        r=source[ms];c=consumed.get(ms)
        if c is None:raise ValueError(f'Physical consumer missing at {ms}')
        command=np.array([float(r['record_'+k]) for k in ('gas','brake','steer')],dtype=np.float32)
        physical=np.array([float(c[k+'_before']) for k in ('gas','brake','steer')],dtype=np.float32)
        if not np.array_equal(command,physical):raise ValueError(f'Input/consumer mismatch at {ms}')
        if r['physical_write']!='0' or c['physical_write']!='0':raise ValueError('Physical overwrite masks normal decoder')
        expected[ms]=command
    matches=[]
    for gi,ghost in enumerate(decoded['ghosts']):
        timeline={};conflict=False
        for group in ghost['groups']:
            if group['truncated_at'] is not None:raise ValueError('Truncated input group')
            for i,tick in enumerate(group['ticks']):
                ms=group['start_offset_ms']+10*i
                if ms not in expected:continue
                cmd=np.array([int(tick['gas']),int(tick['brake']),max(-1,tick['steer']/127)],dtype=np.float32)
                if ms in timeline and not np.array_equal(cmd,timeline[ms]):conflict=True
                timeline[ms]=cmd
        if not conflict and all(ms in timeline and np.array_equal(timeline[ms],expected[ms]) for ms in times):
            matches.append({'ghostIndex':gi,'validationSeed':ghost['validationSeed'],
                'declaredFinishMs':ghost['declaredMs'],'verifiedTicks':len(times)})
    if len(matches)!=1:raise ValueError(f'Expected one matching recorded attempt, found {len(matches)}')
    actions=np.stack([expected[t] for t in times]);changes=[]
    for i,command in enumerate(actions):
        if i==0 or not np.array_equal(command,actions[i-1]):
            changes.append({'ms':i*10,'gas':int(command[0]),'brake':int(command[1]),'steerI8':int(round(command[2]*127))})
    proof={'status':'CLIENT_REPLAY_INPUTS_VERIFIED_FOR_BOUNDED_DIAGNOSTIC','mapUid':decoded['mapUid'],
        'originalClientReplay':str(a.replay.resolve()),'replaySha256':sha(a.replay),
        'physicalTraceSha256':sha(control/'physics.csv'),'runtimeSha256':report['dllSha256'],
        'clientReplayInputsVerified':True,'verifiedTicks':300,'inputHz':100,
        'timeWindowMs':[0,2990],'clockShiftFitted':False,'replayModified':False,
        'sourceEqualsOriginalDecoderPhysicalConsumerEqualsReplay':True,'nonNeutralPhysicalWrites':0,
        'allThreeChannelsVerified':True,'matchingAttempt':matches[0],'changes':changes,
        'raceFinishVerified':False,'humanStyleVerified':False,'championRunVerified':False,
        'scope':'3-second diagnostic on Fall 2025-01; not an arrival or humanized Fall 2026-01 champion validation'}
    (a.trial/'client-replay-input-proof.json').write_text(json.dumps(proof,indent=2))
    print(json.dumps(proof,indent=2))

if __name__=='__main__':main()
