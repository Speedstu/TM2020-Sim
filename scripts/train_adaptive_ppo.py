#!/usr/bin/env python3
"""Matched PPO ablations or persistent own-state training with independent gates."""
import argparse
import copy
import fcntl
import hashlib
import json
import signal
import time
from pathlib import Path
import numpy as np
import torch
from compare_hybrid_ppo import Policy,save_json
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights,atomic_torch,trial_suite
from ppo_time_credit import update
from preview_ppo import PreviewPolicy,OwnEpisodes,physics,evaluate,LIBRARY,API
from run_fast_ppo import ROOT
from finish_evidence import verified_goal

STOP=False
def stop(*_):
    global STOP
    STOP=True


PROFILES={
 'control':{'preview':False,'bank':0.,'temperature':1.},
 'own':{'preview':False,'bank':.5,'temperature':1.},
 'pedals':{'preview':False,'bank':0.,'temperature':.5},
 'own-pedals':{'preview':False,'bank':.5,'temperature':.5},
 'preview':{'preview':True,'bank':.5,'temperature':.5},
 'preview-explore':{'preview':True,'bank':.5,'temperature':.5,'sigma':.05},
}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_model(prior,source,profile):
    if profile['preview']:model=PreviewPolicy(prior,source,profile['temperature'])
    else:
        model=Policy(prior,'continuous');load_weights(model,source);model.pedal_temperature=profile['temperature']
    if 'sigma' in profile:
        with torch.no_grad():model.logstd.fill_(np.log(profile['sigma']))
    return model


