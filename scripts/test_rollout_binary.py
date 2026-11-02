"""Lossless rollout transport and rejection of truncated/mismatched records."""
from pathlib import Path
import struct
import tempfile
import unittest
import numpy as np
from gpu_ppo import read_rollout


class BinaryRolloutTests(unittest.TestCase):
    def test_binary_and_text_have_identical_gae_in_both_action_schemas(self):
        rng=np.random.default_rng(43)
        for na in (1,3):
            data=rng.normal(size=(12,7+48+na))
            data[:,4:6]=0;data[:,6]=1;data[5,4]=1;data[9,5]=1;data[-2:,5]=1
            with tempfile.TemporaryDirectory() as d:
                binary=Path(d)/'rollout.bin';csv=Path(d)/'rollout.csv'
                binary.write_bytes(b'TMROLL01'+struct.pack('<IIQ',48,na,len(data))+data.astype('<f8').tobytes())
                np.savetxt(csv,data,delimiter=',',header='columns',comments='',fmt='%.17g')
                for gamma,lam in ((1.,1.),(.999,.97)):
                    expected=read_rollout(csv,48,na,2,gamma,lam);actual=read_rollout(binary,48,na,2,gamma,lam)
                    for key in expected:np.testing.assert_array_equal(expected[key],actual[key])

    def test_invalid_binary_records_are_rejected(self):
        data=np.zeros((2,56),dtype='<f8');data[:,6]=1
        good=b'TMROLL01'+struct.pack('<IIQ',48,1,2)+data.tobytes()
        for content in (good[:-1],good+b'X',b'TMROLL01',b'TMROLL01'+struct.pack('<IIQ',49,1,2)+data.tobytes()):
            with tempfile.TemporaryDirectory() as d:
                path=Path(d)/'bad.bin';path.write_bytes(content)
                with self.assertRaises(ValueError):read_rollout(path,48,1,2,1.,1.)


if __name__=='__main__':unittest.main()
