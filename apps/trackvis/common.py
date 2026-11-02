"""Read-only multi-backend Trackmania training telemetry.

PPO actor-critic jobs and the newer hybrid (tmhyb) 16-candidate,
four-evaluation-per-candidate generation searches are fundamentally different.
Never convert generations to PPO steps, or evaluations/s to physics SPS.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from pursuit import discover as discover_pursuits, details as pursuit_details

ROOT = Path(__file__).resolve().parents[2]
TRAINING = ROOT / 'local' / 'training'
RUN_CACHE = (0., ())
PROCESS_CACHE = (0., {})


def safe_json(path):
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _process_outputs():
    """Process-derived optimizer output roots, read-only and PID-safe."""
    global PROCESS_CACHE
    now = time.monotonic()
    if now - PROCESS_CACHE[0] < 2:
        return PROCESS_CACHE[1]
    found = {}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            if not any(b'optimize_fall_campaign.py' in a for a in args):
                continue
            options = [os.fsdecode(x) for x in args if x]
            if '--output' not in options:
                continue
            i = options.index('--output')
            if i + 1 >= len(options):
                continue
            output = Path(options[i+1])
            if not output.is_absolute():
                output = Path(os.readlink(proc / 'cwd')) / output
            found[output.resolve()] = int(proc.name)
        except (OSError,ValueError,IndexError):
            continue
    PROCESS_CACHE = (now,found)
    return found


def _pid_belongs(pid, path: Path):
    if not isinstance(pid,int) or pid < 2:
        return False
    try:
        return str(path).encode() in (Path('/proc')/str(pid)/'cmdline').read_bytes()
    except (OSError,ValueError):
        return False


def _discover():
    results = discover_pursuits(TRAINING)
    known_ids = {r['id'] for r in results}
    process_outputs = _process_outputs()
    now = time.time()
    # Freshness and presence of the matching optimizer process both required
    # for declaring a campaign map LIVE; no false 'running' for stale JSON.
    for parent in TRAINING.iterdir():
        if not parent.is_dir():
            continue
        group_entries = []
        for status in parent.glob('*/status.json'):
            folder = status.parent
            if not (folder.name.isdigit() and len(folder.name) == 2):
                continue
            d = safe_json(status)
            if 'generation' not in d or 'bestDevelopment' not in d:
                continue
            try:
                modified = status.stat().st_mtime
            except OSError:
                continue
            name = folder.relative_to(TRAINING).as_posix()
            age = max(0.,now-modified)
            proc = process_outputs.get(parent.resolve())
            live = bool(proc and age < 70 and d.get('state')=='optimizing')
            finished = (folder/'result.json').is_file()
            state = ('RUNNING' if live else
                     'STOPPED' if finished or d.get('state')=='stopped' else
                     'STALE' if d.get('state')=='optimizing' else
                     str(d.get('state','unknown')).upper())
            entry = {'id':name,'name':folder.name,'path':folder,'state':state,
                     'live':live,'mtime':modified,'age':age,'status':d,
                     'kind':'campaign-map','parent':parent,'pid':proc}
            group_entries.append(entry)
            results.append(entry)
        if group_entries:
            # An optimizer is sequential over its maps: show a single
            # parent session with progress, and map entries for drill-down.
            candidate = max(group_entries,key=lambda x:x['mtime'])
            running = [x for x in group_entries if x['live']]
            if running:
                candidate = max(running,key=lambda x:x['mtime'])
            proc = process_outputs.get(parent.resolve())
            live = bool(running)
            group_state = ('RUNNING' if live else
                           'STOPPED' if proc is None else 'ACTIVE / BETWEEN MAPS')
            root_id = parent.relative_to(TRAINING).as_posix()
            results.append({'id':root_id,'name':parent.name,'path':parent,
                    'state':group_state,'live':live,'mtime':candidate['mtime'],
                    'age':candidate['age'],'status':candidate['status'],
                    'kind':'campaign-group','parent':parent,'pid':proc,
                    'current':candidate,'children':group_entries})
    # Legacy PPO and single-run training jobs with top-level status files.
    for p in TRAINING.rglob('status.json'):
        folder=p.parent
        name=folder.relative_to(TRAINING).as_posix()
        if name in known_ids:
            continue
        if folder.name.isdigit() and len(folder.name)==2 and 'generation' in safe_json(p):
            continue
        d=safe_json(p)
        # The 0.57 root is a campaign orchestrator, not PPO. A stale or
        # partially written root should not masquerade as a PPO run.
        if 'activeMaps' in d and 'targetRank' in d:
            continue
        if not d:
            continue
        try: modified=p.stat().st_mtime
        except OSError:continue
        age=max(0.,now-modified)
        raw=str(d.get('state','unknown')).lower()
        pid=d.get('pid')
        live=raw=='training' and (
            _pid_belongs(pid,folder) if isinstance(pid,int) else age<40)
        state=('RUNNING' if live else 'STALE' if raw=='training' else raw.upper())
        results.append({'id':folder.relative_to(TRAINING).as_posix(),
                       'name':folder.name,'path':folder,'state':state,
                       'live':live,'mtime':modified,'age':age,'status':d,
                       'kind':'ppo','pid':pid})
    # Puts the two active sessions first, then live map entries, then history.
    priority={'pursuit-group':0,'pursuit-map':1,'campaign-group':2,'campaign-map':3,'ppo':4}
    results.sort(key=lambda r:(not r['live'],
                priority.get(r['kind'],3),-r['mtime'],r['id']))
    return results


def discover_runs():
    global RUN_CACHE
    now=time.monotonic()
    if now-RUN_CACHE[0] < .45:
        return list(RUN_CACHE[1])
    runs=_discover()
    RUN_CACHE=(now,tuple(runs))
    return runs


def resolve_run(query=None,items=None):
    runs=discover_runs() if items is None else items
    if query is None or str(query).strip().lower() in ('auto','active'):
        # Prefer an active session (not the last touched child) for stability.
        # Stable default: dedicated Fall 01 record session > campaign-wide
        # optimizer > other live runners. Prevent tab flicker between two live
        # JSON files whose write times interleave every few seconds.
        newest_pursuit=next((r for r in runs if r['live'] and r['kind']=='pursuit-group'),None)
        main=next((r for r in runs if r['live'] and r['kind']=='campaign-group'
                   and 'fall01-record' in r['id']),None)
        campaign=next((r for r in runs if r['live'] and r['kind']=='campaign-group'),None)
        return newest_pursuit or main or campaign or next((r for r in runs if r['live']),None) or (runs[0] if runs else None)
    q=str(query).strip().rstrip('/')
    for prefix in (str(TRAINING)+'/', 'local/training/'):
        if q.startswith(prefix):q=q[len(prefix):]
    exact=[r for r in runs if q==r['id']]
    matches=exact or [r for r in runs if q==r['name']]
    if len(matches)>1:
        raise ValueError(f'Ambiguous run {query!r}: ' + ', '.join(x['id'] for x in matches))
    if matches:return matches[0]
    raise ValueError(f'Unknown run {query!r}. See trackstat --list.')


def _campaign_progress(parent,children):
    total = sum(1 for p in parent.iterdir()
                if p.is_dir() and len(p.name)==2 and p.name.isdigit()
                and (p/'map.json').exists())
    done = sum((r['path']/'result.json').exists() for r in children)
    passed=0
    robust=0
    for r in children:
        result=safe_json(r['path']/'result.json')
        if result.get('simGoalPassed'):passed+=1
        if result.get('robustSimGoalPassed'):robust+=1
    return {'mapsDone':done,'mapsTotal':total,'mapsPassed':passed,'mapsRobust':robust}


def _campaign_stats(r):
    selected=r['current'] if r['kind']=='campaign-group' else r
    d=selected['status']
    dev=d.get('bestDevelopment') or {}
    best=d.get('best') or {}
    protocol=safe_json(selected['path']/'protocol.json')
    pmap=protocol.get('map') or safe_json(selected['path']/'map.json')
    population=protocol.get('population') or 16
    trials_per=protocol.get('developmentCases') or 4
    elapsed=d.get('seconds')
    # Evaluations/sec is NOT simulator physics steps/sec.
    evals_per_second=(population*trials_per/elapsed
        if isinstance(elapsed,(int,float)) and elapsed>0 else None)
    gen=d.get('generation')
    progress=_campaign_progress(selected['parent'],
                  r.get('children') if r['kind']=='campaign-group'
                  else [p for p in discover_runs()
                        if p['kind']=='campaign-map' and p['parent']==selected['parent']])
    target=d.get('targetMs',pmap.get('targetMs'))
    best_ms=dev.get('bestMs')
    if best_ms is None:
        delta=None
    elif isinstance(target,(int,float)):
        delta=best_ms-target
    else:
        delta=None
    return {'run':r['id'],'name':r['name'],'path':str(r['path']),
        'state':r['state'].lower(),'live':r['live'],
        'kind':r['kind'],'algorithm':'HYBRID SEARCH',
        'mapName':pmap.get('name') or f'Fall 2026 - {int(d.get("mapIndex",0)):02}',
        'mapIndex':d.get('mapIndex',pmap.get('index')),
        'generation':gen,'generationMax':protocol.get('maxGenerations'),
        'staleGenerations':d.get('stale'),
        'population':population,'developmentCases':trials_per,
        'evalsPerSec':evals_per_second,'genSeconds':elapsed,
        'seconds':d.get('wallSeconds'),'bestMs':best_ms,
        'meanMs':dev.get('meanMs'),'worstMs':dev.get('worstMs'),
        'targetMs':target,'deltaMs':delta,
        'finishes':dev.get('finishes'),'trials':dev.get('count'),
        'targetFinishes':dev.get('targetFinishes'),
        'realGame':False,'assisted':bool(dev.get('referenceAssisted',True)),
        'mapsDone':progress['mapsDone'],'mapsTotal':progress['mapsTotal'],
        'mapsPassed':progress['mapsPassed'],'mapsRobust':progress['mapsRobust'],
        'pid':r.get('pid'),'stale':r['age'],'lastUpdate':time.strftime('%H:%M:%S',time.localtime(r['mtime'])),
        'stopReason':d.get('stopReason'),'simGoalPassed':d.get('simGoalPassed'),
        'nominal':safe_json(selected['path']/'nominal64.json'),
        'perturbed':safe_json(selected['path']/'perturbed64.json')}


def _ppo_stats(r):
    d=r['status'];b=d.get('best') or {}
    if not isinstance(b,dict):b={}
    sps=d.get('wallSps')
    if sps is None:sps=d.get('wallSpsIncludingEvaluations',d.get('sps'))
    if sps is None:
        u=d.get('lastUpdate')
        if isinstance(u,dict) and u.get('seconds'):
            sps=u.get('transitions',0)/u['seconds']
    return {'run':r['id'],'name':r['name'],'path':str(r['path']),
       'kind':'ppo','algorithm':'PPO','state':r['state'].lower(),'live':r['live'],
       'update':d.get('update',0),'transitions':d.get('transitions',0),'sps':sps,
       'gpu':d.get('gpu',d.get('device','—')),
       'bestMs':b.get('bestMs',d.get('latestBestMs')),
       'meanMs':b.get('meanMs',d.get('bestPenalizedMeanMs')),
       'finishes':b.get('finishes',d.get('bestFinishes')),
       'trials':b.get('count',d.get('holdoutTrials')),
       'phase':d.get('phase',d.get('recoveries',0)),
       'lastUpdate':d.get('updatedAt','—'),
       'realGame':d.get('realGameVerified',d.get('realGameFinishVerified',False)),
       'targetMs':d.get('targetMs'),'sectionSuccessRate':d.get('sectionSuccessRate'),
       'pid':d.get('pid'),'stale':r['age']}


def load_stats(run=None):
    r=resolve_run(run)
    if r is None:
        return {'run':'—','state':'no runs','live':False,'kind':'none',
                'algorithm':'—','bestMs':None,'meanMs':None,'realGame':False,
                'pid':None,'stale':None}
    return (pursuit_details(r) if r['kind'].startswith('pursuit') else
            _campaign_stats(r) if r['kind'].startswith('campaign') else _ppo_stats(r))


def active_run():
    """Kept for TrackVis: only a PPO run supports its old PyTorch model."""
    runs=discover_runs()
    r=next((x for x in runs if x['kind']=='ppo' and x['live']),None)
    if r is None:
        r=next((x for x in runs if x['kind']=='ppo'),None)
    return (r['path'],r['status']) if r else (TRAINING,{})


def fmt_time(ms):
    if ms is None:return '—'
    try:return f'{float(ms)/1000:.3f}s'
    except (ValueError,TypeError):return '—'


def fmt_num(x):
    try:return f'{int(x):,}'.replace(',',' ')
    except (ValueError,TypeError):return '—'


def model_path():
    root,_=active_run()
    for p in (root/'best.pt',ROOT/'local/training/top10-20261030/ppo20/best.pt',
              ROOT/'local/training/discrete33-antiplateau-20261030/best.pt'):
        if p.exists():return p
    return None
