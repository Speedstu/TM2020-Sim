"""A qualification from the old late hook cannot arm an early-hook controller."""
import unittest
from run_internal_live import check_observed_assets


class RuntimeIdentity(unittest.TestCase):
    def test_exact_runtime_map_spawn_required(self):
        q={'workerReturnedNormally':True,'dllSha256':'early-runtime',
           'mapSha256':'map06','spawn':[1.,2.,3.]}
        check_observed_assets(q,'early-runtime','map06',[1.,2.,3.])
        for values in ({'dllSha256':'late-runtime'},{'mapSha256':'other-map'},
                       {'spawn':[1.,2.,4.]},{'workerReturnedNormally':False}):
            with self.assertRaises(RuntimeError):
                check_observed_assets(dict(q,**values),'early-runtime','map06',[1.,2.,3.])
        with self.assertRaises(RuntimeError):check_observed_assets(q,'early-runtime','map06',[1.,2.,3.],True)
        upstream=dict(q,inputRecordingRequested=True)
        check_observed_assets(upstream,'early-runtime','map06',[1.,2.,3.],True)
        with self.assertRaises(RuntimeError):check_observed_assets(upstream,'early-runtime','map06',[1.,2.,3.])


if __name__=='__main__':unittest.main()
