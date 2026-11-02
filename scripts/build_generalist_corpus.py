"""Freeze disjoint whole-map splits for one shared policy, never replay splits.

Map UID, identical geometry and declared map families are indivisible groups.
Previously trained maps must remain in training. Geometry fingerprints ignore
map name/UID/author; they catch exact layout copies, not every edited remix.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def build(a):
    if a.output.exists():raise ValueError('Output must be new')
    original=json.loads(a.manifest.read_text())
    families=json.loads(a.families.read_text()) if a.families else {}
    maps={}
    for row in original['pairs']:
        uid=row['mapUid'];path=ROOT/row['mapGbx'];meta=ROOT/row['mapJson'];replay=ROOT/row['replayGbx']
        digest=sha(path)
        if row.get('mapSha256',digest)!=digest:raise ValueError('Map hash differs: '+str(path))
        if row.get('replaySha256',sha(replay))!=sha(replay):raise ValueError('Replay hash differs')
        data=json.loads(meta.read_text())
        if data['uid']!=uid:raise ValueError('Metadata UID differs')
        entry=maps.setdefault(uid,dict(mapUid=uid,map=row['mapGbx'],mapJson=row['mapJson'],
            mapSha256=digest,name=row['mapName'],demonstrations=[]))
        if entry['mapSha256']!=digest:raise ValueError('Same UID has different map bytes')
        entry['demonstrations'].append(dict(path=row['replayGbx'],sha256=sha(replay)))
    for path in a.extra_map:
        path=path.resolve(strict=True);meta=path.with_suffix('.json')
        data=json.loads(meta.read_text());uid=data['uid']
        entry=dict(mapUid=uid,map=path.relative_to(ROOT).as_posix(),mapJson=meta.relative_to(ROOT).as_posix(),
                   mapSha256=sha(path),name=data['mapName'],demonstrations=[])
        if uid in maps and maps[uid]['mapSha256']!=entry['mapSha256']:raise ValueError('Extra map UID conflict')
        maps.setdefault(uid,entry)
    parent={uid:uid for uid in maps}
    if not set(families).issubset(maps):
        raise ValueError('A declared family contains an unknown map UID')
    def find(uid):
        while parent[uid]!=uid:
            parent[uid]=parent[parent[uid]];uid=parent[uid]
        return uid
    def union(left,right):
        left,right=find(left),find(right)
        if left!=right:parent[max(left,right)]=min(left,right)
    groups={}
    for uid,entry in maps.items():
        data=json.loads((ROOT/entry['mapJson']).read_text())
        # Geometry metadata only, no names, replay results or author labels.
        geometry=dict(blocks=data.get('blocks',[]),items=data.get('items',[]))
        encoded=json.dumps(geometry,sort_keys=True,separators=(',',':')).encode()
        fingerprint=hashlib.sha256(encoded).hexdigest();entry['layoutFingerprint']=fingerprint
        for key in [('layout',fingerprint),('file',entry['mapSha256'])]+([('family',families[uid])] if uid in families else []):
            if key in groups:union(uid,groups[key])
            else:groups[key]=uid
    clustered={}
    for uid in maps:clustered.setdefault(find(uid),[]).append(uid)
    known=set(a.known_training_uid)
    if not known.issubset(maps):raise ValueError('A known training UID is missing from the corpus')
    forced={group for group,members in clustered.items() if known.intersection(members)}
    available=[group for group in clustered if group not in forced]
    available.sort(key=lambda group:hashlib.sha256((str(a.seed)+'|'+group).encode()).digest())
    if len(available)<3:raise ValueError('Not enough unseen independent map groups for three splits')
    nv=max(1,math.floor(len(available)*.15));nt=max(1,math.floor(len(available)*.2))
    assignment={g:'train' for g in forced}
    assignment.update({g:'validation' if i<nv else 'test' if i<nv+nt else 'train' for i,g in enumerate(available)})
    splits={key:[] for key in ('train','validation','test')}
    for group,members in clustered.items():
        for uid in sorted(members):
            maps[uid]['leakageGroup']=group;splits[assignment[group]].append(maps[uid])
    for left in splits:
        for right in splits:
            if left>=right:continue
            for field in ('mapUid','mapSha256','layoutFingerprint','leakageGroup'):
                if {x[field] for x in splits[left]} & {x[field] for x in splits[right]}:
                    raise AssertionError('Cross-split leakage: '+field)
    result=dict(schema='tm2020_generalist_whole_map_split_v1',seed=a.seed,
        splits=splits,knownTrainingUids=sorted(known),families=families,
        counts={k:len(v) for k,v in splits.items()},independentGroups=len(clustered),
        holdoutReplaysMayBeUsedForTraining=False,replayOrAuthorGhostRequiredAtInference=False,
        mapUidOrNameAllowedInPolicyInput=False,heldoutMustStartAtRaceZero=True,
        allowHeldoutExpertResetSnapshots=False,mechanicCoverageAnnotated=False,
        representativeGeneralizationBenchmark=False,
        limitations=['Small existing corpus dominated by TAS, edited maps and niche mechanics',
            'Exact layout signature does not detect every rotation, translation or hand-edited remix',
            'Simulator support and live observation parity must be qualified separately for every group'])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('FROZEN WHOLE-MAP SPLITS',result['counts'],'groups',len(clustered))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,default=ROOT/'local/corpus/manifest.json')
    p.add_argument('--extra-map',type=Path,action='append',default=[])
    p.add_argument('--known-training-uid',action='append',default=[])
    p.add_argument('--families',type=Path)
    p.add_argument('--seed',type=int,default=381026)
    p.add_argument('--output',type=Path,required=True)
    build(p.parse_args())
