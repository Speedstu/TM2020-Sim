"""Audit time-major native PPO with independent 10-ms physics re-execution.

Recomputes action quantization and reward outside the collector. Bootstrap
values and behavior likelihoods are independently checked against the saved
behavior model. No update, selection or replacement dynamics occurs here.
"""
import argparse
import csv
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess

from fast_engine import FastEngine, State, State48
from owned_ppo import OwnedPolicy


class Physical(C.Structure):
    _fields_=[('env',C.c_uint32),('episode',C.c_uint32),('before',State),('after',State),('action',C.c_double*3)]


def require(ok,message):
    if not ok:raise AssertionError(message)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]


def main(a):
    require(not a.output.exists(),'Audit never overwrites evidence')
    config=json.loads((a.run/'config.json').read_text())
    folder=a.run/f'update-{a.update}'
    data=(folder/'physics.bin').read_bytes()
    nx=config.get('observations',32)
    state_type=State48 if nx==48 else State
    class Evidence(C.Structure):
        _fields_=[('env',C.c_uint32),('episode',C.c_uint32)]+([('bank',C.c_uint32),('reserved',C.c_uint32)] if nx==48 else [])+[('before',state_type),('after',state_type),('action',C.c_double*3)]
    size=C.sizeof(Evidence)
    require(data[:8]==(b'TMFAST03' if nx==48 else b'TMFAST01') and size==(1128 if nx==48 else 864) and (len(data)-8)%size==0,'Unknown physical evidence layout')
    evidence=[Evidence.from_buffer_copy(data[i:i+size]) for i in range(8,len(data),size)]
    with (folder/'rollout.csv').open() as stream:rows=list(csv.DictReader(stream))
    require(len(rows)==len(evidence)==config['environments']*config['rolloutLength'],'Rollout dimensions differ')
    a.output.mkdir(parents=True)
    subprocess.run([str(a.auditor.resolve()),str((folder/'behavior.tmppo').resolve()),
        str((folder/'rollout.csv').resolve()),str((a.output/'behavior.json').resolve()),'--multiple-episodes'],check=True)
    policy=OwnedPolicy(a.policy_library,folder/'behavior.tmppo',config['schema'],nx,config['actions'])
    maximum_bootstrap=0.;maximum_reward=0.;ticks=0;checked=0
    # An update may start mid-episode. Reconstruct its earlier history from
    # retained previous updates before validating the requested one.
    all_updates=range(a.update+1)
    with FastEngine(a.library,config['map'],a.packs,config['route'],config['horizon']) as root:
        root.configure(config['lookahead'],config['gain'],config['residual'])
        if config.get('planner'):root.planner()
        for env_index in range(config['environments']):
            with FastEngine(a.library,clone=root) as env:
                episode=-1;state=None;best=0.
                for update in all_updates:
                    raw=(a.run/f'update-{update}'/'physics.bin').read_bytes()
                    events=[Evidence.from_buffer_copy(raw[i:i+size]) for i in range(8,len(raw),size)]
                    for at in range(env_index,len(events),config['environments']):
                        event=events[at]
                        require(event.env==env_index,'Environment mixing')
                        if event.episode!=episode:
                            require(event.episode==episode+1,'Episode sequence differs')
                            if state is not None:require(state.terminated or state.truncated,'Reset before physical boundary')
                            episode=event.episode
                            seed=config['seed']+env_index+episode*config['environments']
                            state=env.reset_bank(seed,event.bank) if nx==48 else env.reset(seed)
                            best=state.progress
                        require(bytes(state)==bytes(event.before),'Before observation/physical state differs')
                        if update==a.update:
                            row=rows[at]
                            require(list(state.observation)==[float(row[f'observation_{j}']) for j in range(nx)],'Policy observation misaligned')
                            sampled=[math.tanh(float(row[f'latent_{j}'])) for j in range(config['actions'])]
                            expected=[1.,-1.,sampled[0]] if len(sampled)==1 else sampled
                            require(all(abs(x-y)<1e-14 for x,y in zip(expected,event.action)),'Sampled PPO action differs')
                        # Independently reproduce the collector's discrete controls.
                        value=max(-1.,min(1.,state.observation[31]+config['residual']*event.action[2]))*127
                        steer=int(math.copysign(math.floor(abs(value)+.5),value))
                        controls=[float(event.action[0]>=0),float(event.action[1]>=0),f32(steer/127)]
                        before_best=best;before_cp=state.checkpoints
                        advanced=event.after.advanced_ticks
                        if config.get('planner'):env.planner(False)
                        for micro in range(advanced):
                            if config.get('planner') and micro+1==advanced:env.planner(True)
                            state=env.step_controls(controls,1)
                            if state.progress>best+.01:best=state.progress
                        progress=max(0.,min(30.,best-before_best))
                        reward=(.05*progress+10.*(state.checkpoints-before_cp)+(100. if state.terminated else 0.)+
                                (-20. if state.truncated else 0.)-config.get('timePenalty',.002)*advanced-
                                config.get('crossTrackPenalty',.00002)*min(state.cross_track,30.)**2*advanced)
                        require(abs(reward-event.after.reward)<1e-12,'Reward formula differs outside collector')
                        state.reward=event.after.reward;state.advanced_ticks=advanced
                        if bytes(state)!=bytes(event.after):
                            fields=[name for name,typ in state_type._fields_ if
                                C.string_at(C.addressof(state)+getattr(state_type,name).offset,C.sizeof(typ))!=
                                C.string_at(C.addressof(event.after)+getattr(state_type,name).offset,C.sizeof(typ))]
                            raise AssertionError('Physical successor differs at env '+str(env_index)+', row '+str(at)+': '+str(fields))
                        if update==a.update:
                            require(float(row['reward'])==event.after.reward*.01,'PPO reward scaling differs')
                            _,bootstrap=policy.predict(list(state.observation))
                            error=abs(bootstrap-float(row['next_value']));maximum_bootstrap=max(maximum_bootstrap,error)
                            require(error<1e-12,'PPO critic uses another successor')
                            boundary=bool(state.truncated) or (at//config['environments']+1==config['rolloutLength'] and not state.terminated)
                            require(int(row['terminated'])==state.terminated and bool(int(row['truncated']))==boundary,'Vector rollout boundary differs')
                            require(float(row['elapsed_steps'])==advanced/config['repeat'],'Semi-Markov duration differs')
                            maximum_reward=max(maximum_reward,abs(reward-event.after.reward));checked+=1;ticks+=advanced
    policy.close()
    result=dict(schema='tm2020_fast_vector_physics_audit_v1',update=a.update,transitions=checked,
        physicsTicksReplayedForAuditedUpdate=ticks,allPhysicalWordsAndObservationsExact=True,
        rewardMaximumError=maximum_reward,bootstrapMaximumError=maximum_bootstrap,
        independentlyRecomputedDiscreteActions=True,vectorBoundariesExact=True,
        librarySha256=sha(a.library),behaviorSha256=sha(folder/'behavior.tmppo'),
        physicsEvidenceSha256=sha(folder/'physics.bin'),completeExactPhysicsQualified=False)
    (a.output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS FAST_VECTOR_AUDIT',checked,'transitions',ticks,'ticks')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('run','library','packs','policy-library','auditor','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--update',type=int,default=0)
    main(p.parse_args())
