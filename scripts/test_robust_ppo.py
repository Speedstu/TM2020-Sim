#!/usr/bin/env python3
"""Selection and checkpoint lifecycle tests; no simulator or CUDA work."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch
from torch import nn
import robust_ppo as runner


class SmallPolicy(nn.Module):
    def __init__(self, prior=None, arm=None):
        super().__init__()
        self.actor = nn.Sequential(nn.Linear(240, 1, dtype=torch.float64))
        self.critic = nn.Linear(1, 1, dtype=torch.float64)
        self.logstd = nn.Parameter(torch.zeros((), dtype=torch.float64))
        with torch.no_grad():
            self.actor[0].weight.zero_()

    def export(self, prior, path, helpers):
        Path(path).write_bytes(b'owned-test-export')


class SmallEpisodes:
    def __init__(self, n, seed, **kwargs):
        self.n = n
        self.episodes = np.ones(n, dtype=np.int64)
        self.history = np.zeros((n, 240))
        self.env = SimpleNamespace(close=lambda: None)

    def reset(self, i):
        self.episodes[i] += 1


class SmallPool:
    def run(self, model, suite):
        trials = [{**c, 'finishMs': 10000} for c in suite]
        return {'trials': trials, **runner.summarize_trials(trials)}

    def close(self):
        pass


class RobustTests(unittest.TestCase):
    def test_trial_gate_requires_faster_and_no_regression(self):
        base={'finishes':255,'nominalFinishes':32,'meanWithDnf40sMs':24000.,'cvar90WithDnf40sMs':26500.}
        self.assertFalse(runner.qualifies_for_trial(base,base))
        fast={**base,'meanWithDnf40sMs':23900.}
        self.assertTrue(runner.qualifies_for_trial(fast,base))
        self.assertFalse(runner.qualifies_for_trial({**fast,'finishes':254},base))
        self.assertFalse(runner.qualifies_for_trial({**fast,'nominalFinishes':31},base))
        self.assertFalse(runner.qualifies_for_trial({**fast,'cvar90WithDnf40sMs':27000.},base))

    def test_slow_training_bank_is_bounded_and_graduates(self):
        episodes=runner.RecoveryEpisodes.__new__(runner.RecoveryEpisodes)
        episodes.hard_cases={}
        case=lambda seed:{'seed':seed,'perturb':{'warm':0,'duration':0,'steerKick':0.}}
        episodes.remember_slow_case(case(1),-1)
        self.assertEqual(len(episodes.hard_cases),0)
        episodes.remember_slow_case(case(1),30000)
        episodes.remember_slow_case(case(1),-1)
        self.assertEqual(next(iter(episodes.hard_cases.values()))['costMs'],40000)
        episodes.remember_slow_case(case(1),25000)
        self.assertEqual(len(episodes.hard_cases),0)
        for i in range(140):episodes.remember_slow_case(case(i),26000+i)
        self.assertEqual(len(episodes.hard_cases),128)
        self.assertEqual(min(c['costMs'] for c in episodes.hard_cases.values()),26012)

    def test_hard_replay_resets_complete_world_and_history(self):
        episodes=runner.RecoveryEpisodes.__new__(runner.RecoveryEpisodes)
        episodes.seed=85701;episodes.episodes=np.ones(1,dtype=np.int64)
        episodes.steps=np.zeros(1,dtype=np.int64);episodes.history=np.zeros((1,240))
        episodes.hard_replay_probability=1.;episodes.disturbance_probability=.4
        episodes.hard_cases={};episodes.hard_replay_count=0;episodes.perturb=[None]
        original={'seed':99,'perturb':{'warm':2,'duration':3,'steerKick':.2}}
        episodes.active_cases=[original]
        state=SimpleNamespace(terminated=1,truncated=0,finish_ms=30000)
        observations=np.zeros((1,48));resets=[]
        def reset_world(i,seed):
            resets.append(seed);observations[i,6]=(seed%100)*.01;state.terminated=0
        episodes.env=SimpleNamespace(states=[state],observations=observations,reset=reset_world)
        def reset_base(_,i):
            episodes.episodes[i]+=1
            reset_world(i,123)
        with patch.object(runner.CudaHistoryEpisodes,'reset',reset_base):episodes.reset(0)
        self.assertEqual(resets,[123,99])
        self.assertEqual(episodes.episodes[0],2)
        self.assertEqual(episodes.active_cases[0],original)
        self.assertEqual(episodes.hard_replay_count,1)
        np.testing.assert_array_equal(episodes.history[0],np.tile(observations[0],5))

    def test_invalid_weights_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'invalid.pt'
            model = SmallPolicy()
            with torch.no_grad():
                model.actor[0].weight[0, runner.MASK[0]] = 1.
            torch.save(model.state_dict(), path)
            with self.assertRaisesRegex(ValueError, 'unqualified'):
                runner.load_weights(SmallPolicy(), path)
            with torch.no_grad():
                model.actor[0].weight.zero_()
                model.actor[0].weight[0, 0] = float('nan')
            torch.save(model.state_dict(), path)
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                runner.load_weights(SmallPolicy(), path)

    def test_trials_and_selection(self):
        suite = runner.trial_suite(85200)
        self.assertEqual(suite, runner.trial_suite(85200))
        self.assertEqual(len({c['seed'] for c in suite}), 128)
        self.assertEqual(sum(c['group'] == 'nominal' for c in suite), 16)
        self.assertTrue(all(80 <= c['warm'] <= 360 for c in suite if c['group'] == 'midrace_recovery'))
        trials = [{**c, 'finishMs': 23000} for c in suite]
        base = runner.summarize_trials(trials)
        fast_failure = [{**t, 'finishMs': 21000} for t in trials]
        fast_failure[-1]['finishMs'] = None
        self.assertFalse(runner.better(runner.summarize_trials(fast_failure), base, 23100))
        faster = runner.summarize_trials([{**t, 'finishMs': 22000} for t in trials])
        self.assertTrue(runner.better(faster, base, 23100))
        self.assertFalse(runner.better({**faster, 'nominalMs': 23200}, base, 23100))
        self.assertFalse(runner.better({**base, 'bestMs': 18000}, base, 23100))
        self.assertFalse(runner.better({**faster, 'nominalFinishes': 15}, base, 23100))

    def test_recovery_schedule(self):
        episodes = runner.RecoveryEpisodes.__new__(runner.RecoveryEpisodes)
        episodes.seed = 85101
        episodes.disturbance_probability = .4
        episodes.episodes = np.zeros(1, dtype=np.int64)
        episodes.perturb = [None]
        def reset(_, i):
            episodes.episodes[i] += 1
        with patch.object(runner.CudaHistoryEpisodes, 'reset', reset):
            schedule = []
            for _ in range(1000):
                episodes.reset(0)
                schedule.append(episodes.perturb[0])
        disturbed = [c for c in schedule if c['duration']]
        late = [c for c in disturbed if c['warm'] >= 80]
        self.assertTrue(350 < len(disturbed) < 450)
        self.assertTrue(140 < len(late) < 260)

    def test_empty_stop_and_resume_completed_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source.pt'
            torch.save(SmallPolicy().state_dict(), source)
            base_argv = ['robust_ppo.py', '--source', str(source), '--output', str(root/'run'),
                         '--envs', '2', '--rollout', '4', '--eval-cases', '4',
                         '--skip-final-holdout']
            calls = []
            def update(model, episodes, optimizer, rollout, **kwargs):
                calls.append(1)
                runner.STOP_REQUESTED = True
                return {'transitions': episodes.n * rollout, 'seconds': 1.}
            original_as_tensor = torch.as_tensor
            def cpu_tensor(value, **kwargs):
                kwargs.pop('device', None)
                return original_as_tensor(value, **kwargs)
            with patch.object(runner, 'Policy', SmallPolicy), \
                 patch.object(runner, 'RecoveryEpisodes', SmallEpisodes), \
                 patch.object(runner, 'EvaluationPool', SmallPool), \
                 patch.object(runner, 'Helpers', lambda: None), \
                 patch.object(runner.Checkpoint, 'load', return_value=SimpleNamespace(nx=240, na=1, hidden=512)), \
                 patch.object(runner, 'digest', return_value='test-input-hash'), \
                 patch.object(runner, 'update', update), \
                 patch.object(torch.cuda, 'is_available', return_value=True), \
                 patch.object(torch.cuda, 'get_device_name', return_value='test-device'), \
                 patch.object(torch.cuda, 'get_rng_state', return_value=torch.zeros(8, dtype=torch.uint8)), \
                 patch.object(torch.cuda, 'set_rng_state'), \
                 patch.object(torch, 'as_tensor', side_effect=cpu_tensor):
                for limit, stop_before, expected in [(0, False, 0), (3, True, 0),
                                                     (3, False, 1), (3, False, 2)]:
                    runner.STOP_REQUESTED = stop_before
                    with patch.object(sys, 'argv', base_argv + ['--max-updates', str(limit)]):
                        runner.main()
                    saved = torch.load(root/'run/last.pt', weights_only=True)
                    status = json.loads((root/'run/status.json').read_text())
                    self.assertEqual(saved['update'], expected)
                    self.assertEqual(status['update'], expected)
                    self.assertEqual(status['transitions'], expected * 8)
                    self.assertEqual(status['state'], 'stopped')
                self.assertEqual(len(calls), 2)
            runner.STOP_REQUESTED = False


if __name__ == '__main__':
    unittest.main()
