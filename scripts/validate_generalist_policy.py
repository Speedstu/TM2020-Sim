"""Verify a route-free policy's controls in the pinned official race validator."""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import struct
import subprocess

from generalist_engine import GeneralistEngine,SCHEMA
from official_engine import OfficialEngine,sha
from owned_ppo import OwnedPolicy
from run_fast_ppo import ROOT,steam_packs
from validate_fast_policy import rigid
from observation_history import ObservationHistory,schema_suffix

META=ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'
TAPE=ROOT/'cache/official-step-rust-target/release/tm2020-official-tape'


def metadata(kind,path):
    return json.loads(subprocess.check_output([str(META),kind,str(path)],text=True))


def validate(model,track,source,library,output,threshold_ms,server=None,shim=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    model,track,source,library=(Path(x).resolve(strict=True) for x in (model,track,source,library))
    track_meta=metadata('map',track);replay=metadata('replay',source)
    if not track_meta['mapUid'] or replay['mapUid']!=track_meta['mapUid']:raise ValueError('Official source/map UID differs')
    seed=replay['validationSeed']
    if seed is None or seed==0:raise ValueError('Validation seed is unknown')
    info=json.loads(subprocess.check_output([str(TAPE),'info',str(source)],text=True))
    if info['startOffsetMs']>0 or info['startOffsetMs']%10:raise ValueError('Replay does not cover race zero')
    data=model.read_bytes();version,nx,na,hidden,ns,res=struct.unpack_from('<6I',data,8)
    if data[:8]!=b'TMPPO001' or version!=1 or nx not in (48,144,240) or res!=0 or na not in (1,3):raise ValueError('Invalid generalist model')
    schema=data[32:32+ns].decode()
    if schema!=SCHEMA+schema_suffix(nx//48)+'|policy_actions='+('steering_direct1' if na==1 else 'pedals_direct3'):raise ValueError('Invalid policy schema')
    frames=[];controls={}
    policy=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',model,schema,nx,na)
    try:
        with GeneralistEngine(library,track,steam_packs(),horizon=12000) as env:
            state=env.reset(seed)
            history=ObservationHistory(nx//48);history.reset(state.observation)
            while not(state.terminated or state.truncated):
                action,_=policy.predict(history.values)
                command=[1.,-1.,action[0]] if na==1 else action
                value=max(-1.,min(1.,command[2]))*127
                steer=int(math.copysign(math.floor(abs(value)+.5),value))
                physical=[float(command[0]>=0),float(command[1]>=0),C.c_float(steer/127).value]
                for _ in range(5):
                    frames.append({'raceMs':state.tick*10,'words':rigid(state)})
                    controls[state.tick*10]=[steer,int(physical[0]),int(physical[1])]
                    state=env.step_controls(physical,1)
                    if state.terminated or state.truncated:break
                history.push(state.observation)
            finish=state.finish_ms;checkpoints=state.checkpoints
    finally:policy.close()
    report={'schema':'tm2020_generalist_official_validation_v1','mapUid':track_meta['mapUid'],
            'modelSha256':sha(model),'mapSha256':sha(track),'sourceReplaySha256':sha(source),
            'seed':seed,'simulationFinishMs':finish,'thresholdMs':threshold_ms,
            'originalGamePhysicsExecuted':False,'thresholdAchieved':False,'onlineLeaderboardSubmitted':False}
    # Do not spend validator work on a policy that fails even in simulation.
    if finish<0 or finish>threshold_ms:
        report['status']='SIMULATION_BELOW_TARGET'
    elif max(controls)>info['startOffsetMs']+(info['ticks']-1)*10:
        report['status']='SOURCE_TAPE_TOO_SHORT'
    else:
        edits=output/'edits.tsv';last=max(controls)
        with edits.open('x') as stream:
            for index in range(info['ticks']):
                now=info['startOffsetMs']+index*10
                if now>=0:
                    s,g,b=controls[min(now,last)];stream.write(f'{index} {s} {g} {b}\n')
        ghost=output/'Policy.Ghost.Gbx'
        subprocess.run([str(TAPE),'patch-active',str(source),str(edits),str(ghost)],check=True)
        expected={r['raceMs']:r['words'] for r in frames};checked=0
        with OfficialEngine(server or ROOT/'cache/TrackmaniaServer-official-2026-05-15',track,ghost,
                            shim or ROOT/'native/build-linux/libtm2020_official_step.so') as original:
            frame=original.reset()
            while frame is not None:
                now=frame['raceMs']
                if now in expected:
                    values=frame['quaternionWxyz']+frame['position']+frame['linearVelocity']
                    actual=list(struct.unpack('<10I',struct.pack('<10f',*values)))
                    if actual!=expected[now]:raise AssertionError(f'Original physics mismatch at {now} ms')
                    checked+=1
                frame=original.step()
            results=original.result()
        if checked!=len(frames) or len(results)!=1:raise AssertionError('Incomplete official validation')
        result=results[0]
        if result['mapUid']!=track_meta['mapUid'] or result['validatedMs']!=finish or result['validatedCheckpoints']!=checkpoints:
            raise AssertionError('Official result differs from complete simulated race')
        report.update(status='OFFICIAL_TIME_VERIFIED',originalGamePhysicsExecuted=True,
            thresholdAchieved=result['validatedMs']<=threshold_ms,finishMs=result['validatedMs'],
            exactRigidFrames=checked,checkpoints=checkpoints,originalResult=result)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('model','map','source','library','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--threshold-ms',type=int,required=True);a=p.parse_args()
    validate(a.model,a.map,a.source,a.library,a.output,a.threshold_ms)
