#!/usr/bin/env python3
"""Persistent PPO curriculum. Only real-game evidence can finish the goal."""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import time
import numpy as np
import torch

from compare_hybrid_ppo import Policy,save_json
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights,atomic_torch
from ppo_time_credit import update
import ppo_time_credit
import top10_core
from top10_core import DIRECTORY,API,CURRICULUM,REFERENCE,BankEpisodes,evaluate,score
from vector_physics import VectorPhysics
from run_fast_ppo import ROOT

STOP=False
def stop(signum,frame):
    global STOP
    STOP=True


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def actual_game_goal(output,threshold):
    proof=output/'verified-game.json'
    if not proof.exists():return False
    try:
        g=json.loads(proof.read_text())
        if g['status']!='GAME_FINISH_VERIFIED' or g['mapUid']!='ypPmohQofd72MyTsIsijKfrJH98':return False
        model=Path(g['model']);replay=Path(g['replay']);report=json.loads(Path(g['controlReport']).read_text())
        if sha(model)!=g['modelSha256'] or sha(replay)!=g['replaySha256']:return False
        if report['modelSha256']!=g['modelSha256'] or not report['workerReturnedNormally']:return False
        decoded=subprocess.run([str(ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'),'replay',str(replay)],check=True,capture_output=True,text=True)
        meta=json.loads(decoded.stdout)
        return (meta['mapUid']==g['mapUid'] and meta['respawns']==0
                and meta['declaredMs']==g['finishMs'] and 0<g['finishMs']<=threshold)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):return False


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--envs',type=int,default=32)
    p.add_argument('--rollout',type=int,default=2048);p.add_argument('--eval-every',type=int,default=8)
    p.add_argument('--patience',type=int,default=16);p.add_argument('--max-updates',type=int,default=0)
    p.add_argument('--decision-ticks',type=int,choices=(1,5),default=1)
    p.add_argument('--eval-count',type=int,default=41)
    p.add_argument('--eval-seed',type=int,default=99492)
    p.add_argument('--seed',type=int,default=994901);a=p.parse_args()
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    if not 1<=a.envs<=64 or not 4<=a.eval_count<=64 or a.rollout<1 or a.eval_every<1 or a.patience<1:raise ValueError('Invalid training dimensions')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(a.seed)
    a.output.mkdir(parents=True,exist_ok=True);lock=(a.output/'RUN.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    helpers=Helpers();prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',helpers)
    model=Policy(prior,'continuous');load_weights(model,a.source)
    threshold=json.loads((DIRECTORY/'leaderboard.json').read_text())['thresholdMs']
    lam=.995**(a.decision_ticks/5)
    cfg={'version':2,'algorithm':'PPO with complete-state reverse curriculum','decisionTicks':a.decision_ticks,
         'historyFrames':5,'inputs':240,'actions':'binary gas/brake, continuous i8 steer',
         'source':str(a.source.resolve()),'sourceSha256':sha(a.source),'targetMs':threshold,
         'mapUid':'ypPmohQofd72MyTsIsijKfrJH98','seed':a.seed,'envs':a.envs,'rollout':a.rollout,
         'evalCount':a.eval_count,'evalSeed':a.eval_seed,
         'selection':'finish count first, then complete-race penalized mean; DNF 40s',
         'vectorSha256':sha(API),'physicsSha256':sha(CURRICULUM),'referenceSha256':sha(REFERENCE),
         'learnerSha256':sha(Path(__file__)),'coreSha256':sha(Path(top10_core.__file__)),
         'updateSha256':sha(Path(ppo_time_credit.__file__)),
         'reward':'100-time, DNF compensates remaining 40s horizon; scale .01; gamma1',
         'lambda':lam,'bankWarmup':'four real decision periods on only the reset clone; teacher only during reset',
         'evaluation':'complete unassisted races from tick0; never treat bank finishes as full races',
         'stop':'STOP, signal, error, or real-game verified target; plateau changes curriculum/exploration',
         'onlineLeaderboardSubmission':False,'oldHourlyMonitor':False}
    protocol=a.output/'protocol.json'
    if protocol.exists() and json.loads(protocol.read_text())!=cfg:raise RuntimeError('Resume protocol changed')
    save_json(protocol,cfg)
    completed=0;phase=0;stale=0;best_update=0;best=None;loaded=None
    def optimizer():
        lr=(3e-7,1e-6,1e-7)[phase%3]
        return torch.optim.Adam([{'params':model.actor.parameters(),'lr':lr},
                                 {'params':model.critic.parameters(),'lr':3e-5},
                                 {'params':[model.logstd],'lr':lr}],eps=1e-8)
    optim=optimizer()
    if (a.output/'last.pt').exists():
        loaded=torch.load(a.output/'last.pt',map_location='cpu',weights_only=True)
        model.load_state_dict(loaded['model']);completed=loaded['update'];phase=loaded['phase']
        stale=loaded['stale'];best_update=loaded['bestUpdate'];best=loaded['best']
        optim=optimizer();optim.load_state_dict(loaded['optimizer'])
        torch.cuda.set_rng_state(loaded['cudaRng']);torch.set_rng_state(loaded['cpuRng'])
    episodes=BankEpisodes(a.envs,a.seed,bank_fraction=.8,bank_min=30,decision_ticks=a.decision_ticks)
    if loaded:
        episodes.bank_min=loaded['bankMin'];episodes.bank_fraction=loaded['bankFraction']
        episodes.episodes[:]=np.asarray(loaded['episodeCounters'],dtype=np.int64)
        for i in range(a.envs):episodes.reset(i)
        episodes.cuda_history=torch.as_tensor(episodes.history.copy(),device='cuda')
    evaluator=VectorPhysics(a.eval_count,decision_ticks=a.decision_ticks,api_path=API)
    seeds=[36139877]+[a.eval_seed*100+i for i in range(1,a.eval_count)]
    evaluation_rng=np.random.default_rng(a.eval_seed)
    perturbations=[{'warmMs':int(evaluation_rng.integers(0,21))*50,
                    'durationMs':int(evaluation_rng.integers(1,6))*50,
                    'steerKick':0. if i%4==0 else float(evaluation_rng.choice([-1,1])*evaluation_rng.uniform(.15,.5))}
                   for i in range(a.eval_count)]
    save_json(a.output/'evaluation-cases.json',{'seeds':seeds,'perturbations':perturbations})
    started=time.monotonic();run_transitions=0
    def save():
        atomic_torch(a.output/'last.pt',{'model':model.state_dict(),'optimizer':optim.state_dict(),
            'cpuRng':torch.get_rng_state(),'cudaRng':torch.cuda.get_rng_state().cpu(),
            'episodeCounters':episodes.episodes.tolist(),'update':completed,'phase':phase,'stale':stale,
            'bestUpdate':best_update,'best':best,'bankMin':episodes.bank_min,'bankFraction':episodes.bank_fraction})
    def select(result):
        nonlocal best,best_update,stale
        improved=best is None or score(result)>score(best)
        if improved:
            best=result;best_update=completed;stale=0
            atomic_torch(a.output/'best.pt',model.state_dict())
            path=a.output/'best-next.tmppo';path.unlink(missing_ok=True);model.export(prior,path,helpers,decision_ticks=a.decision_ticks);path.replace(a.output/'best.tmppo')
            save_json(a.output/'best-score.json',{'update':completed,**result})
        else:stale+=1
        return improved
    def status(stage,metrics=None):
        s={'state':stage,'update':completed,'transitions':completed*a.envs*a.rollout,'phase':phase,
           'bestUpdate':best_update,'best':best,'targetMs':threshold,'decisionHz':100//a.decision_ticks,
           'bankMinimum':episodes.bank_min,'bankFraction':episodes.bank_fraction,'bankResets':episodes.bank_resets,
           'sectionSuccessRate':float(np.mean(episodes.section_results)) if episodes.section_results else None,
           'evaluationsWithoutImprovement':stale,'wallSps':run_transitions/max(time.monotonic()-started,.001),
           'gpu':torch.cuda.get_device_name(),'pid':__import__('os').getpid(),'realGameVerified':stage=='goal_verified',
           'experimentalBranch':True,'protectedStableRun':'local/training/time-main-20261030',
           'stableRealGameReferenceMs':23366,
           'simulatedTimeTargetReached':bool(best and best['bestMs'] is not None and best['bestMs']<=threshold),
           'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        if metrics:s['lastUpdate']=metrics
        save_json(a.output/'status.json',s)
    try:
        if best is None:
            initial=evaluate(model,evaluator,seeds,perturbations);select(initial);print('BASELINE '+json.dumps(initial),flush=True)
        save();status('training')
        while not STOP and not (a.output/'STOP').exists() and (a.max_updates==0 or completed<a.max_updates):
            if actual_game_goal(a.output,threshold):status('goal_verified');break
            metrics=update(model,episodes,optim,a.rollout,gae_lambda=lam)
            completed+=1;run_transitions+=metrics['transitions']
            if completed%a.eval_every==0:
                result=evaluate(model,evaluator,seeds,perturbations);improved=select(result)
                event={'update':completed,'phase':phase,'improved':improved,'bankMin':episodes.bank_min,**result}
                with (a.output/'evaluations.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
                print('EVAL '+json.dumps(event),flush=True)
                # Earlier sections are introduced only as training sections
                # become consistently solvable. Global metrics remain full laps.
                if len(episodes.section_results)>=32 and np.mean(episodes.section_results)>=.85 and episodes.bank_min>1:
                    episodes.bank_min=max(1,episodes.bank_min-5);episodes.section_results=[]
                    print('CURRICULUM earliestBank='+str(episodes.bank_min),flush=True)
                if stale>=a.patience:
                    phase+=1;stale=0
                    load_weights(model,a.output/'best.pt')
                    with torch.no_grad():model.logstd.fill_(np.log((.015,.025,.008)[phase%3]))
                    optim=optimizer();episodes.bank_fraction=(.8,.6,.35)[phase%3]
                    print('PLATEAU phase='+str(phase)+' changed exploration/bank mixture; best protected',flush=True)
            save();status('training',metrics)
            if completed%2==0:print('UPDATE '+json.dumps({'update':completed,'sps':metrics['transitions']/metrics['seconds'],'phase':phase}),flush=True)
        save()
        if not actual_game_goal(a.output,threshold):status('stopped')
    except Exception as e:
        status('failed');raise
    finally:episodes.env.close();evaluator.close();lock.close()


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
