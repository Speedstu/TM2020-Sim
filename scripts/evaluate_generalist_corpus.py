#!/usr/bin/env python3
"""Evaluate a frozen shared policy on whole maps, without replay paths."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
from generalist_engine import GeneralistEngine, SCHEMA
from owned_ppo import OwnedPolicy
from run_fast_ppo import steam_packs

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',required=True,type=Path);p.add_argument('--split',choices=['train','validation','test'],required=True)
    p.add_argument('--model',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--packs',type=Path);p.add_argument('--trials',type=int,default=3);p.add_argument('--horizon',type=int,default=6000)
    a=p.parse_args()
    if a.output.exists():p.error('output must be new')
    if not 1<=a.trials<=30:p.error('trials outside 1..30')
    a.output.mkdir(parents=True);corpus=json.loads(a.corpus.read_text());model_sha=hashlib.sha256(a.model.read_bytes()).hexdigest()
    model=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',a.model,SCHEMA+'|policy_actions=pedals_direct3',48,3)
    packs=a.packs or steam_packs();reports=[];begin=time.monotonic()
    try:
        for m in corpus['splits'][a.split]:
            entry={'map':m['map'],'uid':m['mapUid'],'mapSha256':m['mapSha256'],'trials':[]}
            try:
                path=ROOT/m['map']
                if hashlib.sha256(path.read_bytes()).hexdigest()!=m['mapSha256']:raise ValueError('map changed after split')
                with GeneralistEngine(ROOT/'cache/fast-training-final-target/release/libtm2020_generalist.so',path,packs,a.horizon) as e:
                    for trial in range(a.trials):
                        s=e.reset(391026+trial);reward=0.;steps=0
                        while not s.terminated and not s.truncated:
                            action,_=model.predict(s.observation)
                            # Perturb actual controls, never the observation or a fake car pose.
                            if trial>0 and steps in (20,21,22):
                                action[2]=max(-1.,min(1.,action[2]+(.25 if trial%2 else -.25)))
                            s=e.step(action,5);reward+=s.reward;steps+=1
                        entry['trials'].append({'trial':trial,'finished':s.finish_ms>=0,'finishMs':s.finish_ms,
                                                'checkpoints':s.checkpoints,'ticks':s.tick,'reward':reward})
            except Exception as error:
                entry['error']=str(error)
            reports.append(entry);print(json.dumps(entry),flush=True)
            report={'schema':'tm2020_generalist_frozen_whole_map_evaluation_v1','modelSha256':model_sha,
                    'split':a.split,'testUsedForSelection':False,'seconds':time.monotonic()-begin,'maps':reports,
                    'finishes':sum(t['finished'] for x in reports for t in x['trials']),
                    'completedTrials':sum(len(x['trials']) for x in reports),'expectedTrials':len(corpus['splits'][a.split])*a.trials,
                    'unsupportedOrFailedMaps':sum('error' in x for x in reports),'expertRouteRequired':False}
            (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    finally:model.close()
    assert hashlib.sha256(a.model.read_bytes()).hexdigest()==model_sha,'model changed during evaluation'

if __name__=='__main__':main()
