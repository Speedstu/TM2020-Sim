"""Zero-perturbation parity; a declared launch perturbation acts once only."""
import ctypes as C
import json
from pathlib import Path
import numpy as np
from generalist_engine import GeneralistEngine
from run_fast_ppo import ROOT,steam_packs


def main():
    old=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so'
    new=ROOT/'cache/transfer-uncertainty-0.63-target/release/libtm2020_speed.so'
    map_path=ROOT/'local/campaign-2026-autumn/Autumn-2026-03.Map.Gbx'
    with GeneralistEngine(old,map_path,steam_packs()) as baseline,GeneralistEngine(new,map_path,steam_packs()) as changed:
        api=changed.lib;api.tmfast_launch_uncertainty.argtypes=[C.c_void_p,C.c_float]
        baseline.reset(123);changed.reset(123)
        changed.check(api.tmfast_launch_uncertainty(changed.handle,0.))
        for t in range(250):
            controls=[1.,float(90<=t<97),float(np.round(np.sin(t*.05)*40)/127)]
            a=baseline.step_controls(controls,repeat=1);b=changed.step_controls(controls,repeat=1)
            assert bytes(a)==bytes(b),(t,'Zero-noise physics changed')
        assert api.tmfast_launch_uncertainty(changed.handle,-.01)!=0,'Midrace configuration accepted'
        changed.reset(123);assert api.tmfast_launch_uncertainty(changed.handle,float('nan'))!=0
        assert api.tmfast_launch_uncertainty(changed.handle,.11)!=0
        changed.check(api.tmfast_launch_uncertainty(changed.handle,-.01))
        baseline.reset(123)
        for t in range(2):
            a=baseline.step_controls([1,0,0],repeat=1);b=changed.step_controls([1,0,0],repeat=1)
            va=np.array(a.rigid_words,dtype=np.uint32).view(np.float32);vb=np.array(b.rigid_words,dtype=np.uint32).view(np.float32)
            if t==0:assert np.array_equal(va,vb),'Noise applied before 20 ms'
            else:
                assert np.array_equal(va[9:12],vb[9:12]),'Perturbation altered position'
                assert abs(np.linalg.norm(va[16:19]-vb[16:19])-.01)<1e-6,'Wrong launch velocity delta'
    print(json.dumps({'zeroNoiseByteIdenticalSteps':250,'midraceConfigurationRejected':True,
        'nonfiniteOrLargeDeltaRejected':True,'appliedAt20msOnly':True,'gameAccessed':False}))


if __name__=='__main__':main()
