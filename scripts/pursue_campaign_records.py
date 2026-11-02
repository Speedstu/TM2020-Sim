#!/usr/bin/env python3
"""Local simulator campaign search: every map Top 10, then every map Top 1.

No client activation, leaderboard writes, hourly timer or PPO service. Each
bounded stage stops on plateau; later stages vary the basis, spread and RNG.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime,timezone
from campaign_targets import set_goal,milestone,cached_goal_passed,goal_for_rank
from prepare_fall_campaign import fetch,save_json,save
from run_fast_ppo import ROOT
from campaign_resources import available_memory_mb,process_rss_mb,can_admit,live_client_running

STOP=False
def stop(*_):
    global STOP
    STOP=True


def development_key(result):
    d=result.get('development',{});rows=d.get('trials',[])
    nominal=rows[0].get('finishMs') if rows else None
    if nominal is None:
        # Keep a stage's improved approach to the first finish. Previously
        # every all-DNF stage tied, losing its checkpoint/progress gains.
        first=rows[0] if rows else {}
        return (0,first.get('checkpoints',0),first.get('maximumReferenceIndex',0),
            d.get('finishes',0),sum(r.get('checkpoints',0) for r in rows),
            sum(r.get('maximumReferenceIndex',0) for r in rows))
    return (int(nominal is not None),-(nominal if nominal is not None else 10**9),
        d.get('finishes',0),-(d.get('meanMs') or 10**9))


def campaign_plan(states,configs,indices,rounds=0):
    """Global barrier: no WR work while any map lacks a qualified Top 10."""
    top10=[i for i in indices if cached_goal_passed(states[i].get('selected'),goal_for_rank(configs[i],10))]
    top1=[i for i in indices if cached_goal_passed(states[i].get('selected'),goal_for_rank(configs[i],1))]
    rank=10 if len(top10)<len(indices) else 1
    reached=set(top10 if rank==10 else top1)
    remaining=[i for i in indices if i not in reached]
    todo=[i for i in remaining if states[i]['state']!='failed_requires_fix' and
        (not rounds or states[i]['attempts']<rounds)]
    todo.sort(key=lambda i:(states[i]['attempts'],i))
    return {'targetRank':rank,'campaignPhase':'all_maps_top10' if rank==10 else 'all_maps_top1',
        'top10QualifiedMaps':top10,'top1QualifiedMaps':top1,'remainingTop10Maps':[i for i in indices if i not in top10],
        'remainingTop1Maps':[i for i in indices if i not in top1],'todo':todo}


def selection_key(result,goal):
    # A faster development lap cannot discard an already qualified milestone.
    return (int(cached_goal_passed(result,goal_for_rank(goal,1))),
        int(cached_goal_passed(result,goal_for_rank(goal,10))),development_key(result))


def adopt_candidate(state,value,goal,directory):
    if value.get('map',{}).get('mapUid')!=goal['mapUid'] or value.get('map',{}).get('mapSha256')!=goal.get('mapSha256'):
        raise ValueError('Incoming candidate belongs to a different map')
    data=Path(value['model']).read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=value['modelSha256']:raise ValueError('Incoming candidate model hash differs')
    if state.get('selected') and selection_key(value,goal)<=selection_key(state['selected'],goal):return False
    snapshot=directory/f'best-{digest[:20]}.tmhyb';save(snapshot,data)
    state.update(selected=dict(value,model=str(snapshot)),bestAsset=str(snapshot))
    state.pop('resumeAsset',None)
    return True


def ingest_candidates(state,goal,directory):
    changed=False
    for path in sorted(directory.glob('incoming-*.json')):
        try:value=json.loads(path.read_text())
        except json.JSONDecodeError:continue
        try:changed=adopt_candidate(state,value,goal,directory) or changed
        except (ValueError,KeyError,OSError) as error:
            archive=directory/'rejected-candidates';archive.mkdir(exist_ok=True)
            save_json(archive/(path.stem+'-error.json'),{'error':str(error)})
        else:
            archive=directory/'imported-candidates';archive.mkdir(exist_ok=True)
        path.replace(archive/path.name)
    return changed


def repair_window(state,length):
    value=state.get('selected') or {}
    development=state.get('resumeDevelopment',{}) if state.get('resumeAsset') else value.get('development',{})
    rows=development.get('trials',[])
    if not rows:return None
    nominal=rows[0]
    if nominal.get('finishMs') is not None:
        # Speed tuning of a completed lap should not perturb its entire
        # successful route at once. Rotate compact sectors instead.
        width=min(900,length-21);span=max(1,length-width-20)
        lo=20+(state.get('attempts',0)*7919)%span
        return (lo,min(length-1,lo+width))
    cursor=nominal.get('maximumReferenceIndex',0)
    if cursor<50:return None
    return (max(20,cursor-650),min(length-1,cursor+150))


def prepare(source,out,indices):
    configs={};states={}
    for index in indices:
        if STOP:break
        d=out/f'{index:02d}';d.mkdir(parents=True,exist_ok=True)
        s=source/f'{index:02d}';m=json.loads((s/'map.json').read_text())
        goal=d/'leaderboard.json'
        if goal.exists():board=json.loads(goal.read_text())
        else:
            raw=json.loads(fetch(f"https://trackmania.io/api/leaderboard/map/{m['mapUid']}?length=10&offset=0"))
            board={'sourceUrl':f"https://trackmania.io/api/leaderboard/map/{m['mapUid']}?length=10&offset=0",
                'fetchedUtc':datetime.now(timezone.utc).isoformat(),
                'tops':[{k:t[k] for k in ('position','time','url')} for t in raw['tops']]}
            save_json(goal,board);time.sleep(2.5)
        m=set_goal(m,board,1);save_json(d/'map.json',m);configs[index]=m
        for name in ('reference.json','reference.f32'):
            if not(d/name).exists():shutil.copy2(s/name,d/name)
        previous=s/'result.json';selected=None
        if previous.exists():
            value=json.loads(previous.read_text())
            if value.get('nominal64',{}).get('internalPhysicalControls') and Path(value['model']).exists():
                data=Path(value['model']).read_bytes()
                if hashlib.sha256(data).hexdigest()==value['modelSha256']:selected=value
        asset=Path(selected['model']) if selected else s/'best.tmhyb'
        if not asset.exists():asset=s/'warm-start.tmhyb'
        if asset.exists():
            data=asset.read_bytes();digest=hashlib.sha256(data).hexdigest()
            snapshot=d/f'incumbent-{digest[:20]}.tmhyb';save(snapshot,data)
            if selected:selected=dict(selected,model=str(snapshot))
            initial=str(snapshot)
        else:initial=None
        state_path=d/'pursuit.json'
        state=json.loads(state_path.read_text()) if state_path.exists() else {
            'index':index,'attempts':0,'selected':selected,'bestAsset':initial,'state':'queued'}
        old_stage=Path(state['currentStage']) if state.get('currentStage') else None
        if state.get('state')=='searching' and old_stage and not(old_stage/'result.json').exists():
            checkpoint=old_stage/'best.tmhyb'
            if checkpoint.exists():
                data=checkpoint.read_bytes();digest=hashlib.sha256(data).hexdigest()
                snapshot=d/f'resume-{digest[:20]}.tmhyb';save(snapshot,data)
                state['resumeAsset']=str(snapshot)
                if (old_stage/'best.json').exists():
                    state['resumeDevelopment']=json.loads((old_stage/'best.json').read_text()).get('development',{})
            state.setdefault('interruptedStages',[]).append(str(old_stage))
            state.update(attempts=state['attempts']+1,state='queued_after_interruption')
        if state.get('selectionProtocol')!='nominal-first-v2':
            # Recover an available older model if aggregate perturbation scores
            # had replaced a better nominal approach. Pruned models are skipped.
            available={hashlib.sha256(p.read_bytes()).hexdigest():p for p in d.glob('*.tmhyb') if p.is_file()}
            for path in out.glob(f'stages/*/{index:02d}/result.json'):
                value=json.loads(path.read_text());model=available.get(value.get('modelSha256'))
                if model:adopt_candidate(state,dict(value,model=str(model)),m,d)
            state['selectionProtocol']='nominal-first-v2'
            state.pop('resumeAsset',None);state.pop('resumeDevelopment',None)
        ingest_candidates(state,m,d)
        state.update(goal=m,simGoalPassed=cached_goal_passed(state['selected'],m) if state.get('selected') else False)
        state['top10SimGoalPassed']=cached_goal_passed(state.get('selected'),goal_for_rank(m,10))
        if state['simGoalPassed']:state['state']='top1_time_reached_in_simulation'
        elif state['top10SimGoalPassed']:state['state']='top10_time_reached_in_simulation'
        states[index]=state;save_json(state_path,state)
        save_json(out/'status.json',{'state':'preparing','prepared':len(states),'total':len(indices),
            'strategy':'all_maps_top10_then_all_maps_top1','gameAccessed':False})
        print(json.dumps({'preparedMap':index,'top10Ms':m['top10TargetMs'],'beatWorldMs':m['targetMs']}),flush=True)
    return configs,states


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--maps',type=int,nargs='+',default=list(range(2,26)))
    p.add_argument('--parallel',type=int,default=2);p.add_argument('--rounds',type=int,default=0,
        help='0: continue changed search stages until all time goals or explicit stop')
    p.add_argument('--generations',type=int,default=128);p.add_argument('--plateau',type=int,default=32)
    p.add_argument('--native-source',type=Path);p.add_argument('--fast-evaluation',action='store_true')
    p.add_argument('--workers-per-map',type=int,default=6)
    p.add_argument('--reserve-memory-mb',type=int,default=6144)
    p.add_argument('--live-client-extra-reserve-mb',type=int,default=4096)
    p.add_argument('--map-memory-mb',type=int,default=4096)
    p.add_argument('--stall-seconds',type=int,default=900)
    a=p.parse_args()
    if not 1<=a.parallel<=4 or not 1<=a.workers_per_map<=16 or a.rounds<0 or not a.maps or any(i not in range(2,26) for i in a.maps):p.error('Invalid worker/map count')
    if a.reserve_memory_mb<1024 or a.live_client_extra_reserve_mb<0 or a.map_memory_mb<1024 or a.stall_seconds<60:p.error('Invalid resource limits')
    out=a.output.resolve();out.mkdir(exist_ok=True,parents=True)
    lock=(out/'PURSUIT.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with (out/'RETENTION.lock').open('a') as retention:
        fcntl.flock(retention,fcntl.LOCK_EX)
        configs,states=prepare(a.source.resolve(),out,a.maps)
    if STOP:
        save_json(out/'status.json',{'state':'stopped_during_preparation','gameAccessed':False});return
    frozen=out/'frozen'
    if a.native_source:
        source=a.native_source.resolve();names=('libtm2020_vector_physics.so','libtm2020_speed.so','libtm2020_trajectory.so')
        digest=hashlib.sha256(b''.join((source/name).read_bytes() for name in names)).hexdigest()
        native=frozen/('native-'+digest[:20]);native.mkdir(exist_ok=True,parents=True)
        for name in names:
            data=(source/name).read_bytes();dest=native/name
            if dest.exists():
                if dest.read_bytes()!=data:raise RuntimeError('Refusing to replace an immutable native image')
            else:save(dest,data)
    else:
        native=frozen/'native';shutil.copytree(a.source/'frozen/native',native,dirs_exist_ok=True)
    api=native/'libtm2020_vector_physics.so';physics=native/'libtm2020_speed.so'
    env=dict(os.environ,TM2020_PHYSICS_WORKERS=str(a.workers_per_map),OPENBLAS_NUM_THREADS='1',TM2020_HYBRID_CORE=str(native/'libtm2020_trajectory.so'))
    active={};progress={}
    try:
        while not STOP:
            client_present=live_client_running()
            effective_reserve=a.reserve_memory_mb+(a.live_client_extra_reserve_mb if client_present else 0)
            for i in a.maps:
                state=states[i]
                if ingest_candidates(state,configs[i],out/f'{i:02d}'):
                    state['simGoalPassed']=cached_goal_passed(state['selected'],configs[i])
                    state['top10SimGoalPassed']=cached_goal_passed(state['selected'],goal_for_rank(configs[i],10))
                    if i in active and cached_goal_passed(state['selected'],goal_for_rank(configs[i],state.get('stageTargetRank',1))):
                        child,_,_=active[i]
                        if child is not None and child.poll() is None:child.terminate()
                    if i not in active:state['state']='top1_time_reached_in_simulation' if state['simGoalPassed'] else (
                        'top10_time_reached_in_simulation' if state['top10SimGoalPassed'] else 'queued_with_changed_search')
                    save_json(out/f'{i:02d}'/'pursuit.json',state)
            schedule=campaign_plan(states,configs,a.maps,a.rounds);todo=schedule['todo']
            if not todo and not active:break
            for i in todo:
                if len(active)>=a.parallel:break
                if i in active:continue
                state=states[i];attempt=state['attempts'];stage=out/'stages'/f'{attempt:03d}'
                d=stage/f'{i:02d}';d.mkdir(parents=True,exist_ok=True)
                stage_goal=goal_for_rank(configs[i],schedule['targetRank'])
                for name in ('leaderboard.json','reference.json','reference.f32'):
                    if not(d/name).exists():shutil.copy2(out/f'{i:02d}'/name,d/name)
                if not(d/'result.json').exists():save_json(d/'map.json',stage_goal)
                command=[sys.executable,str(ROOT/'scripts/optimize_fall_campaign.py'),'--output',str(stage),
                    '--maps',str(i),'--lock-name',f'map-{i:02d}','--api',str(api),'--physics',str(physics),
                    '--internal-controls','--target-rank',str(schedule['targetRank']),'--generations',str(a.generations),'--plateau',str(a.plateau),
                    '--seed-offset',str(104729*(attempt+1)),
                    '--line-width',str((.045,.025,.08)[attempt%3]),
                    '--spread-scale',str((1.,.65,1.5)[attempt%3])]
                if state.get('resumeAsset') or state.get('bestAsset'):command+=['--initial-asset',state.get('resumeAsset') or state['bestAsset']]
                if a.fast_evaluation:command.append('--fast-evaluation')
                if schedule['targetRank']==10:
                    command.append('--nominal-priority')
                    frames=json.loads((d/'reference.json').read_text())['rows']
                    window=repair_window(state,frames)
                    if window is not None and attempt%3!=0:
                        command+=['--local-window',*map(str,window),'--pedal-timing']
                if (d/'result.json').exists():child=None;log=None
                else:
                    running=[process_rss_mb(c.pid) for c,_,_ in active.values() if c is not None and c.poll() is None]
                    if not can_admit(available_memory_mb(),effective_reserve,a.map_memory_mb,running):break
                    log=(d/'search.log').open('a');child=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
                active[i]=(child,log,d);state.update(state='searching',currentStage=str(d),stageTargetRank=schedule['targetRank'])
                progress[i]={'last':time.monotonic(),'mtime':None,'terminateAt':None}
                save_json(out/f'{i:02d}'/'pursuit.json',state)
            for i,(child,log,d) in list(active.items()):
                if child is not None and child.poll() is None:
                    info=progress[i];path=d/'status.json'
                    mtime=path.stat().st_mtime_ns if path.exists() else None
                    if mtime!=info['mtime']:info.update(last=time.monotonic(),mtime=mtime)
                    if time.monotonic()-info['last']>a.stall_seconds and info['terminateAt'] is None:
                        child.terminate();info['terminateAt']=time.monotonic()
                        states[i]['watchdogStop']=True
                    if info['terminateAt'] is not None and time.monotonic()-info['terminateAt']>30:child.kill()
                    continue
                if log:log.close()
                state=states[i];path=d/'result.json'
                if not path.exists():
                    state.update(state='failed_requires_fix',error=(d/'search.log').read_text()[-1400:] if (d/'search.log').exists() else 'Missing result')
                    save_json(out/f'{i:02d}'/'pursuit.json',state)
                    print(json.dumps({'map':i,'state':state['state'],'reason':'Stage failed; retained incumbent, continuing other maps'}),flush=True)
                    del active[i];del progress[i];continue
                candidate=json.loads(path.read_text())
                if not state.get('selected') or selection_key(candidate,configs[i])>selection_key(state['selected'],configs[i]):
                    data=Path(candidate['model']).read_bytes();digest=hashlib.sha256(data).hexdigest()
                    if digest!=candidate['modelSha256']:raise ValueError('Candidate changed after evaluation')
                    model=out/f'{i:02d}'/f'best-{digest[:20]}.tmhyb';save(model,data)
                    state.update(selected=dict(candidate,model=str(model)),bestAsset=str(model))
                state['attempts']+=1;state['lastResult']=str(path)
                state.pop('resumeAsset',None)
                state['simGoalPassed']=cached_goal_passed(state['selected'],configs[i])
                state['top10SimGoalPassed']=cached_goal_passed(state['selected'],goal_for_rank(configs[i],10))
                state['state']='top1_time_reached_in_simulation' if state['simGoalPassed'] else (
                    'top10_time_reached_in_simulation' if state['top10SimGoalPassed'] else 'queued_with_changed_search')
                state.update(milestone(state['selected'].get('development',{}),configs[i]))
                save_json(out/f'{i:02d}'/'pursuit.json',state)
                print(json.dumps({'map':i,'attempts':state['attempts'],'state':state['state'],
                    'nominalMs':state['selected']['nominal64']['bestMs'],
                    'targetRank':state.get('stageTargetRank'),
                    'targetMs':goal_for_rank(configs[i],state.get('stageTargetRank',1))['targetMs']}),flush=True)
                del active[i];del progress[i]
            schedule=campaign_plan(states,configs,a.maps,a.rounds)
            report={'state':'searching','ultimateTargetRank':1,
                'strategy':'all_maps_top10_then_all_maps_top1','gameAccessed':False,
                'hourlyMonitor':False,'activeMaps':sorted(active),'maps':[states[i] for i in a.maps],
                'simGoalsReached':sum(s['simGoalPassed'] for s in states.values()),'count':len(states),
                'fastWholeRaceEvaluation':a.fast_evaluation,'nativeDirectory':str(native)}
            report.update({k:v for k,v in schedule.items() if k!='todo'})
            report.update(top10SimGoalsReached=len(schedule['top10QualifiedMaps']),
                top1SimGoalsReached=len(schedule['top1QualifiedMaps']))
            report.update(maxParallelMaps=a.parallel,workersPerMap=a.workers_per_map,
                availableMemoryMb=available_memory_mb(),reserveMemoryMb=a.reserve_memory_mb,
                liveClientDetected=client_present,effectiveReserveMemoryMb=effective_reserve,
                mapMemoryReservationMb=a.map_memory_mb,
                failedMaps=[i for i in a.maps if states[i]['state']=='failed_requires_fix'])
            save_json(out/'status.json',report)
            if STOP:break
            time.sleep(1)
    finally:
        deadline=time.monotonic()+50
        for child,_,_ in active.values():
            if child is not None and child.poll() is None:child.terminate()
        for child,log,_ in active.values():
            if child is not None and child.poll() is None:
                try:child.wait(timeout=max(.1,deadline-time.monotonic()))
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            if log:log.close()
        prior=json.loads((out/'status.json').read_text())
        reached=all(s['simGoalPassed'] for s in states.values())
        prior.update(state='all_time_goals_reached_in_simulation' if reached else 'stopped',gameAccessed=False)
        save_json(out/'status.json',prior)


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
