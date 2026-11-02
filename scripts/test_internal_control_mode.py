#!/usr/bin/env python3
"""Verify direct commands preserve device history and reset/clone semantics."""
import ctypes as C
import json
import numpy as np
from generalist_engine import GeneralistEngine
from run_fast_ppo import ROOT,steam_packs


def main():
    lib=ROOT/'cache/internal-control-0.54-target/release/libtm2020_speed.so'
    map_path=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'
    reference=np.fromfile(ROOT/'local/training/fall-campaign-0.52/01/reference.f32',dtype='<f4').reshape(-1,25)
    counts={}
    for mode in (0,1):
        with GeneralistEngine(lib,map_path,steam_packs(),horizon=4000) as env:
            dll=env.lib
            dll.tmfast_set_control_mode.argtypes=[C.c_void_p,C.c_uint32]
            dll.tmfast_control_mode.argtypes=[C.c_void_p];dll.tmfast_control_mode.restype=C.c_uint32
            dll.tmfast_input_adjustments.argtypes=[C.c_void_p];dll.tmfast_input_adjustments.restype=C.c_uint32
            env.check(dll.tmfast_set_control_mode(env.handle,mode))
            env.reset(36139877)
            assert dll.tmfast_control_mode(env.handle)==mode
            assert dll.tmfast_set_control_mode(env.handle,2)!=0
            for t in range(650):env.step_controls(reference[t,22:25],repeat=1)
            counts[mode]=dll.tmfast_input_adjustments(env.handle)
            assert dll.tmfast_set_control_mode(env.handle,1-mode)!=0,'Mode changed midrace'
            assert dll.tmfast_control_mode(env.handle)==mode
            env.reset(99)
            assert dll.tmfast_control_mode(env.handle)==mode,'Reset lost control semantics'
            assert dll.tmfast_input_adjustments(env.handle)==0,'Reset retained adjustment count'
    assert counts[0]>0 and counts[1]==0,counts
    print(json.dumps({'legacyStartAdjustments':counts[0],'internalStartAdjustments':counts[1],
        'resetPreservesMode':True,'midraceModeChangeRejected':True,'gameAccessed':False}))


if __name__=='__main__':main()
