"""Read-only support for the staged/parallel world-record campaign optimizer.

Current schema (0.57):
  .../fall-campaign-world-records-0.57/status.json
  .../stages/000/21/status.json, .../stages/000/22/status.json ...
The root owns progress, goals, queues and active map numbers. Individual
stages own generation statistics and actual native-physics steps per second.
No process is signalled, no training files are written.
"""
from __future__ import annotations
import os
import json
import time
from pathlib import Path


def read_json(p):
    try:
        x=json.loads(p.read_text())
        return x if isinstance(x,dict) else {}
    except (OSError,ValueError,TypeError):
        return {}


def processes():
    """Output directories belonging to live pursuit and native search processes."""
    data={'pursuit':{},'workers':{}}
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            a=[os.fsdecode(x) for x in (directory/'cmdline').read_bytes().split(b'\0') if x]
            if not any('pursue_campaign_records.py' in x or 'optimize_fall_campaign.py' in x for x in a):
                continue
            # --output is used by both commands; --output=DIR is also supported.
            out=None
            for i,x in enumerate(a):
                if x=='--output' and i+1<len(a):
                    out=a[i+1];break
                if x.startswith('--output='):
                    out=x.split('=',1)[1];break
            if out is None:continue
            cwd=Path(os.readlink(directory/'cwd'))
            p=(cwd/out).resolve()
            kind='pursuit' if any('pursue_campaign_records.py' in x for x in a) else 'workers'
            data[kind][p]=int(directory.name)
        except (OSError,ValueError,IndexError):
            continue
    return data


def discover(training,now=None):
    now=time.time() if now is None else now
    pr=processes()
    result=[]
    for parent in training.iterdir():
        if not parent.is_dir():
            continue
        status_path=parent/'status.json'
        root=read_json(status_path)
        if not (isinstance(root.get('activeMaps'),list)
                and isinstance(root.get('maps'),list)
                and 'targetRank' in root):
            continue
        try:mtime=status_path.stat().st_mtime
        except OSError:continue
        pid=pr['pursuit'].get(parent.resolve())
        live=pid is not None
        age=max(0,now-mtime)
        id_root=parent.relative_to(training).as_posix()
        children=[]
        for status in (parent/'stages').glob('*/[0-9][0-9]/status.json'):
            folder=status.parent
            d=read_json(status)
            if 'generation' not in d:
                continue
            try:child_mtime=status.stat().st_mtime
            except OSError:continue
            stage_parent=folder.parent.resolve()
            proc=pr['workers'].get(stage_parent)
            child_age=max(0,now-child_mtime)
            child_live=proc is not None and d.get('state')=='optimizing' and child_age<120
            state=('RUNNING' if child_live else
                    'STOPPED' if d.get('state')=='stopped' or (folder/'result.json').exists()
                    else 'STALE' if d.get('state')=='optimizing' else
                    str(d.get('state','unknown')).upper())
            entry={'id':folder.relative_to(training).as_posix(),
                   'name':f'{folder.parent.name}/{folder.name}',
                   'path':folder,'state':state,'live':child_live,
                   'mtime':child_mtime,'age':child_age,'status':d,
                   'kind':'pursuit-map','parent':parent,'pid':proc,
                   'pursuit_status':root}
            children.append(entry)
        children.sort(key=lambda x:(not x['live'],-x['mtime'],x['id']))
        result.extend(children)
        root_entry={'id':id_root,'name':parent.name,'path':parent,
            'state':'RUNNING' if live else str(root.get('state','stopped')).upper(),
            'live':live,'mtime':mtime,'age':age,'status':root,
            'kind':'pursuit-group','pid':pid,'children':children}
        result.append(root_entry)
    return result


