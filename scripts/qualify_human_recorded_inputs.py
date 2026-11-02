"""Paired 64-seed normal/perturbed qualification, with no teacher/restores."""
import hashlib,json,os
from pathlib import Path
import numpy as np
from prepare_fall_campaign import ROOT,save_json
from tune_hybrid_tracking import NativeEvaluator
from hybrid_tracking import load_asset


def qualify(infos,folder,output,round_id):
    native=Path(os.environ.get('TM2020_HUMAN_NATIVE',ROOT/'native/build-human-0.70'));physics=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so';reports={}
    for info in infos:
        i=info['index'];m=info['meta'];ref=info['reference'];rng=np.random.default_rng(7030000+i)
        seeds=rng.integers(1,2**32-1,64,dtype=np.uint32)
        nominal=[{'seed':int(s),'warm':0,'duration':0,'kick':0.} for s in seeds]
        disturbed=[{'seed':int(s),'warm':int(rng.integers(200,max(201,len(ref)-300))),
            'duration':int(rng.integers(2,6)),'kick':float(rng.choice([-1,1])*rng.uniform(.02,.06))} for s in seeds]
        saved=json.loads((output.parents[0]/f'preserved/{i:02d}/pursuit.json').read_text()) if i!=1 else None
        baseline=next((output.parents[0]/f'preserved/{i:02d}').glob('*.tmhyb'))
        candidate=folder/f'{i:02d}-trained.tmhyb';results={}
        for label,asset in (('before',baseline),('after',candidate)):
            rr,g,_=load_asset(asset,map_path=m['map'],uid=m['mapUid'])
            ev=NativeEvaluator(8,asset,api_path=native/'libtm2020_vector_physics.so',library=physics,
                map_path=m['map'],horizon=max(len(ref),len(rr))+600,internal_controls=False,fast_evaluation=True)
            try:
                for family,cases in (('normal64',nominal),('perturbed64',disturbed)):
                    rows=[]
                    for k in range(0,64,8):rows.extend(ev.evaluate(g,cases[k:k+8])[0])
                    times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
                    results.setdefault(label,{})[family]={'finishes':len(times),'count':64,'bestMs':min(times) if times else None,
                        'meanMs':float(np.mean(times)) if times else None,'medianMs':float(np.median(times)) if times else None,
                        'worstMs':max(times) if times else None,'trials':rows}
            finally:ev.close()
        reports[i]={'modelSha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),'cases':{'normal64':nominal,'perturbed64':disturbed},
            'results':results,'sameSeedsMapsHorizonAndInputHistory':True,'teacherUsedDuringQualification':False,
            'checkpointsRestoredDuringQualification':False,'clientVerified':False,'promoted':False,
            'promotionReason':'Client replay and per-segment post-training style validation still required'}
        save_json(folder/f'qualification-{i:02d}.json',reports[i])
        print(json.dumps({'qualificationMap':i,'round':round_id,'normal64':{k:v['normal64']['finishes'] for k,v in results.items()},
            'perturbed64':{k:v['perturbed64']['finishes'] for k,v in results.items()}}),flush=True)
    save_json(folder/'paired-qualification.json',{'maps':reports,'simulationOnly':True,'allModelsQuarantined':True})
    return reports
