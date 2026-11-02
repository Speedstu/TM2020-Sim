#!/usr/bin/env python3
import unittest
import numpy as np
import torch
from compare_hybrid_ppo import Policy,quantized
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights
from run_fast_ppo import ROOT
from preview_ppo import PreviewPolicy,OwnEpisodes,physics,evaluate

SOURCE=ROOT/'local/training/top10-20261030/ppo20/best.pt'


class PreviewTests(unittest.TestCase):
    def test_full_checkpoint_restore_preserves_future_and_siblings(self):
        with physics(2) as env:
            env.reset(0,99661);env.reset(1,99662)
            for _ in range(30):env.step(np.array([[1,0,.1],[1,0,-.1]]))
            env.save_checkpoint(0,0);at_save=env.preview()[0].copy();tick=env.states[0].tick
            sequence=[np.array([1,0,.1*np.sin(i)],np.float32) for i in range(25)]
            for action in sequence:env.step(np.stack((action,action)))
            expected=list(env.states[0].rigid_words);expected_preview=env.preview()[0].copy()
            sibling=bytes(env.states[0]);env.restore_checkpoint(1,0,99661)
            self.assertEqual(sibling,bytes(env.states[0]));self.assertEqual(tick,env.states[1].tick)
            np.testing.assert_array_equal(env.preview()[1],at_save)
            for action in sequence:env.step(np.stack((action,action)))
            self.assertEqual(expected,list(env.states[1].rigid_words))
            np.testing.assert_array_equal(env.preview()[1],expected_preview)
            with self.assertRaises(RuntimeError):env.restore_checkpoint(0,255,1)

    def test_preview_preserves_all_qualified_legacy_features(self):
        with physics(2) as env:
            for i in range(2):env.reset(i,99671+i)
            for step in range(80):
                env.step(np.array([[1,0,.15],[1,0,-.15]]));x=env.preview()
                base=env.observations.copy();base[:,13:15]=0.
                np.testing.assert_array_equal(x[:,:48],base)
                self.assertTrue(np.isfinite(x).all())

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA required')
    def test_transfer_has_identical_complete_race_controls(self):
        torch.set_num_threads(1)
        prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',Helpers())
        source=Policy(prior,'continuous');load_weights(source,SOURCE)
        # Pin the exact source used by both models even if training promotes.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path=__import__('pathlib').Path(tmp)/'source.pt';torch.save(source.state_dict(),path)
            model=PreviewPolicy(prior,path,pedal_temperature=.5)
        cases=[{'seed':9968100+i,'warm':0,'duration':0,'steerKick':0.,'group':'nominal'} for i in range(4)]
        with physics(4) as env:
            before=evaluate(source,env,cases,preview=False);after=evaluate(model,env,cases)
        self.assertEqual([r['finishMs'] for r in before['trials']],[r['finishMs'] for r in after['trials']])
        x=torch.randn((32,360),device='cuda',dtype=torch.float64)*.1
        with torch.no_grad():
            _,z,lp,_=model.action(x)
            self.assertLess((model.logp(x,z)-lp).abs().max().item(),1e-10)
        for frame in range(5):self.assertEqual(torch.count_nonzero(model.actor[0].weight[:,frame*72+48:(frame+1)*72]).item(),0)

    @unittest.skipUnless(torch.cuda.is_available(),'CUDA required')
    def test_own_resets_keep_actual_history_and_do_not_use_expert(self):
        episodes=OwnEpisodes(4,99691,bank_fraction=.7)
        try:
            for _ in range(180):
                episodes.step(np.tile([1.,0.,.03],(4,1)))
                np.testing.assert_array_equal(episodes.history,episodes.cuda_history.cpu().numpy())
            self.assertGreater(episodes.saved,0)
            episodes.bank_fraction=1.
            before=[bytes(episodes.env.states[i]) for i in range(3)]
            episodes.reset(3)
            self.assertEqual(before,[bytes(episodes.env.states[i]) for i in range(3)])
            self.assertTrue(episodes.from_bank[3]);self.assertGreater(episodes.bank_restores,0)
        finally:episodes.env.close()


if __name__=='__main__':unittest.main()