def key(result):return result['finishes'],-result['selectionCostMs']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--profile',choices=PROFILES,required=True)
    p.add_argument('--seed',type=int,default=99701);p.add_argument('--eval-seed',type=int,default=99720)
    p.add_argument('--holdout-seed',type=int,default=99820);p.add_argument('--updates',type=int,default=16)
    p.add_argument('--envs',type=int,default=16);p.add_argument('--rollout',type=int,default=512)
    p.add_argument('--eval-count',type=int,default=64);p.add_argument('--eval-every',type=int,default=4)
    p.add_argument('--patience',type=int,default=12);p.add_argument('--actor-lr',type=float,default=3e-7)
    p.add_argument('--snapshots-per-bin',type=int,default=4)
    a=p.parse_args();profile=PROFILES[a.profile]
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    if not 1<=a.envs<=64 or not 4<=a.eval_count<=64 or a.eval_count%2 or a.rollout<1:raise ValueError('Invalid dimensions')
    if a.updates<0 or a.eval_every<1 or a.patience<1:raise ValueError('Invalid budget')
    a.output.mkdir(parents=True,exist_ok=True);lock=(a.output/'RUN.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(a.seed)
    helpers=Helpers();prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',helpers)
    model=make_model(prior,a.source,profile);reference=copy.deepcopy(model)
    cfg={'version':1,'profile':profile,'name':a.profile,'source':str(a.source.resolve()),'sourceSha256':sha(a.source),
         'seed':a.seed,'evalSeed':a.eval_seed,'holdoutSeed':a.holdout_seed,'envs':a.envs,'rollout':a.rollout,
         'updates':a.updates,'evalEvery':a.eval_every,'patience':a.patience,'actorLr':a.actor_lr,
         'decisionMs':50,'reward':'native minimum-time v3 unchanged; gamma1 lambda.995 scale.01',
         'librarySha256':sha(LIBRARY),'apiSha256':sha(API),'learnerSha256':sha(__file__),
         'checkpointSampling':'16 separate 2s reservoirs; own full-start policy only',
         'snapshotsPerBin':a.snapshots_per_bin,
         'mapSha256':sha(ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'),
         'priorSha256':sha(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint'),
         'holdoutUsedForTraining':False,'realGameVerified':False,'oldHourlyMonitor':False}
    protocol=a.output/'protocol.json'
    if protocol.exists() and json.loads(protocol.read_text())!=cfg:raise RuntimeError('Resume protocol changed')
    save_json(protocol,cfg)
    def optimizer():return torch.optim.Adam([{'params':model.actor.parameters(),'lr':a.actor_lr},
        {'params':model.critic.parameters(),'lr':3e-5},{'params':[model.logstd],'lr':a.actor_lr}],eps=1e-8)
    optim=optimizer();completed=0;best=None;best_update=0;stale=0;phase=0
    loaded=None
    if (a.output/'last.pt').exists():
        loaded=torch.load(a.output/'last.pt',map_location='cpu',weights_only=True)
        model.load_state_dict(loaded['model']);optim.load_state_dict(loaded['optimizer'])
        completed=loaded['update'];best=loaded['best'];best_update=loaded['bestUpdate'];stale=loaded['stale'];phase=loaded['phase']
    # Expansion initializes extra zero-weight columns but must not change the
    # initial sampling stream in a matched observation ablation.
    torch.manual_seed(a.seed)
    episodes=OwnEpisodes(a.envs,a.seed,profile['bank'],profile['preview'],a.snapshots_per_bin)
    if loaded:
        episodes.bank_fraction=loaded.get('bankFraction',profile['bank'])
        episodes.episodes[:]=np.asarray(loaded['episodeCounters'])
        for i in range(a.envs):episodes.reset(i)
        episodes.cuda_history=torch.as_tensor(episodes.history.copy(),device='cuda')
        torch.cuda.set_rng_state(loaded['cudaRng']);torch.set_rng_state(loaded['cpuRng'])
    evaluator=physics(a.eval_count);cases=trial_suite(a.eval_seed,a.eval_count)
    save_json(a.output/'development-cases.json',cases)
    started=time.monotonic();run_transitions=0;goal=False
    def save():
        atomic_torch(a.output/'last.pt',{'model':model.state_dict(),'optimizer':optim.state_dict(),'update':completed,
          'best':best,'bestUpdate':best_update,'stale':stale,'phase':phase,
          'bankFraction':episodes.bank_fraction,
          'cpuRng':torch.get_rng_state(),'cudaRng':torch.cuda.get_rng_state().cpu(),'episodeCounters':episodes.episodes.tolist()})
    def select(result):
        nonlocal best,best_update,stale
        # Do not promote a faster subset or nominal regression.
        improved=(best is None or (result['nominalFinishes']>=best['nominalFinishes'] and
                  key(result)>key(best) and result['nominalMs']<=baseline['nominalMs']+25))
        if improved:
            best=result;best_update=completed;stale=0
            atomic_torch(a.output/'best.pt',model.state_dict())
            target=a.output/'next.tmppo';target.unlink(missing_ok=True);model.export(prior,target,helpers);target.replace(a.output/'best.tmppo')
            save_json(a.output/'best-score.json',{'update':completed,**best})
        else:stale+=1
        return improved
    def status(stage,metrics=None):
        save_json(a.output/'status.json',{'state':stage,'profile':a.profile,'update':completed,'transitions':completed*a.envs*a.rollout,
          'bestUpdate':best_update,'best':best,'phase':phase,'stale':stale,'checkpointResets':episodes.bank_restores,
          'checkpointSaves':episodes.saved,'checkpointBins':sorted({k//16 for k in episodes.records}),
          'activeSnapshots':len(episodes.records),'wallSps':run_transitions/max(.001,time.monotonic()-started),
          'gpu':torch.cuda.get_device_name(),'pedalTemperature':model.pedal_temperature,'lastUpdate':metrics,
          'bankFraction':episodes.bank_fraction,
          'realGameVerified':stage=='goal_verified','updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')})
    try:
        baseline_path=a.output/'baseline.json'
        if baseline_path.exists():baseline=json.loads(baseline_path.read_text())
        else:
            baseline=evaluate(reference,evaluator,cases,profile['preview']);save_json(baseline_path,baseline)
        if best is None:select(baseline)
        status('training');save()
        while not STOP and not (a.output/'STOP').exists() and (a.updates==0 or completed<a.updates):
            if verified_goal(a.output):goal=True;break
            metrics=update(model,episodes,optim,a.rollout);completed+=1;run_transitions+=metrics['transitions']
            if completed%a.eval_every==0:
                result=evaluate(model,evaluator,cases,profile['preview']);improved=select(result)
                event={'update':completed,'improved':improved,'phase':phase,**result}
                with (a.output/'evaluations.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
                print('EVAL '+json.dumps({k:v for k,v in event.items() if k!='trials'}),flush=True)
                if stale>=a.patience:
                    if a.updates:break
                    phase+=1;stale=0;load_weights(model,a.output/'best.pt');optim=optimizer()
                    # Bounded phases; vary coherent reset coverage, not a WR-time gate.
                    episodes.bank_fraction=(.5,.25,0.)[phase%3]
                    with torch.no_grad():model.logstd.fill_(np.log((.025,.05,.0125)[phase%3]))
                    print('PLATEAU '+str(phase)+' restored incumbent; new own-state/exploration phase',flush=True)
            save();status('training',metrics)
            if completed%2==0:print('UPDATE '+json.dumps({'update':completed,'sps':metrics['transitions']/metrics['seconds']}),flush=True)
        save();status('goal_verified' if goal else 'stopped')
        if a.updates and not STOP and not (a.output/'STOP').exists():
            load_weights(model,a.output/'best.pt');holdout=trial_suite(a.holdout_seed,a.eval_count)
            final=evaluate(model,evaluator,holdout,profile['preview']);base=evaluate(reference,evaluator,holdout,profile['preview'])
            qualified=(final['finishes']>=base['finishes'] and final['nominalFinishes']>=base['nominalFinishes']
              and final['meanWithDnf40sMs']<=base['meanWithDnf40sMs']-25
              and final['cvar90WithDnf40sMs']<=base['cvar90WithDnf40sMs']+25)
            save_json(a.output/'qualification.json',{'candidate':final,'source':base,'qualifiedForGameTrial':qualified,
              'realGameVerified':False,'holdoutSeed':a.holdout_seed,'candidateSha256':sha(a.output/'best.tmppo')})
            print('QUALIFIED '+str(qualified),flush=True)
    except Exception:status('failed');raise
    finally:episodes.env.close();evaluator.close();lock.close()


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
