#!/usr/bin/env python3
"""Offline screen for action plans derived from route geometry/speed, not replay controls."""
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from hybrid_tracking import load_asset,save_asset
import train_hardcode_recorded_inputs as trainer
from tune_hybrid_tracking import NativeEvaluator


def derive(ref,steer_scale,brake_mode,steer_lookahead=10):
    out=ref.copy()
    yaw=np.unwrap(np.arctan2(ref[:,2],ref[:,8]))
    speed=np.linalg.norm(ref[:,16:19],axis=1)
    curvature=np.gradient(yaw,.01)/np.maximum(speed,1.)
    ahead=np.r_[curvature[steer_lookahead:],np.repeat(curvature[-1],steer_lookahead)]
    out[:,24]=np.clip(ahead*steer_scale,-1.,1.)
    out=trainer.smooth_steering_reference(out,5)
    out[:,22]=1.;out[:,23]=0.
    kind,a,b=brake_mode
    if kind=='future_speed_drop':
        future=np.r_[speed[a:],np.repeat(speed[-1],a)]
        out[:,23]=(speed-future)>b
    elif kind=='lateral_accel':
        lateral=np.abs(curvature)*speed*speed
        out[:,23]=lateral>b
    elif kind=='human_control':
        out[:,22:24]=ref[:,22:24]
    elif kind!='none':
        raise ValueError(brake_mode)
    return out


def main():
    idx=int(sys.argv[1]) if len(sys.argv)>1 else 3
    meta=json.loads((ROOT/f'local/training/fall-campaign-0.52/{idx:02d}/map.json').read_text())
    top100=ROOT/f'local/training/human-rework-0.70/top100-cohort/{idx:02d}/leaderboard-top100.json'
    if top100.is_file():meta['top100TargetMs']=int(next(x['time'] for x in json.loads(top100.read_text())['tops'] if int(x['position'])==100))
    source=ROOT/f'local/training/hardcode-human-0.73/{idx:02d}/stage-0001/candidate-final.tmhyb'
    if idx==1:source=ROOT/'local/training/hardcode-human-0.73/01/stage-0000/candidate-final.tmhyb'
    outdir=ROOT/f'local/training/hardcode-human-0.73/{idx:02d}/geometry-action-screen';outdir.mkdir(parents=True,exist_ok=True)
    ref,gain,network=load_asset(source,map_path=meta['map'],uid=meta['mapUid'])
    source_bytes=source.read_bytes();import struct
    nu,ns=struct.unpack_from('<II',source_bytes,24)
    feedback=np.frombuffer(source_bytes,dtype='<f8',count=3,offset=32+nu+ns+(6+449)*8).copy()
    constraints=trainer.human_action_constraints(idx)
    if idx==1:
        modes=[('none',0,0)]
    else:
        modes=[('none',0,0),('human_control',0,0),
            *[('future_speed_drop',ahead,drop) for ahead,drop in ((10,1),(20,1),(20,2),(50,2),(50,3),(100,3),(100,5))],
            *[('lateral_accel',0,limit) for limit in (50,60,70,75)]]
    yaws=np.unwrap(np.arctan2(ref[:,2],ref[:,8]));speed=np.linalg.norm(ref[:,16:19],axis=1)
    curvature=np.gradient(yaws,.01)/np.maximum(speed,1.)
    raw=np.rint(ref[:,24]*127.)/127.;mask=(speed>10)&(np.abs(raw)>.04)&(np.abs(curvature)>1e-5)
    ahead=10;future_curvature=np.r_[curvature[ahead:],np.repeat(curvature[-1],ahead)]
    mask=(speed>10)&(np.abs(raw)>.04)&(np.abs(future_curvature)>1e-5)
    fitted=float(future_curvature[mask]@raw[mask]/(future_curvature[mask]@future_curvature[mask]))
    # Matched small development set, four normal + four perturbed starts.
    rng=np.random.default_rng(7100000+idx*1000+77)
    seeds=rng.integers(1,2**32-1,8,dtype=np.uint32)
    cases=[{'seed':int(s),'warm':0 if k<4 else int(rng.integers(300,max(301,len(ref)-300))),
        'duration':0 if k<4 else 4,'kick':0. if k<4 else float((1 if k%2 else -1)*5/127)} for k,s in enumerate(seeds)]
    ev=NativeEvaluator(8,source,api_path=trainer.NATIVE/'libtm2020_vector_physics.so',library=trainer.PHYSICS,
        map_path=meta['map'],horizon=len(ref)+600,fast_evaluation=True)
    rows=[]
    try:
        for scale in (fitted*.75,fitted,fitted*1.25):
            for mode in modes:
                candidate=trainer.project_reference(derive(ref,scale,mode),constraints)
                name=f"steer-{scale:.4f}-{mode[0]}-{mode[1]}-{mode[2]}"
                path=outdir/f'{name}.tmhyb'
                save_asset(path,candidate,gain,network,map_path=meta['map'],uid=meta['mapUid'],version=7,
                    feedback_filter=feedback,human_constraints=constraints)
                result,_=ev.evaluate(gain,cases,assets=[path]*len(cases))
                finished=[r for r in result if r['finishMs'] is not None]
                rows.append({'candidate':name,'sha256':trainer.sha(path),'config':{'steeringCurvatureFit':scale,'brakeMode':mode},
                    'finish':len(finished),'top100':sum(r['finishMs'] is not None and r['finishMs']<=meta.get('top100TargetMs',10**9) for r in result),
                    'top10':sum(r['finishMs'] is not None and r['finishMs']<=meta['top10TargetMs'] for r in result),
                    'meanMs':float(np.mean([r['finishMs'] for r in finished])) if finished else None,
                    'checkpointTotal':sum(r['checkpoints'] for r in result),
                    'commandMetrics':{k:np.median([r['inputs'][k] for r in finished if r.get('inputs') and r['inputs'].get(k) is not None],axis=0).tolist()
                        for k in ('steeringChangesPerSecond','steeringVariationPerSecond','gasDuty','brakeDuty','gasChangesPerSecond','brakeChangesPerSecond')
                        if any(r.get('inputs') and r['inputs'].get(k) is not None for r in finished)},
                    'sourceGhostCommandsRetained':mode[0]=='human_control'})
                print(json.dumps(rows[-1]),flush=True)
    finally:ev.close()
    report={'map':idx,'source':str(source.relative_to(ROOT)),'sourceSha256':trainer.sha(source),
        'routePositionOrientationRetained':True,'rawSteeringCopied':False,'rawPedalsCopiedOnlyInExplicitControlBaseline':True,
        'humanInputToCurvatureFit':fitted,'steeringCurvatureLookaheadTicks':ahead,'caseSet':cases,'results':rows}
    (outdir/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('report',outdir/'report.json')

if __name__=='__main__':main()
