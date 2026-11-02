#!/usr/bin/env python3
"""Single campaign pass: screen feasibility, bounded hardcode search, audit, Top100 -> Top10.

No hourly timer, replay edits, client attachment or automatic champion deployment.
"""
import argparse
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
import numpy as np
from hybrid_tracking import load_asset
from train_hardcode_recorded_inputs import prepare, parameters, emit, benchmark_cases, rank, human_rhythm, NATIVE, PHYSICS
from tune_hybrid_tracking import NativeEvaluator

ROOT=Path(__file__).resolve().parents[1]
STOP=False
CHILD=None

def stop(*_):
    global STOP
    STOP=True
    if CHILD is not None and CHILD.poll() is None:CHILD.send_signal(signal.SIGTERM)

def write(path,doc):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(doc,indent=2));tmp.replace(path)

def run(argv,log):
    global CHILD
    with log.open('a') as stream:
        CHILD=subprocess.Popen([sys.executable,'-u',*map(str,argv)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        code=CHILD.wait();CHILD=None
    if code and not STOP:raise RuntimeError(f'Child exited {code}; see {log}')

def qualified(report,tier):
    for family in ('normal64','perturbed64'):
        r=report['benchmark'][family]
        if r[f'top{tier}Finishes']!=64 or r[f'perRunHumanTop{tier}']['commonStylePasses']!=64:return False
    return report['acknowledgementMismatchTicks']==0

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--maps',type=int,nargs='+',required=True)
    p.add_argument('--bootstrap-normal-routes',action='store_true',help='diagnose zero-finish maps using genuine normal-input route rollouts')
    p.add_argument('--stay-until-qualified',action='store_true',help='never advance a map until all 128 Top10 + human-style checks pass')
    p.add_argument('--human-focus',action='store_true',help='optimize the number of jointly fast and human-style runs first')
    p.add_argument('--generations',type=int,default=48)
    p.add_argument('--plateau',type=int,default=12)
    a=p.parse_args()
    if a.generations<1 or a.plateau<1:p.error('Positive search limits required')
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    lock=(a.output/'campaign.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    status={'controller':'hardcode','clientVerified':False,'automaticDeployment':False,'workerPid':os.getpid(),
        'advanceOnlyAfterQualification':a.stay_until_qualified,
        'policy':('stay on first unqualified map; bounded attempts stop at plateau then diagnose/retry same map; '
                  'advance only after Top10 + human P10-P90 on all 128 cases' if a.stay_until_qualified else
                  'one bounded attempt per map; Top10 only after Top100 + human P10-P90 audit'),
        'maps':{},'running':True}
    journal=a.output/'campaign-status.json'
    cursor=0;attempts={}
    while cursor<len(a.maps):
        index=a.maps[cursor];attempts[index]=attempts.get(index,0)+1
        if STOP or (a.output/'CAMPAIGN_STOP').exists():break
        item={'state':'screening','attempt':attempts[index]};status['maps'][str(index)]=item;status['currentMap']=index;write(journal,status)
        try:
            folder,source,info=prepare(index,a.output);meta=info['meta'];incumbent=folder/'search-incumbent.tmhyb'
            # Preserve known search checkpoints; new maps start from retained champions.
            if not incumbent.exists():
                previous=next((ROOT/f'local/training/{branch}/{index:02d}/search-incumbent.tmhyb'
                    for branch in ('hardcode-human-0.74','hardcode-human-0.73')
                    if (ROOT/f'local/training/{branch}/{index:02d}/search-incumbent.tmhyb').exists()),None)
                if previous is not None:shutil.copy2(previous,incumbent)
            screen=folder/'screen';screen.mkdir(exist_ok=True)
            assets=[]
            if incumbent.exists():assets.append(incumbent)
            for label,g in [('retained',info['gains']),('zero-feedback',np.array([0,0,0,0,.001,0]))]:
                asset=screen/f'{label}.tmhyb';emit(asset,info['ref'],parameters(g),meta,meta['humanActionConstraints']);assets.append(asset)
            cases=benchmark_cases(index,len(info['ref']))
            trials=cases['normal64'][:8]+cases['perturbed64'][:8]
            ev=NativeEvaluator(16,assets[0],api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
                map_path=meta['map'],horizon=len(info['ref'])+600,fast_evaluation=True)
            screens=[]
            try:
                for asset in assets:
                    _,g,_=load_asset(asset,map_path=meta['map'],uid=meta['mapUid'])
                    rows,_=ev.evaluate(g,trials,assets=[asset]*16)
                    screens.append((rank(rows,None,meta.get('top100TargetMs')),asset,rows))
            finally:ev.close()
            if a.human_focus:
                rhythm=human_rhythm(index)
                screens=[(rank(rows,rhythm,meta.get('top100TargetMs'),human_focus=True),asset,rows)
                         for _,asset,rows in screens]
            screens.sort(key=lambda x:x[0],reverse=True)
            _,best,rows=screens[0];item['screenFinishes']=sum(r['finishMs'] is not None for r in rows)
            write(screen/'results.json',{'cases':trials,'candidates':[{'asset':str(asset),'rows':r} for _,asset,r in screens]})
            if not item['screenFinishes']:
                if a.bootstrap_normal_routes:
                    item['state']='bootstrapping-normal-input-route-targets';write(journal,status)
                    run([ROOT/'scripts/bootstrap_normal_hardcode.py','--map',index,'--output',a.output],folder/'bootstrap.log')
                    if STOP:break
                    boot=json.loads((folder/'normal-route-bootstrap/report.json').read_text())
                    item['bootstrapScreenFinishes']=boot.get('bestFinishes',0)
                    if not boot.get('bestFinishes',0):
                        item['state']='needs-normal-input-parity-diagnosis';write(journal,status)
                        if not a.stay_until_qualified:cursor+=1
                        else:break
                        continue
                    best=Path(boot['bestAsset'])
                else:
                    item['state']='needs-normal-input-parity-diagnosis';write(journal,status)
                    if not a.stay_until_qualified:cursor+=1
                    else:break
                    continue
            if best!=incumbent:
                if incumbent.exists():shutil.copy2(incumbent,screen/'incumbent-before.tmhyb')
                shutil.copy2(best,incumbent)
            for tier in (100,10):
                if STOP:break
                item['state']=f'training-top{tier}';write(journal,status)
                run([ROOT/'scripts/train_hardcode_recorded_inputs.py','--output',a.output,'--maps',index,
                     '--generations',a.generations,'--plateau',a.plateau,'--cycles',1,'--target-rank',tier,'--route-search',
                     *(['--human-focus'] if a.human_focus else [])],folder/'campaign-search.log')
                if STOP:break
                # Immutable snapshot: auditing cannot race a search checkpoint write.
                snapshot=folder/f'campaign-top{tier}-snapshot.tmhyb';shutil.copy2(incumbent,snapshot)
                audit=folder/f'campaign-top{tier}-audit'
                item['state']=f'auditing-top{tier}';write(journal,status)
                run([ROOT/'scripts/audit_hardcode_execution.py','--map',index,'--asset',snapshot,'--output',audit],folder/'campaign-audit.log')
                if STOP:break
                report=json.loads((audit/'report.json').read_text());ok=qualified(report,tier)
                item[f'top{tier}WithCommonHumanMetrics']=ok
                item[f'top{tier}Report']=str(audit/'report.json')
                if not ok:
                    item['state']=f'plateau-before-top{tier}-qualification';break
                item['state']=f'simulation-top{tier}-human-metrics-qualified'
                if tier==100 and qualified(report,10):
                    item['top10WithCommonHumanMetrics']=True;item['state']='simulation-top10-human-metrics-qualified';break
            write(journal,status)
            if not a.stay_until_qualified or item.get('top10WithCommonHumanMetrics'):
                cursor+=1
            else:
                item['state']='retrying-same-map-after-diagnosed-plateau';write(journal,status)
        except Exception as exc:
            item.update(state='error-checkpoint-preserved',error=str(exc));write(journal,status)
            if a.stay_until_qualified:break
            cursor+=1
    status['running']=False;status['stopped']=STOP;write(journal,status)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
