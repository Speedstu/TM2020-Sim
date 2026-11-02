#!/usr/bin/env python3
"""Recheck retained nominal laps with policy failures latched until reset."""
import argparse
import hashlib
import json
from pathlib import Path
from hybrid_tracking import load_asset
from tune_hybrid_tracking import NativeEvaluator
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    p.add_argument('--maps',nargs='+',type=int,default=list(range(2,26)));a=p.parse_args()
    native=ROOT/'native/build-replay-0.68';physics=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so'
    reports=[]
    for i in a.maps:
        state=json.loads((a.source/f'{i:02d}/pursuit.json').read_text());m=state['goal'];d=a.output/f'{i:02d}';d.mkdir(parents=True,exist_ok=True)
        asset=d/'source.tmhyb';asset.write_bytes(Path(state['bestAsset']).read_bytes())
        ref,g,_=load_asset(asset,map_path=m['map'],uid=m['mapUid'])
        ev=NativeEvaluator(1,asset,api_path=native/'libtm2020_vector_physics.so',library=physics,map_path=m['map'],
            horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
        try:trials,seconds=ev.evaluate(g,[{'seed':68000+i,'warm':0,'duration':0,'kick':0.}])
        finally:ev.close()
        old=state['selected']['development']['trials'][0]['finishMs'];now=trials[0]['finishMs']
        r={'mapIndex':i,'modelSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),'previousNominalMs':old,
            'latchedNominal':trials[0],'nominalUnchanged':old==now,'seconds':seconds,
            'simulationOnly':True,'internalDeviceHistoryFrozen':True,'policyFailureLatched':True}
        reports.append(r);save_json(d/'audit.json',r);save_json(a.output/'summary.json',{'reports':reports,'complete':len(reports)==len(a.maps)})
        print(json.dumps(r),flush=True)


if __name__=='__main__':main()
