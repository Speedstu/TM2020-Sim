#!/usr/bin/env python3
"""Search short steering corrections from a full race reset, then distill wins."""
import argparse
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset
from tune_hybrid_tracking import NativeEvaluator
from distill_campaign_run import distill,NATIVE
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map-index',type=int,required=True)
    p.add_argument('--center',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    a=p.parse_args();d=a.output.resolve()/f'{a.map_index:02d}';d.mkdir(parents=True,exist_ok=True)
    s=json.loads((a.source/f'{a.map_index:02d}/pursuit.json').read_text());m=dict(s['goal']);m.update(targetRank=10,targetMs=m['top10TargetMs'],targetExclusive=False)
    model=d/'source.tmhyb';model.write_bytes(Path(s['bestAsset']).read_bytes());ref,g,_=load_asset(model,map_path=m['map'],uid=m['mapUid'])
    ev=NativeEvaluator(64,model,api_path=NATIVE/'libtm2020_vector_physics.so',library=NATIVE/'libtm2020_speed.so',
        map_path=m['map'],horizon=len(ref)+1000,internal_controls=True,fast_evaluation=True)
    best=None
    try:
        for round_id in range(4):
            sign=1 if round_id<2 else -1
            if best is None or best[1]['duration']==0:center=a.center
            else:center=best[1]['warm']
            cases=[{'seed':67000+a.map_index,'warm':max(20,center+offset),'duration':duration,'kick':sign*amp}
                for offset in (-30,-10,0,20) for duration in (2,3,5,8) for amp in (.02,.03221165037321532,.05,.08)]
            cases[0].update(warm=0,duration=0,kick=0.)
            if best:cases[1]=best[1]
            runs,seconds=ev.evaluate(g,cases);save_json(d/f'grid-{round_id}.json',{'cases':cases,'trials':runs,'seconds':seconds})
            for c,r in zip(cases,runs):
                key=(int(r['finishMs'] is not None),r['checkpoints'],-(r['finishMs'] or 10**9),r.get('maximumReferenceIndex',0))
                if best is None or key>best[0]:best=(key,c,r)
            print(json.dumps({'map':a.map_index,'round':round_id,'best':best[2],'case':best[1]}),flush=True)
            if best[2]['finishMs'] is not None and best[2]['finishMs']<=m['top10TargetMs']:break
    finally:ev.close()
    save_json(d/'best-pulse.json',{'case':best[1],'trial':best[2],'model':str(model)})
    if best[2]['finishMs'] is not None:distill(model,m,best[1],d/'distilled')


if __name__=='__main__':main()
