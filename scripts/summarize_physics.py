"""Audit retained layout/causal measurements; never promote a numeric hit to owner.

Uses three independent lines: SHA-bound layout search, repeated input response,
and static accessor relationships. Wall time is not an engine physics tick.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import struct
from reverse_physics import SHA
ROOT=Path(__file__).resolve().parents[1]


def analyze(prefix):
    metadata=prefix.with_suffix('.candidates.txt').read_text().splitlines()
    if len(metadata)<3 or metadata[1]!=SHA:raise ValueError('Probe identity/hash absent')
    rows=list(csv.DictReader(prefix.with_suffix('.csv').open(newline='')))
    groups={}
    for r in rows:groups.setdefault(r['state_address'],[]).append(r)
    measurements=[]
    for address,values in groups.items():
        valid=[r for r in values if r['valid']=='1']
        def point(r):return [float(r[k]) for k in ('x','y','z')]
        distance=math.dist(point(valid[0]),point(valid[-1])) if valid else 0
        maximum_speed=max((math.sqrt(sum(float(r[k])**2 for k in ('vx','vy','vz'))) for r in valid),default=0)
        before=[r for r in valid if float(r['wall_s'])<.45]
        throttle=[r for r in valid if r['command_gas']=='1']
        responses=bool(before and throttle and maximum_speed>5 and distance>5 and len(valid)>=.95*len(values))
        errors=[]
        for a,b in zip(valid,valid[1:]):
            dt=float(b['wall_s'])-float(a['wall_s'])
            if not .005<=dt<=.025:continue
            displacement=[float(b[k])-float(a[k]) for k in ('x','y','z')]
            velocity=[.5*(float(a[k])+float(b[k]))*dt for k in ('vx','vy','vz')]
            errors.append(math.dist(displacement,velocity))
        measurements.append({'address':address,'samples':len(values),'coherentSamples':len(valid),
            'displacementMeters':distance,'maximumSpeedMetersPerSecond':maximum_speed,
            'respondedToInputInThisTrial':responses,'medianWallTimeVelocityConsistencyMeters':statistics.median(errors) if errors else None})
    model=prefix.with_suffix('.manager-sample.json')
    relationship=None
    if model.exists():
        relationship=json.loads(model.read_text());
        if relationship['pid']!=int(metadata[0]):raise ValueError('Probe PID mismatch')
        state=int(relationship['states'],16)+relationship['id_zero_state_index']*0x58
        if f'{state:x}' not in {x.removeprefix('0x').lower() for x in metadata[2:]}:
            raise ValueError('Manager sample does not identify a measured state')
        floats={o:struct.unpack('<f',struct.pack('<I',b))[0] for o,b in relationship['model_binary32_by_offset'].items() if int(o)>=24}
        relationship['modelFloatsByDecimalOffset']=floats
    return {'prefix':str(prefix.relative_to(ROOT)).replace('\\','/'),'pid':int(metadata[0]),'sha256':SHA,
        'measurements':measurements,'managerSample':relationship,
        'traceSha256':hashlib.sha256(prefix.with_suffix('.csv').read_bytes()).hexdigest(),
        'authoritativePlayerRootVerified':False,'internalTickVerified':False}


def main():
    trials=[]
    for manifest in sorted((ROOT/'local/recon').glob('rigid-*.candidates.txt')):
        prefix=Path(str(manifest).removesuffix('.candidates.txt'))
        if prefix.with_suffix('.csv').exists():trials.append(analyze(prefix))
    repeated={}
    for t in trials:
        for m in t['measurements']:
            if m['respondedToInputInThisTrial']:repeated.setdefault((t['pid'],m['address']),[]).append(t['prefix'])
    report={'schema':'tm2020_recovered_physics_qualification_v1','sha256':SHA,'trials':trials,
        'repeatedInputResponsiveStates':[{'pid':p,'address':a,'trials':ts} for (p,a),ts in repeated.items() if len(ts)>=2],
        'probeProcessWriteAccess':False,'stablePlayerRootVerified':False,'internalPhysicsTickVerified':False,
        'completeVehiclePhysicsPorted':False,'fullHeadlessSimulatorReady':False,
        'observedForceSelectors':sorted({t['managerSample']['force_variant_selector'] for t in trials if t['managerSample'] and t['managerSample'].get('vehicle_data_relationship_verified',False)}),
        'bootstrapCaveat':'PID 7620 numeric V3 bootstrap found map-anchored positions but failed old quaternion consensus (20/30 valid). Typed rigid probe independently checks the recovered matrix and scalar-first quaternion; identity manifest is only used for PID/creation/SHA.',
        'limits':['One local Solo session on Fall 2026 - 01','Wall-time reads may tear or repeat engine states','No respawn/relaunch-stable root or contact/force-state capture','Model gravity coefficient +0x18 is not labelled mass without additional evidence']}
    destination=ROOT/'local/recon/physics-live-qualification.json';destination.write_text(json.dumps(report,indent=2)+'\n')
    print('PHYSICS_LIVE_AUDIT trials',len(trials),'repeatedResponsiveStates',len(report['repeatedInputResponsiveStates']),'full_simulator=false')


if __name__=='__main__':main()
