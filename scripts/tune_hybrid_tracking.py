#!/usr/bin/env python3
"""Bounded population search of trajectory feedback; complete native races."""
import argparse
import ctypes as C
import json
import os
import time
from pathlib import Path
import numpy as np
from prepare_fall_campaign import save_json
from hybrid_tracking import DIR,PHYSICS,reference_asset,save_asset,cases
from run_fast_ppo import ROOT
from vector_physics import VectorPhysics


class NativeEvaluator:
    def __init__(self,n,asset,api_path=None,*,map_path=None,horizon=None,library=PHYSICS,internal_controls=False,fast_evaluation=False):
        self.n=n;self.asset=asset;self.fast_evaluation=fast_evaluation
        self.env=VectorPhysics(n,decision_ticks=1,api_path=api_path or Path(os.environ.get('TM2020_HYBRID_API',ROOT/'native/build-hybrid/libtm2020_vector_physics.so')),library=library,map_path=map_path,horizon=horizon,internal_controls=internal_controls)
        self.api=self.env.api
        self.api.tmvec_hybrid_evaluate.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_double),
             C.POINTER(C.c_uint32),C.POINTER(C.c_uint32),C.POINTER(C.c_uint32),C.POINTER(C.c_float)]
    def evaluate(self,gains,trial_cases,assets=None):
        g=np.ascontiguousarray(gains,dtype=np.float64)
        if g.shape==(6,):g=np.tile(g,(self.n,1))
        seeds=np.asarray([c['seed'] for c in trial_cases],dtype=np.uint32)
        warm=np.asarray([c['warm'] for c in trial_cases],dtype=np.uint32)
        duration=np.asarray([c['duration'] for c in trial_cases],dtype=np.uint32)
        kick=np.asarray([c['kick'] for c in trial_cases],dtype=np.float32)
        launch=np.asarray([c.get('launchDeltaMps',0.) for c in trial_cases],dtype=np.float32)
        if hasattr(self.api,'tmvec_launch_uncertainty') and hasattr(self.env.api,'tmvec_set_control_mode'):
            self.api.tmvec_launch_uncertainty.argtypes=[C.c_void_p,C.POINTER(C.c_float)]
            # New wrapper may also load a frozen legacy engine. Only request
            # the new semantics when the caller explicitly declared a case.
            if any('launchDeltaMps' in c for c in trial_cases) or getattr(self,'launch_used',False):
                self.env.check(self.api.tmvec_launch_uncertainty(self.env.handle,launch.ctypes.data_as(C.POINTER(C.c_float))))
                self.launch_used=True
        elif np.any(launch):raise RuntimeError('Native evaluator lacks launch uncertainty support')
        assert g.shape==(self.n,6) and len(trial_cases)==self.n
        start=time.monotonic()
        function=self.api.tmvec_hybrid_evaluate_fast if self.fast_evaluation else self.api.tmvec_hybrid_evaluate
        function.argtypes=self.api.tmvec_hybrid_evaluate.argtypes
        asset=str(self.asset).encode()
        if assets is not None:
            function=self.api.tmvec_hybrid_evaluate_assets_fast if self.fast_evaluation else self.api.tmvec_hybrid_evaluate_assets
            function.argtypes=[C.c_void_p,C.POINTER(C.c_char_p),*self.api.tmvec_hybrid_evaluate.argtypes[2:]]
            assert len(assets)==self.n
            asset=(C.c_char_p*self.n)(*[str(a).encode() for a in assets])
        self.env.check(function(self.env.handle,asset,
           g.ctypes.data_as(C.POINTER(C.c_double)),seeds.ctypes.data_as(C.POINTER(C.c_uint32)),
           warm.ctypes.data_as(C.POINTER(C.c_uint32)),duration.ctypes.data_as(C.POINTER(C.c_uint32)),kick.ctypes.data_as(C.POINTER(C.c_float))))
        result=[{'seed':int(c['seed']),'finishMs':int(s.finish_ms) if s.finish_ms>=0 else None,
                 'checkpoints':int(s.checkpoints),'tick':int(s.tick),
                 'finalPosition':np.array(s.rigid_words,dtype=np.uint32).view(np.float32)[9:12].tolist() if not s.reserved else None}
                for c,s in zip(trial_cases,self.env.states[:self.n])]
        if hasattr(self.api,'tmvec_hybrid_progress'):
            self.api.tmvec_hybrid_progress.argtypes=[C.c_void_p];self.api.tmvec_hybrid_progress.restype=C.POINTER(C.c_uint32)
            progress=self.api.tmvec_hybrid_progress(self.env.handle)
            for i,r in enumerate(result):r['maximumReferenceIndex']=int(progress[i])
        if hasattr(self.api,'tmvec_hybrid_input_statistics'):
            self.api.tmvec_hybrid_input_statistics.argtypes=[C.c_void_p]
            self.api.tmvec_hybrid_input_statistics.restype=C.POINTER(C.c_uint32)
            stat_size=20744
            counts=np.ctypeslib.as_array(self.api.tmvec_hybrid_input_statistics(self.env.handle),shape=(self.n*stat_size,)).reshape(self.n,stat_size)
            for r,c in zip(result,counts):
                seconds=max(int(c[0])*.01,.01)
                steps=np.repeat(np.arange(255),c[9:264].astype(int))
                def durations(offset):
                    hist=c[offset:offset+4096]
                    return np.repeat(np.arange(1,4097,dtype=float)*10.,hist.astype(int))
                def quantiles(values):return np.percentile(values,[10,50,90]).tolist() if len(values) else []
                r['inputs']={'ticks':int(c[0]),'steeringChangesPerSecond':int(c[1])/seconds,
                    'steeringVariationPerSecond':int(c[2])/127/seconds,
                    'reversalsWithin100ms':int(c[3]),'smallReversalsWithin100ms':int(c[4]),
                    'gasChanges':int(c[5]),'brakeChanges':int(c[6]),
                    'gasChangesPerSecond':int(c[5])/seconds,'brakeChangesPerSecond':int(c[6])/seconds,
                    'gasDuty':int(c[7])/max(int(c[0]),1),'brakeDuty':int(c[8])/max(int(c[0]),1),
                    'rawSteeringStepP50P95P99':np.percentile(steps,[50,95,99]).tolist() if len(steps) else [],
                    'steeringHoldMsP10P50P90':quantiles(durations(264)),
                    'gasPressMsP10P50P90':quantiles(durations(4360)),
                    'gasReleaseMsP10P50P90':quantiles(durations(8456)),
                    'brakePressMsP10P50P90':quantiles(durations(12552)),
                    'brakeReleaseMsP10P50P90':quantiles(durations(16648))}
        return result,time.monotonic()-start
    def close(self):self.env.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--generations',type=int,default=20)
    p.add_argument('--output',type=Path,default=DIR/'feedback-search')
    p.add_argument('--initial',type=Path);p.add_argument('--diverse',action='store_true');a=p.parse_args()
    a.output.mkdir(exist_ok=False,parents=True)
    asset=a.output/'reference.tmhyb';ref=reference_asset();save_asset(asset,ref,[0,0,0,0,.001,0])
    env=NativeEvaluator(64,asset);rng=np.random.default_rng(105151)
    dev=cases(105152,4,False)
    # Exclude the exact reference seed from optimization: it trivially wins.
    if a.diverse:
        dev=cases(105161,64,True)[1:5]
    else:dev=[dict(c,seed=105152001+i) for i,c in enumerate(dev)]
    candidates=[]
    for kp in (0.,.002,.01,.05):
        for kh in (-1.,0.,1.,4.):candidates.append([kp,0.,kh,0.,.001,0.])
    candidates=np.asarray(candidates);best=None;mean=np.array([.01,.01,1.,.05,.001,0.]);spread=np.array([.03,.04,2.,.2,.005,0.])
    if a.initial:
        mean=np.array(json.loads(a.initial.read_text())['gains']);candidates=mean+rng.normal(size=(16,6))*spread
        candidates[:,4]=np.clip(candidates[:,4],0,.05);candidates[:,5]=0;candidates[0]=mean
    save_json(a.output/'development-cases.json',dev)
    try:
        for generation in range(a.generations):
            if generation:
                candidates=mean+rng.normal(size=(16,6))*spread
                candidates[:,4]=np.clip(candidates[:,4],0,.05);candidates[:,5]=0
                candidates[0]=best['gains']
            trials=dev*16;rows,seconds=env.evaluate(np.repeat(candidates,4,axis=0),trials)
            metrics=[]
            for i,g in enumerate(candidates):
                runs=rows[i*4:(i+1)*4];times=[r['finishMs'] or 40000 for r in runs]
                finishes=sum(r['finishMs'] is not None for r in runs)
                key=(finishes,-float(np.mean(times)),sum(r['checkpoints'] for r in runs))
                metrics.append((key,i));record={'generation':generation,'gains':g.tolist(),'finishes':finishes,
                    'penalizedMeanMs':float(np.mean(times)),'key':key,'trials':runs}
                if best is None or tuple(record['key'])>tuple(best['key']):
                    best=record;save_json(a.output/'best.json',best);save_asset(a.output/'best.tmhyb',ref,g)
            metrics.sort(reverse=True);elite=candidates[[i for _,i in metrics[:4]]]
            mean=elite.mean(0);spread=np.maximum(elite.std(0),[.002,.003,.1,.01,.0002,0.])
            spread[5]=0
            print(json.dumps({'generation':generation,'seconds':seconds,'best':best}),flush=True)
            save_json(a.output/'status.json',{'generation':generation,'best':best,'mean':mean.tolist(),'spread':spread.tolist()})
        final=cases(105153,64,True);rows,seconds=env.evaluate(best['gains'],final)
        save_json(a.output/'qualification.json',{'trials':rows,'seconds':seconds,'gains':best['gains'],
                  'finishes':sum(r['finishMs'] is not None for r in rows),'referenceAssisted':True,'gameVerified':False})
    finally:env.close()


if __name__=='__main__':main()
