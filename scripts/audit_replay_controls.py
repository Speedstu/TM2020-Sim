#!/usr/bin/env python3
"""Compare original replay inputs with measured internal actuation.

Read-only: exports original GBX inputs, never changes or fabricates a replay.
All comparisons use the declared race clock, with no fitted time shift.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from run_fast_ppo import ROOT
from prepare_fall_campaign import save_json


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(path):
    binary=ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'
    value=json.loads(subprocess.check_output([str(binary),'inputs',str(path)],text=True))
    if len(value['ghosts'])!=1:raise ValueError('Select one ghost explicitly')
    ghost=value['ghosts'][0];duration=ghost['declaredMs']
    if not isinstance(duration,int) or duration<=0:raise ValueError('Finished ghost required')
    timeline={}
    for group in ghost['groups']:
        if group['truncated_at'] is not None:raise ValueError('Truncated replay input stream')
        for i,t in enumerate(group['ticks']):
            ms=group['start_offset_ms']+i*10
            if 0<=ms<duration:
                command=(int(t['gas']),int(t['brake']),max(-1,t['steer']/127))
                if ms in timeline and timeline[ms]!=command:raise ValueError('Conflicting input groups')
                timeline[ms]=command
    if not timeline:raise ValueError('No driving ticks')
    return value,timeline


def metrics(controls):
    a=np.asarray(controls,dtype=float)
    if a.ndim!=2 or a.shape[1]!=3 or len(a)<2 or not np.isfinite(a).all():
        raise ValueError('Finite contiguous gas/brake/steer samples required')
    steer=np.rint(a[:,2]*127).astype(int);delta=np.diff(steer);moving=delta[delta!=0]
    cuts=np.r_[0,np.flatnonzero(delta!=0)+1,len(a)]
    holds=np.diff(cuts)
    return {'ticks':len(a),'durationSeconds':len(a)*.01,
        'gasActiveTicks':int(np.count_nonzero(a[:,0]>.5)),
        'brakeActiveTicks':int(np.count_nonzero(a[:,1]>.5)),
        'nonNeutralSteeringTicks':int(np.count_nonzero(steer)),
        'steeringChangesPerSecond':len(moving)/(len(a)*.01),
        'steeringTotalVariationPerSecond':float(np.abs(delta).sum()/127/(len(a)*.01)),
        'stepRawP50P95P99Max':np.percentile(np.abs(delta),[50,95,99,100]).tolist(),
        'directionReversalsOfSteeringChanges':int(np.count_nonzero(moving[1:]*moving[:-1]<0)),
        'shortSteeringHoldsAtMost20Ms':int(np.count_nonzero(holds<=2)),
        'medianSteeringHoldMs':float(np.median(holds)*10),
        'gasTransitions':int(np.count_nonzero(np.diff(a[:,0]>.5))),
        'brakeTransitions':int(np.count_nonzero(np.diff(a[:,1]>.5)))}


def audit(index,run_dir,out):
    replay=run_dir/'client-autosave.Replay.Gbx';trace=run_dir/'control/physics.csv'
    human=ROOT/f'local/training/fall-campaign-0.52/{index:02d}/reference.Ghost.Gbx'
    recorded,events=decode(replay);reference,human_events=decode(human)
    if recorded['mapUid']!=reference['mapUid']:raise ValueError('Map UID differs')
    ms_limit=recorded['ghosts'][0]['declaredMs']
    rows=list(csv.DictReader(trace.open()));written=[r for r in rows if int(r['wrote']) and r.get('input_stage','0')=='0']
    if not written:raise ValueError('No applied actions in trace')
    start=int(written[0]['race_start_ms']);actual={}
    for r in written:
        ms=int(r['tick_ms'])-int(r['race_start_ms'])
        if int(r['race_start_ms'])==start and 0<=ms<ms_limit:
            command=tuple(float(r[k]) for k in ('gas','brake','steer'))
            if ms in actual and actual[ms]!=command:raise ValueError('Conflicting physical tick commands')
            actual[ms]=command
    times=sorted(actual)
    if any(b-a!=10 for a,b in zip(times,times[1:])):raise ValueError('Actuation trace has gaps')
    common=sorted(actual.keys()&events.keys())
    if not common:raise ValueError('No overlapping original replay/physics clocks')
    errors=np.abs(np.array([actual[t] for t in common])-np.array([events[t] for t in common]))
    complete=times[0]==0 and times[-1]>=((ms_limit-1)//10)*10
    report={'mapIndex':index,'mapUid':recorded['mapUid'],'clockShiftMs':0,
        'originalReplaySha256':digest(replay),'physicalTraceSha256':digest(trace),
        'humanReferenceSha256':digest(human),'declaredMs':ms_limit,
        'comparedTicks':len(common),'comparedCoverage':len(common)/len(times),
        'channelMismatchTicks':dict(zip(('gas','brake','steer'),(errors>1e-6).sum(axis=0).tolist())),
        'completeRaceActuationTrace':complete,
        'replayInputsMatchActuation':bool(complete and np.all(errors<=1e-6) and len(common)==len(times)),
        'recordedInputs':metrics([events[t] for t in sorted(events)]),
        'actualBotControls':metrics([actual[t] for t in times]),
        'humanReferenceControls':metrics([human_events[t] for t in sorted(human_events)]),
        'filesModified':False,'referenceHumanOriginIndependentlyVerified':False,
        'humanIndistinguishabilityProven':False}
    save_json(out/f'{index:02d}/original-inputs.json',recorded)
    save_json(out/f'{index:02d}/audit.json',report)
    print(json.dumps(report),flush=True);return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    runs=[(3,ROOT/'local/recon/internal-0.65/live03-original'),
          (6,ROOT/'local/recon/internal-0.65/live06-registers')]
    reports=[audit(i,path,out) for i,path in runs]
    save_json(out/'summary.json',{'reports':reports,'replaysRewritten':False})


if __name__=='__main__':main()
