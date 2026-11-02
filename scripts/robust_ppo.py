#!/usr/bin/env python3
"""Bounded CUDA PPO continuation with independent recovery trials and safe saves.

Simulation only. No game launcher, driving input, timer, or automatic restart.
The historical matched experiment and its update function remain unchanged.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time

import numpy as np
import torch

from compare_hybrid_ppo import MASK, Policy, cases, evaluate, save_json, frame
from ppo_time_credit import update, potential, shape_reward
from cuda_history import CudaHistoryEpisodes
from gpu_ppo import Checkpoint, Helpers
from run_fast_ppo import ROOT
from vector_physics import VectorPhysics

STOP_REQUESTED = False
PROFILES = {
    'precision': {'actorLr': 3e-7, 'criticLr': 3e-5},
    'conservative': {'actorLr': 1e-6, 'criticLr': 3e-5},
    'balanced': {'actorLr': 3e-6, 'criticLr': 3e-5},
}


def on_signal(signum, frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def atomic_torch(path, value):
    temp = path.with_name(path.name + '.tmp')
    torch.save(value, temp)
    os.replace(temp, path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize_trials(trials):
    times = [t['finishMs'] for t in trials if t['finishMs'] is not None]
    penalized = [t['finishMs'] if t['finishMs'] is not None else 40000 for t in trials]
    nominal_trials = [t for t in trials if t['group'] == 'nominal']
    nominal_times = [t['finishMs'] for t in nominal_trials if t['finishMs'] is not None]
    nominal = float(np.mean(nominal_times)) if nominal_times else None
    mean = float(np.mean(penalized))
    p90 = float(np.percentile(penalized, 90))
    cvar90 = float(np.mean(sorted(penalized)[-max(1, int(np.ceil(.1*len(penalized)))):]))
    return {
        'finishes': len(times), 'count': len(trials), 'finishRate': len(times) / len(trials),
        'meanMs': float(np.mean(times)) if times else None,
        'medianMs': float(np.median(times)) if times else None,
        'bestMs': min(times) if times else None, 'nominalMs': nominal,
        'nominalFinishes': len(nominal_times), 'nominalCount': len(nominal_trials),
        'nominalWorstMs': max(nominal_times) if nominal_times else None,
        'meanWithDnf40sMs': mean, 'p90WithDnf40sMs': p90,
        'cvar90WithDnf40sMs': cvar90,
        'selectionCostMs': mean + .15 * cvar90,
        'groups': {g: {'finishes': sum(t['finishMs'] is not None for t in trials if t['group'] == g),
                       'count': sum(t['group'] == g for t in trials)}
                   for g in sorted({t['group'] for t in trials})},
        'measuredInGame': False,
    }


def better(candidate, incumbent, nominal_limit, min_gain=25.):
    # A faster outlier must not displace a model with fewer failures. A fixed
    # nominal ceiling prevents improvements obtained only under injected kicks.
    nominal = candidate['nominalMs']
    if nominal is None or nominal > nominal_limit:
        return False
    if candidate['nominalFinishes'] < incumbent['nominalFinishes']:
        return False
    if candidate['finishes'] != incumbent['finishes']:
        return candidate['finishes'] > incumbent['finishes']
    return candidate['selectionCostMs'] < incumbent['selectionCostMs'] - min_gain


def trial_suite(seed, count=128):
    if count < 4 or count % 2:
        raise ValueError('Suite size must be even and at least four')
    nominal_count = max(1, count // 8)
    departure_count = (count - nominal_count) // 2
    recovery_count = count - nominal_count - departure_count
    nominal = [{'seed': int((seed * 10000 + i) % 4294967295), 'warm': 0,
                'duration': 0, 'steerKick': 0., 'group': 'nominal'} for i in range(nominal_count)]
    # Drop cases()'s single nominal entry: every departure case here is disturbed.
    first = cases(seed, departure_count + 1)[1:]
    for trial in first:
        trial['group'] = 'departure'
    rng = np.random.default_rng(seed + 1)
    recovery = [
        {'seed': int((seed + 1) * 100 + i), 'warm': int(rng.integers(80, 361)),
         'duration': int(rng.integers(1, 4)),
         'steerKick': float(rng.choice([-1, 1]) * rng.uniform(.04, .18)),
         'group': 'midrace_recovery'} for i in range(recovery_count)
    ]
    return nominal + first + recovery


class RecoveryEpisodes(CudaHistoryEpisodes):
    def __init__(self, n, seed, disturbance_probability=.4, reward_shaping='none', hard_replay_probability=0.):
        self.disturbance_probability = disturbance_probability
        self.reward_shaping = reward_shaping
        self.hard_replay_probability = hard_replay_probability
        self.hard_cases = {}
        self.active_cases = [None] * n
        self.hard_replay_count = 0
        super().__init__(n, seed)

    def remember_slow_case(self, case, finish_ms):
        key=json.dumps(case,sort_keys=True)
        # New entries come only from this trainer's successful slow episodes.
        # A failed repeat remains difficult; fast repeats graduate out of bank.
        if finish_ms < 0 and key not in self.hard_cases:
            return
        if 0 <= finish_ms < 26000:
            self.hard_cases.pop(key,None)
        else:
            self.hard_cases[key]={'case':copy.deepcopy(case),'costMs':int(finish_ms) if finish_ms>=0 else 40000}
        if len(self.hard_cases)>128:
            fastest=min(self.hard_cases,key=lambda k:(self.hard_cases[k]['costMs'],k))
            del self.hard_cases[fastest]

    def step(self, actions):
        before = potential(self.env.observations) if self.reward_shaping == 'potential' else None
        reward, done = super().step(actions)
        if before is not None:
            reward = shape_reward(reward, before, potential(self.env.observations), done)
        return reward, done

    def reset(self, i):
        replay_enabled=getattr(self,'hard_replay_probability',0.)>0.
        if replay_enabled and self.active_cases[i] is not None:
            state=self.env.states[i]
            if state.terminated or state.truncated:
                self.remember_slow_case(self.active_cases[i],state.finish_ms)
        super().reset(i)
        episode = int(self.episodes[i]) - 1
        rng = np.random.default_rng((self.seed * 100003 + i * 7919 + episode * 2654435761) % 4294967295)
        disturbance = {'warm': 0, 'duration': 0, 'steerKick': 0.}
        if rng.random() < self.disturbance_probability:
            late = rng.random() < .5
            disturbance = {
                'warm': int(rng.integers(80, 361) if late else rng.integers(0, 21)),
                'duration': int(rng.integers(1, 4) if late else rng.integers(1, 6)),
                'steerKick': float(rng.choice([-1, 1]) * rng.uniform(.04, .18) if late
                                   else rng.choice([-1, 1]) * rng.uniform(.15, .5)),
            }
        self.perturb[i] = disturbance
        if replay_enabled:
            seed=(self.seed*1000003+i*10007+episode*31337)%4294967295
            case={'seed':int(seed),'perturb':copy.deepcopy(disturbance)}
            if self.hard_cases and rng.random()<self.hard_replay_probability:
                values=list(self.hard_cases.values())
                case=copy.deepcopy(values[int(rng.integers(len(values)))]['case'])
                self.env.reset(i,case['seed'])
                self.history[i]=np.tile(frame(self.env.observations[i:i+1])[0],5)
                self.perturb[i]=copy.deepcopy(case['perturb'])
                self.hard_replay_count+=1
            self.active_cases[i]=case


class EvaluationPool:
    def __init__(self):
        self.batches = {}

    def run(self, model, suite):
        trials = []
        for offset in range(0, len(suite), 64):
            batch = suite[offset:offset + 64]
            if len(batch) not in self.batches:
                self.batches[len(batch)] = VectorPhysics(len(batch))
            result = evaluate(model, self.batches[len(batch)], batch)
            trials.extend(result['trials'])
        return {'trials': trials, **summarize_trials(trials)}

    def close(self):
        for batch in self.batches.values():
            batch.close()


def metadata(result):
    return {k: v for k, v in result.items() if k != 'trials'}


def qualifies_for_trial(candidate, reference):
    return (candidate['finishes'] >= reference['finishes']
            and candidate['nominalFinishes'] >= reference['nominalFinishes']
            and candidate['meanWithDnf40sMs'] <= reference['meanWithDnf40sMs']-25.
            and candidate['cvar90WithDnf40sMs'] <= reference['cvar90WithDnf40sMs']+25.)


def export_atomic(model, prior, path, helpers):
    temp = path.with_name(path.name + '.tmp')
    temp.unlink(missing_ok=True)
    model.export(prior, temp, helpers)
    os.replace(temp, path)


def load_weights(model, path):
    state = torch.load(path, map_location='cpu', weights_only=True)
    model.load_state_dict(state['model'] if 'model' in state else state)
    if not all(torch.isfinite(p).all().item() for p in model.parameters()):
        raise ValueError('Policy contains nonfinite parameters')
    inputs=model.actor[0].in_features
    if inputs not in (240,360):raise ValueError('Unsupported policy observation schema')
    mask=[f*(inputs//5)+channel for f in range(5) for channel in (13,14)]
    if torch.count_nonzero(model.actor[0].weight[:, mask]).item():
        raise ValueError('Policy consumes unqualified contact/turbo channels')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT/'local/training/best-tuned-20261030/best.pt')
    parser.add_argument('--prior', type=Path, default=ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint')
    parser.add_argument('--evaluate-models', type=Path, nargs='+')
    parser.add_argument('--profile', choices=PROFILES, default='balanced')
    parser.add_argument('--max-updates', type=int, default=512)
    parser.add_argument('--eval-every', type=int, default=8)
    parser.add_argument('--patience', type=int, default=10)
    parser.add_argument('--envs', type=int, default=32)
    parser.add_argument('--rollout', type=int, default=512)
    parser.add_argument('--seed', type=int, default=85101)
    parser.add_argument('--dev-seed', type=int, default=85200)
    parser.add_argument('--holdout-seed', type=int, default=86300)
    parser.add_argument('--eval-cases', type=int, default=128)
    parser.add_argument('--nominal-slack-ms', type=float, default=100.)
    parser.add_argument('--gae-lambda', type=float, default=.995)
    parser.add_argument('--reward-shaping', choices=('none', 'potential'), default='none')
    parser.add_argument('--hard-replay-probability', type=float, default=0.)
    parser.add_argument('--skip-final-holdout', action='store_true', help='Development pilots only')
    args = parser.parse_args()
    if not (1 <= args.envs <= 64 and args.rollout > 0 and args.max_updates >= 0
            and args.eval_every > 0 and args.patience > 0
            and 0. <= args.gae_lambda <= 1.
            and 0. <= args.hard_replay_probability <= 1.
            and np.isfinite(args.nominal_slack_ms) and args.nominal_slack_ms >= 0):
        raise ValueError('Invalid training limits')
    dev = trial_suite(args.dev_seed, args.eval_cases)
    if args.dev_seed == args.holdout_seed:
        raise ValueError('Development and final holdout seeds must differ')
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required; no CPU fallback')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    lock = (args.output/'RUN.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    helpers = Helpers()
    prior = Checkpoint.load(args.prior, helpers)
    if (prior.nx, prior.na, prior.hidden) != (240, 1, 512):
        raise ValueError('Expected qualified 240x512 prior')
    model = Policy(prior, 'continuous')
    pool = EvaluationPool()
    episodes = None
    try:
        if args.evaluate_models:
            if (args.output/'screening.json').exists():
                raise FileExistsError('Use a new screening output')
            results = []
            for source in args.evaluate_models:
                load_weights(model, source)
                result = pool.run(model, dev)
                item = {'source': str(source), 'sha256': digest(source), **result}
                results.append(item)
                save_json(args.output/'screening.json', {'suite': dev, 'results': results})
                print('SCREEN '+json.dumps({k: v for k, v in item.items() if k != 'trials'}), flush=True)
            return

        profile = PROFILES[args.profile]
        protocol = {
            'version': 3, 'profile': args.profile, 'optimizer': profile,
            'source': str(args.source.resolve()), 'sourceSha256': digest(args.source),
            'priorSha256': digest(args.prior), 'seed': args.seed,
            'devSeed': args.dev_seed, 'holdoutSeed': args.holdout_seed,
            'evalCases': args.eval_cases, 'envs': args.envs, 'rollout': args.rollout,
            'evalEvery': args.eval_every, 'patience': args.patience,
            'disturbanceProbability': .4, 'disturbanceMix': 'half early, half midrace',
            'hardReplayProbability': args.hard_replay_probability,
            'hardReplay': 'own training successful races >=26s; keep up to128 slow seeds/disturbances; fast repeats graduate; no validation cases',
            'reward': 'v3 pure time: finish 100-seconds, failure -140 over 40s; scale .01',
            'rewardShaping': args.reward_shaping,
            'potential': 'phi=-2*norm(observable local goal vector); gamma=1; terminal phi=0',
            'gaeLambda': args.gae_lambda,
            'selection': 'no regression in nominal finish count; finish count first, then mean(DNF=40s)+.15*mean(worst10%); fixed ceiling on nominal mean',
            'nominalSlackMs': args.nominal_slack_ms,
            'update': 'PPO: gamma=1 configurable GAE lambda; clip=.1 epochs<=4 KL guard=.0045',
            'physicsSha256': digest(ROOT/'cache/reward-study-target/release/libtm2020_speed.so'),
            'vectorSha256': digest(ROOT/'native/build-linux/libtm2020_vector_physics.so'),
            'mapSha256': digest(ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'),
            'runnerSha256': digest(Path(__file__)),
            'ppoUpdateSha256': digest(ROOT/'scripts/ppo_time_credit.py'),
            'policyImplementationSha256': digest(ROOT/'scripts/compare_hybrid_ppo.py'),
            'historySha256': digest(ROOT/'scripts/cuda_history.py'),
            'nativeWorkers': int(os.environ.get('TM2020_PHYSICS_WORKERS', '16')),
            'cudaHistory': True, 'physicsDevice': 'CPU', 'optimizerDevice': 'CUDA',
            'resume': 'optimizer and RNG restored; simulator episodes reset to next saved seed counters',
            'realGameFinishVerified': False,
        }
        protocol_path = args.output/'protocol.json'
        if protocol_path.exists() and json.loads(protocol_path.read_text()) != protocol:
            raise ValueError('Resume protocol changed; use a new output directory')
        save_json(protocol_path, protocol)
        optimizer = torch.optim.Adam([
            {'params': model.actor.parameters(), 'lr': profile['actorLr']},
            {'params': model.critic.parameters(), 'lr': profile['criticLr']},
            {'params': [model.logstd], 'lr': profile['actorLr']}], eps=1e-8)
        completed = 0
        stale = 0
        last_path = args.output/'last.pt'
        loaded = None
        if last_path.exists():
            loaded = torch.load(last_path, map_location='cpu', weights_only=True)
            if (args.output/'holdout.json').exists() and args.max_updates > int(loaded['update']):
                raise ValueError('Final cases already consumed; use a new output and fresh holdout seed for more training')
            model.load_state_dict(loaded['model'])
            optimizer.load_state_dict(loaded['optimizer'])
            completed = int(loaded['update'])
            stale = int(loaded['noGain'])
            incumbent = loaded['bestScore']
            nominal_limit = float(loaded['nominalLimitMs'])
            best_update = int(loaded['bestUpdate'])
            torch.set_rng_state(loaded['cpuRng'])
            torch.cuda.set_rng_state(loaded['cudaRng'])
        else:
            load_weights(model, args.source)
            initial = pool.run(model, dev)
            incumbent = metadata(initial)
            if initial['nominalMs'] is None:
                raise ValueError('Source does not finish nominal development trial')
            nominal_limit = initial['nominalMs'] + args.nominal_slack_ms
            best_update = 0
            atomic_torch(args.output/'best.pt', model.state_dict())
            export_atomic(model, prior, args.output/'best.tmppo', helpers)
            save_json(args.output/'baseline.json', initial)
            save_json(args.output/'best-score.json', {'update': 0, **initial})
            print('BASELINE '+json.dumps(incumbent), flush=True)

        episodes = RecoveryEpisodes(args.envs, args.seed, reward_shaping=args.reward_shaping,
                                    hard_replay_probability=args.hard_replay_probability)
        if loaded is not None:
            episodes.hard_cases=loaded.get('hardCases',{})
            episodes.hard_replay_count=int(loaded.get('hardReplayCount',0))
            episodes.episodes[:] = np.asarray(loaded['episodeCounters'], dtype=np.int64)
            for i in range(args.envs):
                episodes.reset(i)
            episodes.cuda_history = torch.as_tensor(episodes.history.copy(), device='cuda')
        reason = 'update budget'
        started = time.monotonic()
        run_transitions = 0

        def checkpoint():
            atomic_torch(last_path, {
                'model': model.state_dict(), 'optimizer': optimizer.state_dict(),
                'cpuRng': torch.get_rng_state(), 'cudaRng': torch.cuda.get_rng_state().cpu(),
                'episodeCounters': episodes.episodes.tolist(), 'update': completed,
                'hardCases': getattr(episodes,'hard_cases',{}),
                'hardReplayCount': getattr(episodes,'hard_replay_count',0),
                'noGain': stale, 'bestUpdate': best_update, 'bestScore': incumbent,
                'nominalLimitMs': nominal_limit, 'protocol': protocol,
            })

        def status(state, metrics=None):
            value = {
                'state': state, 'update': completed,
                'transitions': completed * args.envs * args.rollout,
                'runTransitions': run_transitions,
                'wallSpsIncludingEvaluations': run_transitions / max(time.monotonic()-started, .001),
                'profile': args.profile, 'bestUpdate': best_update, 'best': incumbent,
                'noGainEvaluations': stale, 'patience': args.patience,
                'device': torch.cuda.get_device_name(), 'physicsDevice': 'CPU',
                'hardReplayBankSize': len(getattr(episodes,'hard_cases',{})),
                'hardReplayCount': getattr(episodes,'hard_replay_count',0),
                'reason': reason if state == 'stopped' else None,
                'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'pid': os.getpid(), 'realGameFinishVerified': False,
            }
            if metrics:
                value['lastUpdate'] = metrics
            save_json(args.output/'status.json', value)

        checkpoint()
        status('training')
        while completed < args.max_updates:
            if STOP_REQUESTED or (args.output/'STOP').exists():
                reason = 'requested stop'
                break
            if stale >= args.patience:
                reason = 'plateau'
                break
            metrics = update(model, episodes, optimizer, args.rollout, gae_lambda=args.gae_lambda)
            completed += 1
            run_transitions += metrics['transitions']
            metrics['sps'] = metrics['transitions'] / metrics['seconds']
            if completed % args.eval_every == 0 or completed == args.max_updates:
                score = pool.run(model, dev)
                improved = better(score, incumbent, nominal_limit)
                if improved:
                    incumbent = metadata(score)
                    best_update = completed
                    stale = 0
                    atomic_torch(args.output/'best.pt', model.state_dict())
                    export_atomic(model, prior, args.output/'best.tmppo', helpers)
                    save_json(args.output/'best-score.json', {'update': completed, **score})
                else:
                    stale += 1
                event = {'update': completed, 'improved': improved, 'noGain': stale, **metadata(score)}
                with (args.output/'evaluations.jsonl').open('a') as stream:
                    stream.write(json.dumps(event)+'\n')
                print('EVAL '+json.dumps(event), flush=True)
            checkpoint()
            status('training', metrics)
            if completed % 4 == 0:
                print('UPDATE '+json.dumps({'update': completed, **metrics}), flush=True)
        if stale >= args.patience:
            reason = 'plateau'
        checkpoint()
        # The untouched final suite is evaluated once, after selection ends.
        if not args.skip_final_holdout and reason != 'requested stop':
            best_model = copy.deepcopy(model)
            load_weights(best_model, args.output/'best.pt')
            held = pool.run(best_model, trial_suite(args.holdout_seed, args.eval_cases))
            save_json(args.output/'holdout.json', {'bestUpdate': best_update, **held})
            reference_model=copy.deepcopy(best_model)
            load_weights(reference_model,args.source)
            reference=pool.run(reference_model,trial_suite(args.holdout_seed,args.eval_cases))
            save_json(args.output/'holdout-reference.json',reference)
            save_json(args.output/'trial-qualification.json',{
                'candidate':metadata(held),'reference':metadata(reference),
                'sourceSha256':protocol['sourceSha256'],
                'candidateSha256':digest(args.output/'best.pt'),
                'acceptedForNextGameTrial':bool(best_update>0 and qualifies_for_trial(held,reference)),
                'realGameVerified':False,
                'criterion':'no completion regression; penalized mean at least25ms faster; worst10% mean no more than25ms worse',
            })
            print('HOLDOUT '+json.dumps(metadata(held)), flush=True)
        status('stopped')
        print('STOP '+json.dumps({'reason': reason, 'update': completed, 'bestUpdate': best_update}), flush=True)
    except Exception as error:
        if not args.evaluate_models:
            status_path = args.output/'status.json'
            previous = json.loads(status_path.read_text()) if status_path.exists() else {}
            save_json(status_path, {**previous, 'state': 'failed', 'error': str(error),
                                   'updatedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z')})
        raise
    finally:
        pool.close()
        if episodes is not None:
            episodes.env.close()
        lock.close()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    main()
