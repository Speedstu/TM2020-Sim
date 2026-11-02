"""Train-only expert labels on the actual learner states, with exact paired physics."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import csv
import ctypes as C
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import time

from fast_engine import FastEngine
from generalist_engine import GeneralistEngine,SCHEMA
from owned_ppo import OwnedPolicy
from run_fast_ppo import ROOT,steam_packs
from observation_history import ObservationHistory,schema_suffix


def quantize(value):
    return int(math.copysign(math.floor(abs(max(-1.,min(1.,value))*127)+.5),value))


def collect(a):
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=False)
    teacher_dir=ROOT/'local/recon/fast-0.37/release-candidate'
    config=json.loads((teacher_dir/'config.json').read_text());mentor_model=teacher_dir/'policy.tmppo'
    mentor=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',mentor_model,config['schema'],48,1)
    learner=None
    frames=1
    if a.student is not None:
        inputs=struct.unpack_from('<I',a.student.read_bytes(),12)[0];frames=inputs//48
        learner=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',a.student,SCHEMA+schema_suffix(frames)+'|policy_actions=steering_direct1',inputs,1)
    track=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx';source=ROOT/'local/replays/tmtas-4634.Replay.Gbx'
    teacher_lib=ROOT/'cache/fast-training-final-target/release/libtm2020_fast.so'
    student_lib=ROOT/'cache/reward-study-target/release/libtm2020_speed.so'
    started=time.perf_counter();results=[]
    try:
        with FastEngine(teacher_lib,track,steam_packs(),source,4000) as teacher_base,GeneralistEngine(student_lib,track,steam_packs(),4000) as student_base:
            teacher_base.configure(config['lookahead'],config['gain'],config['residual']);teacher_base.planner(True)
            def episode(index):
                rng=random.Random(a.seed+index);rows=0;checked=0;interventions=0;steer_sum=0.
                with FastEngine(teacher_lib,clone=teacher_base) as t,GeneralistEngine(student_lib,clone=student_base) as s:
                    ts=t.reset(a.seed+index);ss=s.reset(a.seed+index)
                    history=ObservationHistory(frames);history.reset(ss.observation)
                    perturb_start=rng.randrange(8,23);perturb_duration=rng.randrange(1,6)
                    amplitude=(1. if index%2 else -1.)*rng.uniform(.15,.5) if index else 0.
                    with (output/f'episode-{index:04d}.csv').open('x') as stream:
                        writer=csv.writer(stream);writer.writerow([f'x{k}' for k in range(48)]+['steer','episode','decision','used_student'])
                        while not(ts.terminated or ts.truncated or ss.terminated or ss.truncated):
                            if list(ts.rigid_words)!=list(ss.rigid_words) or ts.tick!=ss.tick:raise AssertionError('Paired physics diverged')
                            checked+=1;x=list(ss.observation)
                            residual=mentor.predict(list(ts.observation))[0][0]
                            expert=max(-1.,min(1.,ts.observation[31]+config['residual']*residual))
                            use_student=learner is not None and rng.random()<a.mixture
                            action=learner.predict(history.values)[0][0] if use_student else expert
                            writer.writerow([*x,quantize(expert)/127,index,rows,int(use_student)])
                            if perturb_start<=rows<perturb_start+perturb_duration:action+=amplitude;interventions+=1
                            if a.noise:action+=rng.gauss(0.,a.noise)
                            steer=quantize(action);steer_sum+=abs(steer)/127
                            controls=[1.,0.,C.c_float(steer/127).value]
                            ts=t.step_controls(controls,5);ss=s.step_controls(controls,int(ts.advanced_ticks));history.push(ss.observation);rows+=1
                    # The two adapters have different absorbing failure rules.
                    # A learner stuck-limit can stop inside the final held
                    # action before the teacher adapter's five ticks finish.
                    early_student_end=bool((ss.terminated or ss.truncated) and ss.tick<ts.tick)
                    if not early_student_end and list(ts.rigid_words)!=list(ss.rigid_words):
                        raise AssertionError(f'Final paired physics diverged at {ts.tick}/{ss.tick}; reserved={ss.reserved}')
                    return {'episode':index,'seed':a.seed+index,'rows':rows,'finishMs':ss.finish_ms,'teacherFinishMs':ts.finish_ms,
                            'matchedDecisionStates':checked,'perturbedDecisions':interventions,'meanAbsSteer':steer_sum/max(rows,1),
                            'studentMixture':a.mixture if learner else 0.,'endedByTeacher':bool(ts.truncated and not ss.truncated),
                            'endedEarlyByStudent':early_student_end}
            with ThreadPoolExecutor(max_workers=a.workers) as pool:
                futures=[pool.submit(episode,i) for i in range(a.trials)]
                for future in as_completed(futures):
                    result=future.result();results.append(result);print(json.dumps(result),flush=True)
                    (output/'progress.json').write_text(json.dumps({'completed':len(results),'trials':a.trials,'seconds':time.perf_counter()-started,'cases':sorted(results,key=lambda r:r['episode'])},indent=2)+'\n')
    finally:
        mentor.close()
        if learner:learner.close()
    with (output/'dataset.csv').open('x') as stream:
        writer=csv.writer(stream);writer.writerow([f'x{k}' for k in range(48)]+['steer','episode','decision','used_student'])
        for path in sorted(output.glob('episode-*.csv')):
            with path.open() as f:
                reader=csv.reader(f);next(reader);writer.writerows(reader)
    report={'schema':'tm2020_generalist_dagger_v1','cases':sorted(results,key=lambda r:r['episode']),
            'rows':sum(r['rows'] for r in results),'seconds':time.perf_counter()-started,
            'teacherAvailableOnlyDuringTraining':True,'deploymentRequiresExpert':False,'policyObservations':48,
            'teacherModelSha256':hashlib.sha256(mentor_model.read_bytes()).hexdigest(),
            'studentModel':str(a.student) if a.student else None}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--student',type=Path);p.add_argument('--trials',type=int,default=8);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--mixture',type=float,default=.5);p.add_argument('--noise',type=float,default=.015);p.add_argument('--seed',type=int,default=45026)
    a=p.parse_args()
    if not (1<=a.trials<=200 and 1<=a.workers<=16 and 0<=a.mixture<=1 and 0<=a.noise<=.2):p.error('Invalid bounded DAgger settings')
    collect(a)
