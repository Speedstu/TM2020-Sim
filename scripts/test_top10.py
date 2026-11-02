#!/usr/bin/env python3
"""Check cadence compatibility and physical isolation of curriculum resets."""
import unittest
import numpy as np
import torch
from compare_hybrid_ppo import Policy,frame,evaluate as legacy_evaluate,cases
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights
from run_fast_ppo import ROOT
from top10_core import API,BankEpisodes,evaluate,score
from vector_physics import VectorPhysics


class TopTenTests(unittest.TestCase):
    def test_completion_dominates_speed(self):
        def result(count,mean):
            return {'finishes':count,'penalizedMeanMs':mean,
                    'trials':[{'checkpoints':4}]*count}
        self.assertGreater(score(result(41,25000)),score(result(40,20100)))
        self.assertGreater(score(result(41,23000)),score(result(41,25000)))

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA required')
    def test_twenty_hz_matches_existing_evaluator(self):
        torch.set_num_threads(1)
        prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',Helpers())
        model=Policy(prior,'continuous')
        load_weights(model,ROOT/'local/training/time-main-20261030/best.pt')
        trial_cases=cases(99577,4)
        with VectorPhysics(4,api_path=API) as env:
            previous=legacy_evaluate(model,env,trial_cases)
            current=evaluate(model,env,[c['seed'] for c in trial_cases],
                             [{'warmMs':c['warm']*50,'durationMs':c['duration']*50,
                               'steerKick':c['steerKick']} for c in trial_cases])
        self.assertEqual([r['finishMs'] for r in previous['trials']],
                         [r['finishMs'] for r in current['trials']])
        self.assertEqual(previous['finishes'],current['finishes'])

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA required')
    def test_reset_warms_real_history_without_advancing_siblings(self):
        for period in (1,5):
            with self.subTest(period=period):
                episodes=BankEpisodes(4,99578,bank_fraction=1.,bank_min=30,decision_ticks=period)
                try:
                    before=[bytes(episodes.env.states[i]) for i in range(3)]
                    episodes.reset(3)
                    self.assertEqual(before,[bytes(episodes.env.states[i]) for i in range(3)])
                    state=episodes.env.states[3]
                    self.assertEqual(state.tick%50,4*period)
                    self.assertTrue(np.isfinite(episodes.history[3]).all())
                    # At speed, a physically warmed history must contain motion.
                    self.assertFalse(np.array_equal(episodes.history[3,:48],episodes.history[3,-48:]))
                    np.testing.assert_array_equal(episodes.history[3,-48:],frame(episodes.env.observations[3:4])[0])
                    reward,done=episodes.step(np.tile([1.,0.,0.],(4,1)))
                    self.assertTrue(np.isfinite(reward).all())
                finally:episodes.env.close()


if __name__=='__main__':unittest.main()
