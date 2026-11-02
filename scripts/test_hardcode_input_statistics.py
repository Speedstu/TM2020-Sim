"""Verify the hardcoded controller reports its actual 100Hz input stream."""
import json
import unittest
from hybrid_tracking import load_asset
from tune_hybrid_tracking import NativeEvaluator
from train_hardcode_recorded_inputs import BASE,NATIVE,PHYSICS,ROOT

class ExecutableInputStatistics(unittest.TestCase):
    def test_real_native_rollout_emits_quantized_control_rhythm(self):
        meta=json.loads((ROOT/'local/training/fall-campaign-0.52/01/map.json').read_text())
        asset=next((BASE/'preserved/01').glob('*.tmhyb'))
        ref,g,_=load_asset(asset,map_path=meta['map'],uid=meta['mapUid'])
        ev=NativeEvaluator(1,asset,api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
            map_path=meta['map'],horizon=len(ref)+600,fast_evaluation=True)
        try:rows,_=ev.evaluate(g,[{'seed':36139877,'warm':0,'duration':0,'kick':0.}])
        finally:ev.close()
        row=rows[0];stats=row['inputs']
        self.assertEqual(stats['ticks'],row['tick'])
        self.assertGreater(stats['steeringChangesPerSecond'],0)
        self.assertEqual(len(stats['steeringHoldMsP10P50P90']),3)
        self.assertEqual(len(stats['gasPressMsP10P50P90']),3)
        self.assertEqual(stats['brakePressMsP10P50P90'],[])
        self.assertEqual(stats['brakeDuty'],0.)
        self.assertTrue(all(float(v).is_integer() for v in stats['rawSteeringStepP50P95P99']))
        self.assertEqual(row['finishMs'],19987)

if __name__=='__main__':unittest.main()
