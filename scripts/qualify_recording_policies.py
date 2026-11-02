#!/usr/bin/env python3
"""Qualify policies with normal input history, as used by the new recorder path.

Seeds now affect the engine's normal start adjustments. Every case starts at
race zero; no launch/state corrections and no modified replay files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset,save_asset
from tune_hybrid_tracking import NativeEvaluator
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase-screen',action='store_true',help='Test fixed-clock references and geometric feedback signs')
    p.add_argument('--maps',type=int,nargs='+',default=[3,6]);a=p.parse_args()
    native=ROOT/'native/build-replay-0.68';physics=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so'
    for i in a.maps:
        d=a.output/f'{i:02d}';d.mkdir(parents=True,exist_ok=True)
        state=json.loads((ROOT/f'local/training/fall-campaign-world-records-0.57/{i:02d}/pursuit.json').read_text());m=state['goal']
        baseline=d/'selected.tmhyb';baseline.write_bytes(Path(state['bestAsset']).read_bytes())
        ref,g,nn=load_asset(baseline,map_path=m['map'],uid=m['mapUid']);variants=[(baseline,g)]
        for raw in (.5,1.,1.5):
            asset=d/f'selected-filter{raw}.tmhyb';save_asset(asset,ref,g,nn,map_path=m['map'],uid=m['mapUid'],version=3,feedback_filter=[raw/127,0,10]);variants.append((asset,g))
        human_dir=ROOT/f'local/training/fall-campaign-0.52/{i:02d}';meta=json.loads((human_dir/'reference.json').read_text())
        human=np.fromfile(human_dir/'reference.f32',dtype='<f4').reshape(-1,25)
        source_gains=np.array([0.,0.,0.,0.,.001,0.]);asset=d/'reference-controller.tmhyb'
        save_asset(asset,human,source_gains,map_path=m['map'],uid=m['mapUid']);variants.append((asset,source_gains))
        if a.phase_screen:
            variants=[(baseline,g)]
            for label,trajectory in (('selected',ref),('human',human)):
                for name,values in (
                    ('current',np.r_[g[:4],100.,0.]),('zero',[0,0,0,0,100.,0]),
                    ('positive',[.05,.03,1.,.1,100.,0]),('negative',[-.05,-.03,-1.,-.1,100.,0]),
                    ('cross',[.05,.03,-1.,-.1,100.,0]),('cross2',[-.05,-.03,1.,.1,100.,0])):
                    asset=d/f'{label}-clock-{name}.tmhyb';values=np.asarray(values,dtype=float)
                    save_asset(asset,trajectory,values,map_path=m['map'],uid=m['mapUid']);variants.append((asset,values))
        seeds=np.random.default_rng(69000+i).integers(1,2**32-1,size=64,dtype=np.uint32);seeds[0]=meta['seed']
        trials=[{'seed':int(s),'warm':0,'duration':0,'kick':0.} for s in seeds];results=[]
        for asset,gains in variants:
            ev=NativeEvaluator(8,asset,api_path=native/'libtm2020_vector_physics.so',library=physics,map_path=m['map'],
                horizon=max(len(ref),len(human))+1000,internal_controls=False,fast_evaluation=True)
            rows=[]
            try:
                for k in range(0,64,8):rows.extend(ev.evaluate(gains,trials[k:k+8])[0])
            finally:ev.close()
            times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
            result={'model':str(asset.resolve()),'modelSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
                'finishes':len(times),'count':64,'targetFinishes':sum(t<=m['top10TargetMs'] for t in times),
                'bestMs':min(times) if times else None,'meanMs':float(np.mean(times)) if times else None,
                'medianMs':float(np.median(times)) if times else None,'worstMs':max(times) if times else None,
                'referenceSeedTrial':rows[0],'trials':rows}
            results.append(result);save_json(d/'qualification.json',{'map':m,'cases':trials,'variants':results,
                'normalInputHistory':True,'policyFailureLatched':True,'simulationOnly':True,
                'clientRecordingVerified':False,'assistedTrajectoryController':True})
            print(json.dumps({'map':i,'model':asset.name,**{k:result[k] for k in ('finishes','targetFinishes','bestMs','meanMs')}}),flush=True)


if __name__=='__main__':main()
