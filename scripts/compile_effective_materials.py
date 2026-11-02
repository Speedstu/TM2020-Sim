"""Validate a retained typed capture and serialize numeric oracle inputs only."""
import hashlib
import json
import math
from pathlib import Path
import struct
from reverse_physics import ROOT,SHA


def main():
    source=ROOT/'local/recon/effective-vehicle-26616-v7.json'
    capture=json.loads(source.read_text())
    if capture['sha256']!=SHA or not capture['readOnly'] or not capture['bindingStableDuringCapture']:raise ValueError('Unpinned or unstable capture')
    if capture['authoritativeOwnerVerified'] or capture['internalTickVerified']:raise ValueError('Unexpected unsupported owner/tick claim')
    if not all(capture.get(k) is True for k in ('forceCallbackContextVerified','forceContextDynaBacklinkVerified','forceContextVehicleMembershipVerified')) or capture.get('forceCallbackRva')!='0x8427d0':raise ValueError('Force callback context binding unqualified')
    materials=capture['materials']
    if len(materials)!=80 or [m['id'] for m in materials]!=list(range(80)):raise ValueError('Wrong material inventory')
    def value(bits):
        if type(bits) is not int or not 0<=bits<=0xffffffff:raise ValueError('Invalid binary32 word')
        x=struct.unpack('<f',struct.pack('<I',bits))[0]
        if not math.isfinite(x) or abs(x)>1e6:raise ValueError('Nonfinite/out-of-domain parameter')
        return x
    payload=bytearray(struct.pack('<II',0x4d50544d,80))
    for m in materials:
        words=m['words']
        for offset in range(0x18,0x54,4):
            bits=words[str(offset)]
            if offset not in (0x40,0x50):value(bits)
            elif offset==0x40 and bits>1000000:raise ValueError('Material integer exceeds qualified domain')
            payload+=struct.pack('<I',bits)
        for offset in (0x128,0x88,0x178,0x1c8):
            curve=m['curves'][str(offset)]
            if curve['count']!=len(curve['points']) or not 0<=curve['count']<=4096:raise ValueError('Curve extent differs')
            payload+=struct.pack('<II',curve['flags'],curve['count']);last=-math.inf
            for x,y in curve['points']:
                current=value(x);value(y)
                if current<=last:raise ValueError('Curve points do not increase')
                last=current;payload+=struct.pack('<II',x,y)
    output=ROOT/'local/recon/effective-materials-26616.bin';output.write_bytes(payload)
    floats=lambda table,offsets:[value(table[str(k)]) for k in offsets]
    report={'schema':'tm2020_effective_material_capture_audit_v1','sha256':SHA,
        'captureSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'fixtureSha256':hashlib.sha256(payload).hexdigest(),
        'sourceProbeSha256':hashlib.sha256((ROOT/'native/src/vehicle_parameter_probe.cpp').read_bytes()).hexdigest(),
        'materials':80,'capturedCurves':sum(len(m['curves']) for m in materials)+len(capture['configurationCurves']),
        'materialIntegerMinimum':min(m['words']['64'] for m in materials),'materialIntegerMaximum':max(m['words']['64'] for m in materials),
        'mathDispatchObserved':capture['scalarMathDispatchFlag'],'modelCenter':floats(capture['modelWords'],(64,68,72)),
        'suspensionStiffnessDampingRestLength':floats(capture['configurationWords'],(0x23c,0x240,0x244)),
        'persistentGravity':floats(capture['persistentGravityWords'],(0,4,8)),
        'activationSnapshotAtomic':capture['bodyActivationSnapshot']['atomicPhysicsStageSnapshot'],
        'positionConfiguration':floats(capture['positionConfigurationWords'],(0,4,8)),
        'materialRecordsRecoveredFromLiveLinkedVehicle':True,'forceCallbackContextVerified':True,
        'forceContextVehicleCount':capture['forceContextVehicleCount'],'authoritativeOwnerVerified':False,'internalTickVerified':False,
        'completeRaceTrajectoryQualified':False,'originalGameAccessRequiredToReauditRetainedCapture':False}
    (ROOT/'local/recon/effective-materials-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS EFFECTIVE_MATERIAL_CAPTURE materials=80 curves='+str(report['capturedCurves'])+' integer_max='+str(report['materialIntegerMaximum'])+' observed_math_flag='+str(report['mathDispatchObserved'])+' owner_unqualified=true')


if __name__=='__main__':main()
