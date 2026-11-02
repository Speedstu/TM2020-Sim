#!/usr/bin/env python3
"""Keep campaign model history bounded without touching active runs or evidence.

Only finalized campaign stages acknowledged by pursuit.json are eligible.
Keep the latest N stages and snapshots per map, plus all currently referenced
models. Reports, client traces, replays, source assets and native DLLs stay.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time
from prepare_fall_campaign import save_json

STOP=False
MODEL=re.compile(r'(?:best|incumbent|resume)-[0-9a-f]{20}\.tmhyb\Z')
CANDIDATE=re.compile(r'candidate-[0-9]+\.tmhyb\Z')


def stop(*_):
    global STOP
    STOP=True


def references(value,root):
    result=set()
    if isinstance(value,dict):
        for v in value.values():result.update(references(v,root))
    elif isinstance(value,list):
        for v in value:result.update(references(v,root))
    elif isinstance(value,str):
        p=Path(value)
        if p.is_absolute() and p.is_relative_to(root):result.add(p)
    return result


def plan(root,keep=3):
    root=Path(root).resolve(strict=True)
    if keep<1:raise ValueError('Keep at least one historical version')
    protected=set();states={};eligible=[];duplicates=[]
    for path in sorted(root.glob('??/pursuit.json')):
        if not path.parent.name.isdigit() or path.is_symlink() or path.parent.is_symlink():continue
        state=json.loads(path.read_text())
        if state.get('index')!=int(path.parent.name) or not isinstance(state.get('attempts'),int):
            raise ValueError('Invalid pursuit identity; cleanup refused')
        states[path.parent.name]=state;protected.update(references(state,root))
    if not states:raise ValueError('No valid campaign state; cleanup refused')
    for map_id,state in states.items():
        completed=[]
        for stage in root.glob(f'stages/[0-9]*/{map_id}'):
            if stage.is_symlink() or stage.parent.is_symlink() or not stage.parent.name.isdigit():continue
            if int(stage.parent.name)>=state['attempts'] or not(stage/'result.json').is_file():continue
            # Parent acknowledgement comes after child exit and model copying.
            if stage in protected or str(stage)==state.get('currentStage'):continue
            completed.append(stage)
        completed.sort(key=lambda p:int(p.parent.name),reverse=True)
        for stage in completed[keep:]:
            for path in stage.glob('*.tmhyb'):
                if path.name not in ('initial.tmhyb','best.tmhyb') and not CANDIDATE.fullmatch(path.name):continue
                if path in protected or path.is_symlink() or not path.is_file():continue
                eligible.append(path)
            # Preserve the historical reference path, sharing immutable bytes
            # with the map's original reference instead of storing each copy.
            duplicate=stage/'reference.f32';canonical=root/map_id/'reference.f32'
            if duplicate.is_file() and not duplicate.is_symlink() and canonical.is_file() and not canonical.is_symlink():
                if duplicate.stat().st_size==canonical.stat().st_size:
                    if hashlib.sha256(duplicate.read_bytes()).digest()==hashlib.sha256(canonical.read_bytes()).digest():
                        duplicates.append((duplicate,canonical))
        snapshots=[p for p in (root/map_id).glob('*.tmhyb')
            if MODEL.fullmatch(p.name) and not p.is_symlink() and p.is_file()]
        snapshots.sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
        for path in snapshots[keep:]:
            if path not in protected:eligible.append(path)
    return eligible,duplicates,protected


def sweep(root,keep=3,apply=False):
    root=Path(root).resolve(strict=True)
    with (root/'RETENTION.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        files,duplicates,protected=plan(root,keep)
        sizes={p:p.stat().st_size for p in files}
        report={'updatedUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'apply':apply,
            'keepRecentStagesPerMap':keep,'keepRecentSnapshotsPerMap':keep,
            'protectedReferences':len(protected),'removableModels':len(files),
            'removableBytes':sum(sizes.values()),'deduplicateReferences':len(duplicates),
            'deduplicateBytes':sum(p.stat().st_size for p,_ in duplicates),
            'removedModels':0,'removedBytes':0,'deduplicatedReferences':0,
            'scope':'completed simulator stages only; reports/client evidence untouched'}
        if apply:
            by_stage={}
            for path in files:
                by_stage.setdefault(path.parent,[]).append({'name':path.name,'bytes':sizes[path],
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            for parent,entries in by_stage.items():
                marker=parent/'retention-pruned-models.json'
                previous=json.loads(marker.read_text()).get('models',[]) if marker.exists() else []
                save_json(marker,{'reason':'superseded unreferenced model history','models':previous+entries})
            # Re-read references before deletion; a newer incumbent or stage
            # selected during planning must never be removed.
            _,_,fresh_protected=plan(root,keep)
            for path in files:
                if path in fresh_protected or path.parent in fresh_protected:continue
                path.unlink();report['removedModels']+=1;report['removedBytes']+=sizes[path]
            for path,canonical in duplicates:
                temporary=path.with_name('.retention-reference-link')
                if temporary.exists() or temporary.is_symlink():raise RuntimeError('Unexpected reference link temporary')
                temporary.symlink_to(os.path.relpath(canonical,path.parent));temporary.replace(path)
                report['deduplicatedReferences']+=1
            save_json(root/'retention-status.json',report)
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--keep',type=int,default=3);p.add_argument('--apply',action='store_true')
    p.add_argument('--watch',action='store_true');p.add_argument('--interval',type=int,default=300)
    a=p.parse_args()
    if a.interval<10:p.error('Interval must be at least ten seconds')
    while not STOP:
        print(json.dumps(sweep(a.root,a.keep,a.apply)),flush=True)
        if not a.watch:break
        deadline=time.monotonic()+a.interval
        while not STOP and time.monotonic()<deadline:time.sleep(max(0.,min(1.,deadline-time.monotonic())))


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
