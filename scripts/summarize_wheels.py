"""Typed wheel records and stored spring branch parameters; no tick/owner claim."""
import csv
import json
from pathlib import Path
import struct
from reverse_physics import ROOT,SHA


def f32(word):return struct.unpack('<f',struct.pack('<I',int(word)))[0]


def main():
    trials=[]
    for path in sorted((ROOT/'local/recon').glob('rigid-*.wheels.csv')):
        prefix=Path(str(path).removesuffix('.wheels.csv'));sample=json.loads(prefix.with_suffix('.manager-sample.json').read_text())
        if not sample.get('vehicle_data_relationship_verified'):raise ValueError('Wheel sample lacks checked item relationship')
        identity=prefix.with_suffix('.candidates.txt').read_text().splitlines()
        if identity[1]!=SHA or int(identity[0])!=sample['pid']:raise ValueError('Wheel identity mismatch')
        rows=list(csv.DictReader(path.open(newline='')));wheels=[]
        for k in range(4):
            all_rows=[r for r in rows if int(r['wheel'])==k];valid=[r for r in all_rows if r['valid']=='1']
            if not valid:raise ValueError('No valid typed wheel samples')
            wheels.append({'wheel':k,'samples':len(all_rows),'valid':len(valid),
                'lengthRange':[min(f32(r['bits_0']) for r in valid),max(f32(r['bits_0']) for r in valid)],
                'speedRange':[min(f32(r['bits_4']) for r in valid),max(f32(r['bits_4']) for r in valid)],
                'contactWords':sorted({int(r['bits_34']) for r in valid}),
                'materialBytes':sorted({int(r['bits_40'])&255 for r in valid})})
        p=sample['suspension_branch']
        trials.append({'prefix':str(prefix.relative_to(ROOT)).replace('\\','/'),'pid':sample['pid'],'wheels':wheels,
            'storedSpringBranchParameters':{'mode':p['mode'],'requireAllContactsWord':p['require_all_contacts_word'],
                'stiffness':f32(p['stiffness_bits']),'damping':f32(p['damping_bits']),'restLength':f32(p['rest_length_bits'])},
            'forceBranchExecutionVerified':False,'unitsVerified':False,'internalTickVerified':False})
    failures=[]
    for path in sorted((ROOT/'local/recon').glob('rigid-*.failure.txt')):failures.append({'artifact':str(path.relative_to(ROOT)),'reason':path.read_text(encoding='utf-8-sig').strip()})
    report={'schema':'tm2020_wheel_observation_v1','sha256':SHA,'trials':trials,'failedTrials':failures,
        'wheelStride':0xb8,'vehicleWheelOffset':0x1780,'fullTireModelRecovered':False,'completePhysics':False,
        'limits':['Read-only asynchronous samples','Stored mode/parameters do not prove execution of a conditional branch','No wheel naming/order or SI units inferred','No throttle wheel trial: foreground guard rejected it before input']}
    (ROOT/'local/recon/wheel-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS WHEEL_AUDIT passive_trials',len(trials),'retained_failures',len(failures),'tire_model_complete=false')


if __name__=='__main__':main()