def details(r):
    """Summarize the session or one stage without inventing game verification."""
    root_entry=r['kind']=='pursuit-group'
    if root_entry:
        root=r['status']
        children=r['children']
        active=sorted([x for x in children if x['live']],key=lambda x:x['name'])
        selected=max(active,key=lambda x:x['mtime']) if active else (children[0] if children else None)
        root_path=r['path']
    else:
        root=r['pursuit_status']
        selected=r
        root_path=r['parent']
        children=[]
        active=[]
    mapped=root.get('maps') or []
    by_index={int(m['index']):m for m in mapped if isinstance(m,dict) and isinstance(m.get('index'),int)}
    # The root stores the authoritative progress. Stage result files alone
    # are not proof of qualifying for a game leaderboard.
    goals=sum(m.get('simGoalPassed') is True for m in by_index.values())
    top1=sum(m.get('phase')=='top1_reached' for m in by_index.values())
    top10=sum(m.get('top10ReachedOnNominalDevelopment') is True for m in by_index.values())
    counted=root.get('count') if isinstance(root.get('count'),int) else len(by_index)
    if selected is not None:
        d=selected['status']
        protocol=read_json(selected['path']/'protocol.json')
        map_file=read_json(selected['path']/'map.json')
        dev=d.get('bestDevelopment') or {}
        num=int(d.get('mapIndex') or map_file.get('index') or selected['path'].name)
        record=by_index.get(num,{})
        goal=record.get('goal') or map_file
        target=d.get('targetMs',goal.get('top1TargetMs'))
        best=dev.get('bestMs')
        if best is not None and target is not None:
            delta=best-target
        else:delta=None
        population=protocol.get('population',16)
        cases=protocol.get('developmentCases',4)
        seconds=d.get('generationSeconds') or d.get('seconds')
        evals=(population*cases/seconds if isinstance(seconds,(float,int)) and seconds>0 else None)
        ticks=d.get('simulatedTicks')
        native_sps=d.get('nativeStepsPerSecond')
        gen_sps=d.get('generationStepsPerSecond')
        a={'mapIndex':num,'mapName':map_file.get('name') or goal.get('name') or f'Map {num:02}',
           'generation':d.get('generation'),'generationMax':protocol.get('maxGenerations'),
           'staleGenerations':d.get('stale'),'population':population,
           'developmentCases':cases,'evalsPerSec':evals,
           'genSeconds':seconds,'simulatedTicks':ticks,
           'nativeStepsPerSecond':native_sps,
           'generationStepsPerSecond':gen_sps,
           'bestMs':best,'meanMs':dev.get('meanMs'),'worstMs':dev.get('worstMs'),
           'targetMs':target,'deltaMs':delta,
           'worldBestMs':d.get('worldBestMs',goal.get('worldBestMs')),
           'top10Ms':d.get('top10TargetMs',goal.get('top10TargetMs')),
           'finishes':dev.get('finishes'),'trials':dev.get('count'),
           'targetFinishes':dev.get('targetFinishes'),
           'stage':selected['path'].parent.name,
           'stageStatus':selected['state'].lower(),
           'stageId':selected['id'],'phase':d.get('phase') or record.get('phase'),
           'stale':selected['age'],
           'lastUpdate':time.strftime('%H:%M:%S',time.localtime(selected['mtime'])),
           'nominal':read_json(selected['path']/'nominal64.json'),
           'perturbed':read_json(selected['path']/'perturbed64.json'),
           'stopReason':d.get('stopReason')}
    else:
        a={'mapIndex':None,'mapName':'—','generation':None,
           'nativeStepsPerSecond':None,'simulatedTicks':None,
           'evalsPerSec':None,'bestMs':None,'meanMs':None,'targetMs':None,
           'deltaMs':None,'stale':r['age']}
    summary={
        'run':r['id'],'path':str(r['path']),'name':r['name'],
        'state':r['state'].lower(),'live':r['live'],'kind':r['kind'],
        'algorithm':'STAGED WORLD-RECORD SEARCH',
        'targetRank':root.get('targetRank',1),
        'mapsDone':sum(m.get('attempts',0)>0 for m in by_index.values()),
        'mapsTotal':counted,
        'mapsPassed':goals,'mapsTop1':top1,'mapsTop10':top10,
        'mapsQueued':sum(m.get('state')=='queued' for m in by_index.values()),
        'activeMapIndices':root.get('activeMaps') if root_entry else [a.get('mapIndex')],
        'activeMapCount':len(root.get('activeMaps',[])) if root_entry else int(r['live']),
        'activeDetails':[
            {'mapIndex':x['status'].get('mapIndex'),
             'generation':x['status'].get('generation'),
             'bestMs':(x['status'].get('bestDevelopment') or {}).get('bestMs'),
             'nativeStepsPerSecond':x['status'].get('nativeStepsPerSecond'),
             'state':x['state']}
            for x in active] if root_entry else [],
        'nativeSpsAggregate':sum(
            x['status'].get('nativeStepsPerSecond') or 0 for x in active)
            if active else None,
        'parallelLimit':root.get('maxParallelMaps'),
        'workersPerMap':root.get('workersPerMap'),
        'failedMaps':len(root.get('failedMaps') or []),
        'realGame':False,'assisted':True,
        'pid':r.get('pid'),
        'gameAccessed':bool(root.get('gameAccessed')),
    }
    summary.update(a)
    return summary
