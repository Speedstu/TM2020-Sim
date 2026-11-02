#!/usr/bin/env python3
"""Native physics/collector and checkpoint-compatible CUDA PPO on one map."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
from run_fast_ppo import steam_packs

ROOT=Path(__file__).resolve().parents[1]


def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--resume',type=Path,required=True)
    p.add_argument('--map',type=Path,default=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
    p.add_argument('--packs',type=Path);p.add_argument('--library',type=Path)
    p.add_argument('--updates',type=int,default=1000)
    p.add_argument('--environments',type=int,default=16);p.add_argument('--threads',type=int,default=16)
    p.add_argument('--rollout',type=int,default=256);p.add_argument('--horizon',type=int,default=4000)
    p.add_argument('--seed',type=int,default=301026);p.add_argument('--eval-every',type=int,default=10)
    p.add_argument('--eval-trials',type=int,default=1)
    p.add_argument('--disturbance-probability',type=float,default=0.)
    p.add_argument('--rollout-format',choices=['csv','binary'],default='binary')
    p.add_argument('--gpu-optimizer',choices=['eager','graph'],default='graph')
    p.add_argument('--curriculum-replay',type=Path);p.add_argument('--bank-min-fraction',type=float,default=0.)
    p.add_argument('--bank-probability',type=float,default=.9);p.add_argument('--bank-decay',type=int,default=100000)
    p.add_argument('--keep-updates',type=int,default=0,help='0 keeps all evidence; otherwise keep first and latest N updates plus best')
    p.add_argument('--gpu-python',type=Path,default=ROOT/'tools/venv-gpu/bin/python')
    a=p.parse_args();job=a.directory.resolve();checkpoint=a.resume.resolve(strict=True)
    if job.exists():p.error('Job directory already exists; never overwrite retained training')
    if not 1<=a.updates<=100000:p.error('updates outside 1..100000')
    if a.keep_updates<0:p.error('keep-updates must be nonnegative')
    trainer=ROOT/'native/build-linux/tm2020_generalist_train';library=(a.library or ROOT/'cache/fast-training-final-target/release/libtm2020_generalist.so').resolve(strict=True)
    header=checkpoint.read_bytes()[:32]
    if len(header)!=32 or header[:8]!=b'TMTRAIN1':p.error('Invalid native checkpoint header')
    version,nx,actions,width,ns,flags=struct.unpack_from('<6I',header,8)
    if version!=1 or nx not in (48,144,240) or actions not in (1,3):p.error('Checkpoint observation/action dimensions differ')
    for f in (a.gpu_python,trainer,library,ROOT/'native/build-linux/libtm2020_gpu_helpers.so'):
        if not f.is_file():p.error(f'Missing built dependency: {f}')
    job.mkdir(parents=True);service=job/'cuda-service';service.mkdir()
    command=[str(trainer),'--mode','train','--library',str(library),'--map',str(a.map.resolve(strict=True)),
             '--packs',str((a.packs or steam_packs()).resolve(strict=True)),'--route',str(a.curriculum_replay.resolve(strict=True)) if a.curriculum_replay else '/dev/null',
             '--output',str(job/'run'),'--resume',str(checkpoint),'--actions',str(actions),'--planner','0','--residual','1',
             '--curriculum',str(int(a.curriculum_replay is not None)),'--bank-min-fraction',str(a.bank_min_fraction),
             '--bank-probability',str(a.bank_probability),'--bank-decay',str(a.bank_decay),
             '--environments',str(a.environments),'--threads',str(a.threads),
             '--rollout',str(a.rollout),'--horizon',str(a.horizon),'--repeat','5','--updates',str(a.updates),
             '--eval-every',str(a.eval_every),'--eval-trials',str(a.eval_trials),'--seed',str(a.seed),'--gpu-service',str(service),
             '--disturbance-probability',str(a.disturbance_probability),'--rollout-format',a.rollout_format]
    metadata={'schema':'tm2020_single_map_cuda_ppo_job_v1','createdUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'supervisorPid':os.getpid(),'map':str(a.map.resolve()),'onlyThisMap':True,'device':'cuda','physicsDevice':'cpu',
              'command':command,'resume':str(checkpoint),'resumeSha256':sha(checkpoint),'trainerSha256':sha(trainer),
              'librarySha256':sha(library),'targetUpdates':a.updates,'targetTransitions':a.updates*a.environments*a.rollout,
              'environments':a.environments,'policyActions':actions,'evaluationTrials':a.eval_trials,'rolloutFormat':a.rollout_format,'gpuOptimizer':a.gpu_optimizer,'stopFile':str(job/'run/STOP'),'state':'STARTING'}
    def status(state,**extra):
        metadata.update(state=state,**extra);temporary=job/'job.json.tmp';temporary.write_text(json.dumps(metadata,indent=2)+'\n');temporary.replace(job/'job.json')
    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    worker=collector=None
    try:
        with (job/'gpu.log').open('x') as gpu_log,(job/'training.log').open('x') as train_log:
            worker=subprocess.Popen([str(a.gpu_python.absolute()),'-u',str(ROOT/'scripts/gpu_ppo_service.py'),
                  '--directory',str(service),'--parent-pid',str(os.getpid()),'--optimizer',a.gpu_optimizer],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=gpu_log,stderr=subprocess.STDOUT)
            status('STARTING',workerPid=worker.pid)
            deadline=time.monotonic()+120
            while not (service/'ready.txt').exists():
                if worker.poll() is not None:raise RuntimeError('CUDA service failed to initialize; see gpu.log')
                if time.monotonic()>deadline:raise TimeoutError('CUDA service initialization timeout')
                time.sleep(.1)
            collector=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=train_log,stderr=subprocess.STDOUT)
            status('RUNNING',collectorPid=collector.pid,deviceInfo=json.loads((service/'device.json').read_text()))
            print('CUDA_TRAINING_STARTED',collector.pid,str(job),flush=True)
            while collector.poll() is None:
                if worker.poll() is not None:raise RuntimeError('CUDA service exited before collector')
                if a.keep_updates:
                    try:
                        report=json.loads((job/'run/report.json').read_text())
                    except (FileNotFoundError,json.JSONDecodeError):pass
                    else:
                        from train_continuous import prune_evidence
                        prune_evidence(job,int(report['updates'])-1,a.keep_updates)
                time.sleep(.25)
            code=collector.returncode
            if code:raise RuntimeError(f'Native collector exited with code {code}; see training.log')
            status('COMPLETE',collectorExitCode=code,completedUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    except KeyboardInterrupt:
        status('INTERRUPTED');raise
    except Exception as error:
        status('FAILED',error=str(error));raise
    finally:
        if collector is not None and collector.poll() is None:
            # Preserve a graceful checkpoint boundary when possible.
            run=job/'run'
            if run.exists():(run/'STOP').touch()
            try:collector.wait(timeout=10)
            except subprocess.TimeoutExpired:collector.terminate();collector.wait(timeout=5)
        (service/'STOP').touch()
        if worker is not None and worker.poll() is None:
            try:worker.wait(timeout=5)
            except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=5)

if __name__=='__main__':main()
