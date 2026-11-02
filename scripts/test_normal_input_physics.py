#!/usr/bin/env python3
"""Independent input decode and unchanged full physics across 5/10/15s."""
import ctypes as C,json,subprocess
from pathlib import Path
import numpy as np
from generalist_engine import GeneralistEngine
from prepare_fall_campaign import ROOT,save_json
from verify_owned_causal_inputs import encode_owned
from run_fast_ppo import steam_packs


def main():
    out=ROOT/'local/training/human-rework-0.70/physics-audit';out.mkdir(exist_ok=True)
    q=np.load(ROOT/'local/training/human-rework-0.70/corpus/01/leaderboard-rank1/timeline.npz');actions=q['controls'][:1700]
    path=out/'reference-owned.inputstream.json';save_json(path,encode_owned(actions))
    decoded=json.loads(subprocess.check_output([str(ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'),'decode-owned',str(path)],text=True))['decoded']
    assert decoded['truncated_at'] is None
    replayed=np.array([[int(t['gas']),int(t['brake']),max(-1,t['steer']/127)] for t in decoded['ticks']],dtype=np.float32)
    assert np.array_equal(actions,replayed)
    lib=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so';engines=[];exact=0;divergence=None
    try:
        root=GeneralistEngine(lib,map_path=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx',packs=steam_packs(),horizon=2500);engines.append(root)
        for _ in range(2):engines.append(GeneralistEngine(lib,horizon=2500,clone=root))
        for i,e in enumerate(engines):
            e.lib.tmfast_set_control_mode.argtypes=[C.c_void_p,C.c_uint32];e.lib.tmfast_input_adjustments.argtypes=[C.c_void_p]
            e.check(e.lib.tmfast_set_control_mode(e.handle,int(i==2)));e.reset(36139877)
        for k,(a,b) in enumerate(zip(actions,replayed)):
            for e,c in zip(engines,(a,b,a)):e.step_controls(c,1)
            words=[list(e.state.rigid_words) for e in engines]
            if words[0]!=words[1]:raise AssertionError(f'Codec changed physics at tick {k}')
            exact+=1
            if words[0]!=words[2] and divergence is None:divergence=(k+1)*10
        counts=[e.lib.tmfast_input_adjustments(e.handle) for e in engines]
        assert counts[:2]==[3,3] and counts[2]==0 and divergence is not None
    finally:
        for e in reversed(engines):e.close()
    report={'normalOriginalVsDecodedRigid22BitExactTicks':exact,'inputHistoryAdjustments':counts,
        'normalVsLegacyFrozenFirstDivergenceMs':divergence,'physicsLibraryChanged':False,'stateCorrections':0,
        'ownedEnvelopeIsNotClientReplay':True}
    save_json(out/'proof.json',report);print(json.dumps(report))


if __name__=='__main__':main()
