#!/usr/bin/env python3
"""Continuous, checkpoint-resuming single-map CUDA PPO with bounded evidence."""
import argparse
import csv
import datetime
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OWNER='tm2020_continuous_cuda_ppo_v1'


def atomic_json(path,value):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w') as out:json.dump(value,out,indent=2);out.write('\n');out.flush();os.fsync(out.fileno())
    tmp.replace(path)


def atomic_copy(source,target):
    source=Path(source);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name(target.name+'.tmp')
    with source.open('rb') as a,tmp.open('wb') as b:
        shutil.copyfileobj(a,b);b.flush();os.fsync(b.fileno())
    tmp.replace(target)
    return hashlib.sha256(target.read_bytes()).hexdigest()


def atomic_link(path,target):
    path=Path(path);tmp=path.with_name(path.name+'.next')
    if tmp.is_symlink():tmp.unlink()
    tmp.symlink_to(Path(target).absolute());tmp.replace(path)


def read_json(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (FileNotFoundError,json.JSONDecodeError):return default


def completed_rows(run):
    try:text=(Path(run)/'updates.csv').read_text()
    except FileNotFoundError:return []
    # A flushed newline marks a complete row, even during concurrent collection.
    if '\n' not in text:return []
    text=text[:text.rfind('\n')+1]
    rows=list(csv.DictReader(io.StringIO(text)))
    if rows:
        assert [int(r['update']) for r in rows]==list(range(len(rows))),'noncontiguous progress rows'
    return rows


def score(evaluation):
    n=int(evaluation['trials']);f=int(evaluation['finishes'])
    if n<=0 or not 0<=f<=n:raise ValueError('Invalid evaluation count')
    return (f/n,-float(evaluation['meanFinishMs']) if f else float('-inf'),float(evaluation['meanReward']))


def prune_evidence(cycle,last_complete,keep=5):
    cycle=Path(cycle);run=cycle/'run';service=cycle/'cuda-service'
    for p in run.glob('update-*'):
        if not p.name.removeprefix('update-').isdigit():continue
        index=int(p.name[7:])
        if index==0 or index>last_complete-keep:continue
        if p.is_symlink() or p.parent!=run:raise ValueError('Refusing unexpected evidence path')
        shutil.rmtree(p)
        for name in (f'request-{index}.txt',f'response-{index}.txt'):
            file=service/name
            if file.is_symlink():raise ValueError('Refusing symlink in service evidence')
            file.unlink(missing_ok=True)


def publish_best(root,evaluation,model,checkpoint,source):
    root=Path(root);previous=read_json(root/'best.json')
    if previous is not None and score(evaluation)<=score(previous['evaluation']):return False
    atomic_copy(model,root/'best.tmppo');digest=atomic_copy(checkpoint,root/'best.checkpoint')
    atomic_json(root/'best.json',{'schema':OWNER,'evaluation':evaluation,'source':source,
                'checkpointSha256':digest,'updatedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'clientGameFinishVerified':False})
    return True


def stop_child(child,cycle):
    if child is None or child.poll() is not None:return
    run=Path(cycle)/'run'
    if run.exists():(run/'STOP').touch()
    else:child.terminate()
    try:child.wait(timeout=140)
    except subprocess.TimeoutExpired:child.terminate();child.wait(timeout=10)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--resume',type=Path,required=True)
    p.add_argument('--baseline-model',type=Path,required=True);p.add_argument('--baseline-checkpoint',type=Path,required=True)
    p.add_argument('--map',type=Path,default=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
    p.add_argument('--library',type=Path);p.add_argument('--restart-from-best',action='store_true')
    p.add_argument('--cycle-updates',type=int,default=500);p.add_argument('--eval-trials',type=int,default=5)
    p.add_argument('--rollout',type=int,default=256);p.add_argument('--eval-every',type=int,default=10)
    p.add_argument('--horizon',type=int,default=4000)
    p.add_argument('--disturbance-probability',type=float,default=0.)
    p.add_argument('--prior-updates',type=int,default=1000);p.add_argument('--prior-transitions',type=int,default=4096000)
    p.add_argument('--seed',type=int,default=301026);p.add_argument('--keep-updates',type=int,default=5)
    p.add_argument('--keep-cycles',type=int,default=3);p.add_argument('--max-cycles',type=int,default=0)
    a=p.parse_args();root=a.directory.resolve()
    if not(1<=a.cycle_updates<=100000 and 1<=a.eval_trials<=100 and a.keep_updates>=1 and a.keep_cycles>=1 and 1<=a.rollout<=4096 and 1<=a.eval_every<=1000 and 0<=a.disturbance_probability<=1 and 1<=a.horizon<=100000):p.error('Invalid continuous training limits')
    library=(a.library or ROOT/'cache/fast-training-final-target/release/libtm2020_generalist.so').resolve(strict=True)
    expected_owner={'schema':OWNER,'map':str(a.map.resolve()),'evalTrials':a.eval_trials,'seed':a.seed}
    if a.library is not None:expected_owner['librarySha256']=hashlib.sha256(library.read_bytes()).hexdigest()
    if a.restart_from_best:expected_owner['restartFromBest']=True
    if a.rollout!=256 or a.eval_every!=10:expected_owner.update(rollout=a.rollout,evalEvery=a.eval_every)
    if a.disturbance_probability:expected_owner['trainingDisturbanceProbability']=a.disturbance_probability
    if a.horizon!=4000:expected_owner['horizon']=a.horizon
    root.mkdir(parents=True,exist_ok=True)
    marker=root/'owner.json'
    if not marker.exists():
        if any(root.iterdir()):p.error('Nonempty directory is not owned by this supervisor')
        atomic_json(marker,expected_owner)
    owner=read_json(marker)
    if owner!=expected_owner:p.error('Session map/evaluation protocol differs')
    lock=(root/'supervisor.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:p.error('Another supervisor owns this training session')
    requested=False
    def interrupt(signum,frame):
        nonlocal requested
        requested=True
    signal.signal(signal.SIGTERM,interrupt);signal.signal(signal.SIGINT,interrupt)
    def stopped():return requested or (root/'STOP').exists()
    state=read_json(root/'state.json')
    if state is None:
        initial=root/'snapshots/initial.checkpoint';digest=atomic_copy(a.resume.resolve(strict=True),initial)
        state={'schema':OWNER,'totalUpdates':a.prior_updates,'totalTransitions':a.prior_transitions,
               'latestCheckpoint':str(initial),'latestCheckpointSha256':digest,'nextCycle':0,
               'cyclesCompleted':0,'status':'STARTING','map':str(a.map.resolve()),'device':'cuda',
               'physicsDevice':'cpu','retainedUpdatesPerCycle':a.keep_updates,'retainedCycles':a.keep_cycles}
    def save(status=None,**extra):
        if status is not None:state['status']=status
        state.update(extra,supervisorPid=os.getpid(),updatedUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        atomic_json(root/'state.json',state)
    child=None;cycle=None;attempts=0;cycles_this_start=0
    try:
        if not (root/'best.json').exists() and not stopped():
            save('EVALUATING_BASELINE')
            destination=root/f'baseline-{time.time_ns()}'
            command=[str(ROOT/'native/build-linux/tm2020_generalist_train'),'--mode','eval','--library',str(library),
              '--map',str(a.map.resolve()),'--packs',str(__import__('run_fast_ppo').steam_packs()),'--route','/dev/null',
              '--output',str(destination),'--model',str(a.baseline_model.resolve(strict=True)),'--actions',str(struct.unpack_from('<I',a.baseline_model.read_bytes(),16)[0]),'--residual','1','--planner','0',
              '--environments','16','--trials',str(a.eval_trials),'--seed',str((a.seed-50000)%(2**32)),'--horizon',str(a.horizon)]
            with (root/'baseline.log').open('a') as out:baseline=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
            while baseline.poll() is None:
                if stopped():baseline.terminate();baseline.wait(timeout=10);break
                time.sleep(.2)
            if not stopped():
                if baseline.returncode:raise RuntimeError('Baseline evaluation failed; inspect baseline.log')
                result=read_json(destination/'report.json')['candidate']
                publish_best(root,result,a.baseline_model,a.baseline_checkpoint,{'type':'baseline','report':str(destination/'report.json')})
        while not stopped() and (a.max_cycles==0 or cycles_this_start<a.max_cycles):
            index=state['nextCycle'];state['nextCycle']=index+1
            cycle=root/'cycles'/f'cycle-{index:06d}';cycle.parent.mkdir(exist_ok=True)
            base_updates=state['totalUpdates'];base_transitions=state['totalTransitions'];committed=0
            resume_checkpoint=state['latestCheckpoint']
            if a.restart_from_best and (root/'best.checkpoint').exists():
                restart=root/f'restart-{index:06d}.checkpoint'
                subprocess.run([str(ROOT/'tools/venv-gpu/bin/python'),str(ROOT/'scripts/recover_best_policy.py'),
                    '--best',str(root/'best.checkpoint'),'--latest',state['latestCheckpoint'],'--output',str(restart)],check=True,cwd=ROOT)
                resume_checkpoint=str(restart)
                for old in sorted(root.glob('restart-*.checkpoint'))[:-2]:old.unlink()
            command=[sys.executable,str(ROOT/'scripts/run_gpu_training.py'),'--directory',str(cycle),'--resume',resume_checkpoint,'--library',str(library),
                     '--map',str(a.map.resolve()),'--updates',str(a.cycle_updates),'--seed',str(a.seed),'--eval-trials',str(a.eval_trials),
                     '--rollout',str(a.rollout),'--eval-every',str(a.eval_every),'--disturbance-probability',str(a.disturbance_probability),'--horizon',str(a.horizon)]
            with (root/'controller.log').open('a') as out:child=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT)
            save('STARTING_CYCLE',currentCycle=str(cycle),controllerPid=child.pid)
            atomic_link(root/'current',cycle);atomic_link(root/'training.log',cycle/'training.log')
            def commit_progress():
                nonlocal committed,attempts
                run=cycle/'run';rows=completed_rows(run)
                if len(rows)<=committed:return
                last=int(rows[-1]['update']);folder=run/f'update-{last}'
                checkpoint=folder/'training.checkpoint'
                if not checkpoint.exists() or not (folder/'updated.tmppo').exists():return
                total=base_updates+len(rows);snapshot=root/'snapshots'/f'update-{total:012d}.checkpoint'
                digest=atomic_copy(checkpoint,snapshot)
                best=read_json(run/'best.json')
                if best is not None and int(best['update'])<=last:
                    bestfolder=run/f'update-{best["update"]}'
                    previous=read_json(root/'best.json')
                    if previous is None or score(best['evaluation'])>score(previous['evaluation']):
                        publish_best(root,best['evaluation'],bestfolder/'updated.tmppo',bestfolder/'training.checkpoint',
                                     {'type':'training','cycle':index,'update':best['update']})
                state.update(totalUpdates=total,totalTransitions=base_transitions+sum(int(r['transitions']) for r in rows),
                             latestCheckpoint=str(snapshot),latestCheckpointSha256=digest,lastCycleUpdate=last)
                save('RUNNING')
                atomic_link(root/'latest.checkpoint',snapshot)
                # Only disposable artifacts produced inside this owned session are pruned.
                prune_evidence(cycle,last,a.keep_updates)
                snapshots=sorted((root/'snapshots').glob('update-*.checkpoint'))
                for old in snapshots[:-2]:old.unlink()
                committed=len(rows);attempts=0
            while child.poll() is None:
                commit_progress()
                if stopped():stop_child(child,cycle);break
                time.sleep(1.)
            commit_progress();code=child.poll();child=None
            if stopped():break
            if code:
                attempts+=1;save('BACKOFF',lastError=f'Cycle {index} exited with {code}',consecutiveFailures=attempts)
                deadline=time.monotonic()+min(300.,10.*2**min(attempts-1,5))
                while not stopped() and time.monotonic()<deadline:time.sleep(1.)
                continue
            state['cyclesCompleted']+=1;cycles_this_start+=1;save('BETWEEN_CYCLES')
            retained=sorted((root/'cycles').glob('cycle-*'))
            for old in retained[:-a.keep_cycles]:
                if old.is_symlink():raise ValueError('Unexpected cycle symlink')
                shutil.rmtree(old)
        save('STOPPED' if stopped() else 'TEST_COMPLETE')
    finally:
        stop_child(child,cycle) if cycle is not None else None
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()

if __name__=='__main__':main()
