#!/usr/bin/env python3
"""Replay selected full-start controllers and retain first failure evidence."""
import argparse
import json
from pathlib import Path
import numpy as np
from hybrid_tracking import Hybrid,load_asset
from vector_physics import VectorPhysics
from prepare_fall_campaign import save_json
from run_fast_ppo import ROOT


def diagnose(index,source,output,use_current=False):
    s=json.loads((source/f'{index:02d}/pursuit.json').read_text());m=s['goal']
    model=Path(s['bestAsset'])
    if use_current and s.get('currentStage') and (Path(s['currentStage'])/'best.tmhyb').exists():model=Path(s['currentStage'])/'best.tmhyb'
    d=output/f'{index:02d}';d.mkdir(parents=True,exist_ok=True)
    snapshot=d/'source.tmhyb';snapshot.write_bytes(model.read_bytes());model=str(snapshot)
    ref,g,_=load_asset(model,map_path=m['map'],uid=m['mapUid'])
    native=ROOT/'local/training/campaign-speed-0.66/native'
    trace=[];events=[];first_failure=None;cursor=0;prior_speed=None;prior_cp=0
    with VectorPhysics(1,decision_ticks=1,api_path=native/'libtm2020_vector_physics.so',
            library=native/'libtm2020_speed.so',map_path=m['map'],horizon=len(ref)+1200,internal_controls=True) as env,Hybrid(model,1) as controller:
        env.reset(0,36139877)
        for t in range(len(ref)+1200):
            state=env.states[0]
            if state.reserved or state.terminated or state.truncated:break
            rigid=np.array(state.rigid_words,dtype=np.uint32).view(np.float32)
            action=controller.act(env)[0];x=controller.features[0].copy()
            speed=float(np.linalg.norm(rigid[16:19]));ms=int(state.tick)*10;cp=int(state.checkpoints)
            if x[11]==0:
                reason='reference_budget_neutral_stop' if cursor+10>=len(ref) and ms>=len(ref)*10+40 else (
                    'reference_time_guard' if ms>(len(ref)+200)*10 else 'reference_observation_guard')
                if first_failure is None:
                    first_failure={'ms':ms,'reason':reason,'cursor':cursor,'checkpoints':cp,
                        'position':rigid[9:12].tolist(),'speedMps':speed,
                        'referencePosition':ref[cursor,9:12].tolist(),
                        'distanceToReferenceM':float(np.linalg.norm(rigid[9:12]-ref[cursor,9:12]))}
            else:cursor=int(round(x[9]*(len(ref)-1)))
            if cp>prior_cp:events.append({'event':'checkpoint','ms':ms,'count':cp,'cursor':cursor})
            if prior_speed is not None and prior_speed-speed>4:
                events.append({'event':'abrupt_speed_loss','ms':ms,'lossMps':prior_speed-speed,
                    'cursor':cursor,'brake':float(action[1]),'position':rigid[9:12].tolist()})
            trace.append(np.concatenate(([ms,cp,cursor],rigid,action,x)))
            prior_speed=speed;prior_cp=cp;env.step(action[None,:])
        final=env.states[0]
        result={'mapIndex':index,'model':model,'map':m,'referenceFrames':len(ref),'gains':g.tolist(),
            'finishMs':int(final.finish_ms) if final.finish_ms>=0 else None,
            'finalMs':int(final.tick)*10,'finalCheckpoints':int(final.checkpoints),
            'maximumReferenceIndex':max(int(row[2]) for row in trace),'firstControllerNeutralGuard':first_failure,
            'events':events,'simulationOnly':True,'launchCorrectionUsed':False}
    d=output/f'{index:02d}';d.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(d/'rollout.npz',rows=np.asarray(trace,dtype=np.float64),
        columns=np.array(['ms','checkpoints','cursor',*[f'rigid{i}' for i in range(22)],'gas','brake','steer',*[f'feature{i}' for i in range(12)]]))
    save_json(d/'diagnosis.json',result)
    print(json.dumps({k:result[k] for k in ('mapIndex','referenceFrames','finishMs','maximumReferenceIndex','firstControllerNeutralGuard')}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=ROOT/'local/training/fall-campaign-world-records-0.57')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--maps',type=int,nargs='+',required=True)
    p.add_argument('--current',action='store_true')
    a=p.parse_args();results=[diagnose(i,a.source.resolve(),a.output.resolve(),a.current) for i in a.maps]
    save_json(a.output/'summary.json',{'results':results,'simulationOnly':True})


if __name__=='__main__':main()
