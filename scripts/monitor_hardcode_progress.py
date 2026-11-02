#!/usr/bin/env python3
"""Read-only process health plus next-stage diagnostic plans for native training.

No AI timer, process termination, client access, promotion or champion writes.
Plans tune search proposals only; every result still undergoes normal evaluation.
"""
import argparse
from collections import Counter
import fcntl
import json
import hashlib
import os
from pathlib import Path
import signal
import time
import numpy as np
from compare_human_sim_inputs import human_style_proxy,summarize_rows,summarize_human_cohort

STOP=False
def stop(*_):
    global STOP
    STOP=True

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return None

def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,indent=2));tmp.replace(path)

def alive(pid):
    try:
        cmd=(Path('/proc')/str(int(pid))/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
        return 'run_hardcode_human_campaign.py' in cmd
    except (OSError,ValueError,TypeError):return False

def diagnose(index,record,cohort,target):
    rows=record.get('best',{}).get('validation',[]);failed=[r for r in rows if r.get('finishMs') is None]
    violations=Counter();qualified=0
    for r in rows:
        if r.get('finishMs') is None or r['finishMs']>target:continue
        check=human_style_proxy(summarize_rows([r],target,'top100'),cohort)
        qualified+=int(check['commonStylePasses']);violations.update(check['commonStyleFailures'])
    focus=max(0,int(np.percentile([r.get('maximumReferenceIndex',0) for r in failed],25))-80) if failed else None
    pedal=sum(n for k,n in violations.items() if k.startswith(('gas ','brake ')))
    steering=sum(n for k,n in violations.items() if not k.startswith(('gas ','brake ')))
    primary='pedal-rhythm' if pedal>steering and pedal>len(failed) else 'route-recovery' if failed else 'steering-rhythm'
    return {'map':index,'stage':record.get('stage'),'generation':record.get('generation'),
        'staleGenerations':record.get('stale',0),'finishes':len(rows)-len(failed),
        'jointHumanTargetRuns':qualified,'failedStyleCriteria':dict(violations),
        'primarySearchFocus':primary,'failureFocusTick':focus,
        'requestedAfterPlateau':record.get('stale',0)>=6,'inputEnvelopeChanged':False,
        'noClientOrChampionWrites':True}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--roots',nargs='+',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--once',action='store_true');args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);lock=(args.output/'monitor.lock').open('a')
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    previous={};cohorts={}
    while not STOP and not (args.output/'STOP').exists():
        snapshots=[]
        for root in args.roots:
            campaign=read(root/'campaign-status.json') or {};index=campaign.get('currentMap')
            snap={'root':str(root.resolve()),'map':index,'workerPid':campaign.get('workerPid'),
                'processAlive':alive(campaign.get('workerPid')),'reportedRunning':campaign.get('running',False)}
            if isinstance(index,int):
                folder=root/f'{index:02d}';record=read(root/'status.json')
                if record and record.get('map')==index:
                    protocol=read(folder/f"stage-{record['stage']:04d}/protocol.json") or {}
                    target=protocol.get('trainingTargetMs')
                    if target:
                        if index not in cohorts:cohorts[index]=summarize_human_cohort(index)[0]
                        plan=diagnose(index,record,cohorts[index],target);snap.update(plan)
                        key=(record.get('stage'),record.get('generation'))
                        old=previous.get(str(root));unchanged=time.time()-old[1] if old and old[0]==key else 0.
                        if not old or old[0]!=key:previous[str(root)]=(key,time.time())
                        snap['generationUnchangedSeconds']=round(unchanged,1)
                        snap['progressStalled']=unchanged>300 and snap['processAlive']
                        if plan['requestedAfterPlateau']:write(folder/'next-stage-diagnostic-plan.json',plan)
                    # Publish only an immutable search seed, never a deployment.
                    # The ordered trainer must reevaluate it on its own cases.
                    if root.name=='hardcode-human-0.76-prep':
                        source=folder/'search-incumbent.tmhyb'
                        if source.exists():
                            payload=source.read_bytes();digest=hashlib.sha256(payload).hexdigest()
                            dest=root/f'handoff/{index:02d}/candidate-{digest[:20]}.tmhyb';dest.parent.mkdir(parents=True,exist_ok=True)
                            if not dest.exists():
                                tmp=dest.with_suffix('.tmp');tmp.write_bytes(payload);tmp.replace(dest)
                            write(dest.parent/'latest.json',{'map':index,'asset':str(dest.resolve()),'sha256':digest,
                                'requiresIndependentReevaluation':True,'clientVerified':False,'promoted':False})
            snap['needsIntervention']=bool(snap['reportedRunning'] and not snap['processAlive']) or snap.get('progressStalled',False)
            snapshots.append(snap)
        write(args.output/'status.json',{'monitorPid':os.getpid(),'updatedUnixNs':time.time_ns(),
            'roots':snapshots,'hourlyModelTimer':False,'kind':'deterministic training health and next-stage diagnostics'})
        if args.once:break
        for _ in range(20):
            if STOP:break
            time.sleep(1)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
