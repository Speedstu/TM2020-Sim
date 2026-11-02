"""Local repairs preserve successful prefixes and nominal candidate progress."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from hybrid_tracking import retime_pedals
from optimize_fall_campaign import deform_local,update_search_spread
from pursue_campaign_records import development_key,adopt_candidate,repair_window


class LocalSearch(unittest.TestCase):
    def test_pedal_baseline_grid_does_not_erase_initial_steering_exploration(self):
        elite=np.zeros((4,40));initial=np.ones(40)*.08;minimum=np.ones(40)*.01
        first=update_search_spread(elite,minimum,initial,0)
        later=update_search_spread(elite,minimum,initial,1)
        self.assertTrue(np.array_equal(first,initial))
        self.assertTrue(np.array_equal(later,minimum))

    def test_local_kernels_preserve_every_byte_outside_the_window(self):
        rng=np.random.default_rng(67001);ref=rng.normal(size=(1000,25)).astype(np.float32)
        ref[:,24]=rng.uniform(-1,1,1000);p=np.zeros(39);p[:32]=rng.normal(size=32)*.1
        changed=deform_local(ref,p,(500,800))
        self.assertEqual(changed[:500].tobytes(),ref[:500].tobytes())
        self.assertEqual(changed[801:].tobytes(),ref[801:].tobytes())
        self.assertFalse(np.array_equal(changed[550:750],ref[550:750]))

    def test_pedal_timing_is_binary_local_and_preserves_launch(self):
        ref=np.zeros((100,25),dtype=np.float32);ref[:,22]=1;ref[50:60,23]=1
        shifted=retime_pedals(ref,-2,0,40,80)
        self.assertEqual(shifted[:40].tobytes(),ref[:40].tobytes())
        self.assertEqual(shifted[80:].tobytes(),ref[80:].tobytes())
        self.assertEqual(np.flatnonzero(shifted[:,23]).tolist(),list(range(48,58)))
        self.assertTrue(set(np.unique(shifted[:,22:24])).issubset({0.,1.}))

    def test_brake_release_can_change_without_moving_its_onset(self):
        ref=np.zeros((100,25),dtype=np.float32);ref[:,22]=1;ref[50:60,23]=1
        longer=retime_pedals(ref,0,0,40,80,3)
        shorter=retime_pedals(ref,0,0,40,80,-2)
        self.assertEqual(np.flatnonzero(longer[:,23]).tolist(),list(range(50,63)))
        self.assertEqual(np.flatnonzero(shorter[:,23]).tolist(),list(range(50,58)))
        self.assertEqual(longer[:40].tobytes(),ref[:40].tobytes())
        self.assertEqual(longer[80:].tobytes(),ref[80:].tobytes())

    def test_perturbed_progress_cannot_replace_a_better_nominal_prefix(self):
        def result(rows):return {'development':{'finishes':0,'trials':rows}}
        nominal={'finishMs':None,'checkpoints':9,'maximumReferenceIndex':4700}
        regressed={'finishMs':None,'checkpoints':6,'maximumReferenceIndex':3300}
        self.assertGreater(development_key(result([nominal]*4)),development_key(result([regressed,nominal,nominal,dict(nominal,checkpoints=30)])))

    def test_repair_window_follows_first_nominal_case(self):
        s={'selected':{'development':{'trials':[{'finishMs':None,'maximumReferenceIndex':1513},
            {'finishMs':None,'maximumReferenceIndex':3000}]}}}
        self.assertEqual(repair_window(s,3690),(863,1663))

    def test_incoming_qualified_candidate_is_frozen_and_wrong_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);model=root/'candidate.tmhyb';model.write_bytes(b'owned candidate bytes')
            d=root/'02';d.mkdir();goal={'mapUid':'owned-map','mapSha256':'mapsha','top10TargetMs':11000,'top1TargetMs':9999}
            result={'map':dict(goal),'model':str(model),'modelSha256':hashlib.sha256(model.read_bytes()).hexdigest(),
                'nominal64':{'count':64,'finishes':64,'worstMs':10500},
                'development':{'finishes':4,'meanMs':10500,'trials':[{'finishMs':10500}]}}
            state={'selected':None,'resumeAsset':'superseded model'}
            self.assertTrue(adopt_candidate(state,result,goal,d));self.assertNotIn('resumeAsset',state)
            model.write_bytes(b'changed')
            with self.assertRaises(ValueError):adopt_candidate(state,result,goal,d)
            self.assertEqual(Path(state['bestAsset']).read_bytes(),b'owned candidate bytes')


if __name__=='__main__':unittest.main()
