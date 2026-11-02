"""Summarize all retained native driving trials, including failures.

This is historical experiment evidence, not automatic verification of a finish,
offline session identity, physical ownership, or the quality of a new build.
"""
import csv
import json
import math
from pathlib import Path
import struct
import hashlib

ROOT=Path(__file__).resolve().parents[1]
reference=ROOT/'local/campaign-2026-autumn/native-replays/4634.tmreplay'
b=reference.read_bytes()
if b[:8]!=b'TMRDSV1\0':raise ValueError('Unsupported reference format')
version,n,events,finish,interval=struct.unpack_from('<IIIii',b,8)
if version!=1 or n>100000:raise ValueError('Invalid reference header')
offset=28
for _ in range(2):
    size=struct.unpack_from('<H',b,offset)[0];offset+=2+size
record=struct.Struct('<i16d5B')
waypoints=sum(record.unpack_from(b,offset+i*record.size)[0]<=finish for i in range(n))
if waypoints<2:raise ValueError('Insufficient reference route')
trials=[]
finishes=[]
for evidence in sorted((ROOT/'local/recon').glob('finish-*.json')):
    proof=json.loads(evidence.read_text(encoding='utf-8-sig'))
    if not(proof.get('gameFinishUiObserved') and proof.get('gameGeneratedReplayConfirmsFinish')):continue
    def checked_artifact(name,key):
        path=(ROOT/proof[name]).resolve()
        return path.is_relative_to(ROOT) and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==proof[key]
    if checked_artifact('screen','screenSha256') and checked_artifact('savedReplay','savedReplaySha256'):
        finishes.append({'trial':proof['trial'],'evidence':str(evidence.relative_to(ROOT)).replace('\\','/'),
            'displayed_record_ms':proof['displayedPersonalRecordMs'],'saved_replay_time':proof['savedReplayRaceTime'],
            'official_trial_time_ms':proof.get('officialTrialTimeMs',proof['displayedPersonalRecordMs']),
            'includes_idle_discovery_time':proof['includesIdleDiscoveryTime']})
for file in sorted((ROOT/'local/recon').glob('codex-follower-*.csv')):
    with file.open(newline='') as f:
        reader=csv.DictReader(f);rows=list(reader)
        if reader.fieldnames and 'nearest_sample' not in reader.fieldnames:continue
    numeric=[]
    for row in rows:
        try:
            values={k:float(row[k]) for k in ('wall_s','x','y','z','reference_error_m','nearest_sample','command_steer','gas')}
            if not all(math.isfinite(x) for x in values.values()):continue
            numeric.append(values)
        except (KeyError,TypeError,ValueError):continue
    relative=str(file.relative_to(ROOT)).replace('\\','/')
    error_path=Path(str(file)+'.error.txt')
    if not numeric:
        trials.append({'file':relative,'observations':0,'max_reference_progress':0.,
            'partial_closed_loop_observed':False,'game_finish_verified':False,
            'runtime_error':error_path.read_text().strip() if error_path.exists() else 'No valid observations retained'})
        continue
    start=numeric[0]
    motion=max(math.dist([r['x'],r['y'],r['z']],[start['x'],start['y'],start['z']]) for r in numeric)
    progress=max(r['nearest_sample'] for r in numeric)/(waypoints-1)
    controls=any(abs(r['command_steer'])>.1 and r['gas']>.5 for r in numeric)
    trials.append({'file':relative,'observations':len(numeric),
        'wall_seconds':numeric[-1]['wall_s'],'max_displacement_m':motion,'max_reference_progress':progress,
        'max_reference_error_m':max(r['reference_error_m'] for r in numeric),
        'partial_closed_loop_observed':len(numeric)>=100 and motion>10 and controls,
        'game_finish_verified':any(e['trial']==relative for e in finishes),
        'runtime_error':error_path.read_text().strip() if error_path.exists() else None})
report={'schema':'tm2020_retained_local_driving_trials_v2','reference_waypoints':waypoints,
    'partial_closed_loop_observed':any(t['partial_closed_loop_observed'] for t in trials),
    'best_reference_progress':max((t['max_reference_progress'] for t in trials),default=0.),
    'game_finish_verified':bool(finishes),'independent_finish_evidence':finishes,'native_finish_counter_recovered':False,'all_retained_trials':trials,
    'warning':'Best progress is not a completion rate. This records historical local experiments, not a reproducible performance guarantee.'}
destination=ROOT/'local/recon/live-driving-qualification.json'
destination.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('LIVE_TRIAL_EVIDENCE trials',len(trials),'best_progress',report['best_reference_progress'],
      'partial_closed_loop',report['partial_closed_loop_observed'],'finish_verified',bool(finishes))
