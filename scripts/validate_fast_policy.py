"""Run a learned policy from zero and replay its controls in original physics.

The source ghost supplies the race setup and validation seed. Its declared
finish time is not used as the candidate result. All ten observed official
rigid-body floats are compared bit for bit at every pre-input race boundary.
"""
import argparse
import ctypes as C
import json
import math
from pathlib import Path
import struct
import subprocess

from fast_engine import FastEngine
from official_engine import OfficialEngine, sha
from owned_ppo import OwnedPolicy
from run_fast_ppo import ROOT, steam_packs


def rigid(state):
    x=list(state.rigid_words)
    return x[12:16]+x[9:12]+x[16:19]


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    config=json.loads((a.run/'config.json').read_text())
    model=a.model or a.run/'best.tmppo'
    tape=ROOT/'cache/official-step-rust-target/release/tm2020-official-tape'
    source=Path(config['route'])
    info=json.loads(subprocess.check_output([str(tape),'info',str(source)],text=True))
    if info['startOffsetMs']>0 or info['startOffsetMs']%10:
        raise ValueError('Source tape must cover race zero on the 10-ms clock')
    policy=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',model,config['schema'],config['observations'],config['actions'])
    frames=[];controls={}
    try:
        with FastEngine(config['library'],config['map'],a.packs or steam_packs(),source,config['horizon']) as env:
            env.configure(config['lookahead'],config['gain'],config['residual'])
            if config.get('planner'):env.planner()
            state=env.reset(a.seed)
            while not(state.terminated or state.truncated):
                action,_=policy.predict(list(state.observation))
                command=[1.,-1.,action[0]] if len(action)==1 else action
                value=max(-1.,min(1.,state.observation[31]+config['residual']*command[2]))*127
                steer=int(math.copysign(math.floor(abs(value)+.5),value))
                physical=[float(command[0]>=0),float(command[1]>=0),C.c_float(steer/127).value]
                # Physics still advances every 10 ms. Planning is needed again
                # only at the next decision, and cannot affect these forces.
                if config.get('planner'):env.planner(False)
                for micro in range(config['repeat']):
                    frames.append(dict(raceMs=state.tick*10,words=rigid(state)))
                    controls[state.tick*10]=[steer,int(physical[0]),int(physical[1])]
                    if config.get('planner') and micro+1==config['repeat']:env.planner()
                    state=env.step_controls(physical,1)
                    if state.terminated or state.truncated:break
            finish=state.finish_ms;checkpoints=state.checkpoints
    finally:
        policy.close()
    (a.output/'fast.json').write_text(json.dumps(dict(seed=a.seed,finishMs=finish,checkpoints=checkpoints,frames=frames))+'\n')
    if finish<0:raise AssertionError('Candidate did not finish from zero')
    last=max(controls)
    if last>info['startOffsetMs']+(info['ticks']-1)*10:
        raise ValueError('Finished trajectory exceeds source tape capacity')
    edits=a.output/'edits.tsv'
    with edits.open('x') as out:
        for index in range(info['ticks']):
            now=info['startOffsetMs']+index*10
            if now>=0:
                s,g,b=controls[min(now,last)]
                out.write(f'{index} {s} {g} {b}\n')
    ghost=a.output/'Policy.Ghost.Gbx'
    subprocess.run([str(tape),'patch-active',str(source),str(edits),str(ghost)],check=True)
    expected={r['raceMs']:r['words'] for r in frames};checked=0
    with OfficialEngine(a.server,config['map'],ghost,a.shim) as official:
        frame=official.reset()
        with (a.output/'official.jsonl').open('x') as out:
            while frame is not None:
                out.write(json.dumps(frame)+'\n')
                now=frame['raceMs']
                if now in expected:
                    values=frame['quaternionWxyz']+frame['position']+frame['linearVelocity']
                    actual=list(struct.unpack('<10I',struct.pack('<10f',*values)))
                    if actual!=expected[now]:raise AssertionError(f'Original physics differs at {now} ms; check the source validation seed')
                    checked+=1
                frame=official.step()
        result=official.result()
    if checked!=len(frames):raise AssertionError('Original engine did not cover every candidate race frame')
    if len(result)!=1 or result[0]['validatedMs']!=finish or result[0]['validatedCheckpoints']!=checkpoints:
        raise AssertionError('Original computed race result differs')
    report=dict(schema='tm2020_fast_policy_original_physics_v1',seed=a.seed,finishMs=finish,
        checkpoints=checkpoints,exactRigidFrames=checked,rigidFloatsPerFrame=10,
        originalResult=result,modelSha256=sha(model),librarySha256=sha(Path(config['library'])),
        sourceReplaySha256=sha(source),candidateGhostSha256=sha(ghost),
        fullInternalPhysicsStateCompared=False,generalRacePolicyQualified=False)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS FAST_POLICY_ORIGINAL_PHYSICS',finish,'ms',checked,'exact rigid frames')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--model',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed',type=int,required=True,help='Must equal the source ghost validation seed')
    p.add_argument('--packs',type=Path)
    p.add_argument('--server',type=Path,default=ROOT/'cache/TrackmaniaServer-official-2026-05-15')
    p.add_argument('--shim',type=Path,default=ROOT/'native/build-linux/libtm2020_official_step.so')
    main(p.parse_args())
