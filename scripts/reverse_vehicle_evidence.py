"""Pin curve/suspension/force arithmetic and distinguish unresolved tire stages."""
import hashlib
import json
from pathlib import Path
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA,evidence


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown vehicle executable')
    code=PeCode(exe);records=[]
    names={0x42bcb0:'curve evaluator',0x42bba0:'Hermite curve helper',0x844090:'conditional mode-2 suspension through force application',
        0x7bda90:'local force and application point transform',0x7bd310:'world force/torque accumulation and wake tail',
        0x7b9b70:'wake queue gate, qualified with queue disabled',0x84da80:'complete auxiliary vehicle force arithmetic',
        0x7bdd20:'local force rotation and center-force accumulation',0x7bd4f0:'center force manager indexing and wake tail',
        0x844130:'complete wheel phase, angle and suspension state/pose update',0x843190:'complete wheel spin update',
        0x84f1a0:'complete quaternion/velocity direction factor update',0x8456b0:'complete vertical-velocity response factors',
        0x845b60:'complete four-wheel material aggregation including curve helper',
        0x845880:'complete four-curve material response aggregation',0x83af90:'material blend scalar and integer averaging',
        0x18f6954:'finite bounded integer rounding helper',0x18f76e4:'round-half-away finite helper',
        0x846010:'complete vehicle resistance, timed braking and airborne angular damping',
        0x7bdf40:'complete local torque rotation and angular accumulation',
        0x195cb14:'original finite float remainder helper',
        0x851f00:'observed vehicle variant 5, unported',0x84f720:'variant steering/drive force helper, unported',
        0x850e50:'vehicle force helper, unported',0x84de60:'vehicle special-state helper, unported',
        0x4df590:'collision/material initialization; only material store slice qualified',
        0x7bf0d0:'surface friction/restitution response arithmetic',0x7d7cb0:'runtime class ID getter, initialized path qualified'}
    for root,label in names.items():
        ins=code.instructions(root)
        if not ins:raise ValueError(f'Empty vehicle procedure {root:#x}')
        records.append({'root':hex(root),'label':label,'ranges':[[hex(r.begin),hex(r.end)] for r in code.index.groups[root]],
            'instructions':len(ins),'calls':[evidence(i) for i in ins if i.mnemonic in {'call','jmp'} and i.op_str.startswith('0x')]})
        (ROOT/f'local/recon/physics/{root:08x}-qualified.asm').write_text('\n'.join(f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in ins)+'\n')
    leaves=[]
    for begin,end,label in [(0x845100,0x845108,'vehicle item-ID adapter'),(0x7be690,0x7be6a6,'manager rigid-state lookup'),
        (0x4eff20,0x4eff4a,'surface restitution combiner'),(0x7bd4b0,0x7bd4ea,'linear force accumulator'),
        (0x845210,0x845218,'center force item adapter'),(0x83db50,0x83db72,'raw status lower two bits equal one'),
        (0x83db80,0x83dba2,'raw status lower two bits equal two'),(0x83dbf0,0x83dc0b,'raw status bit four'),
        (0x186d10,0x186d31,'identity rotation store, translation untouched'),
        (0x18ce30,0x18cf62,'binary32 fast sine/cosine polynomial and range reduction'),
        (0x845840,0x84587a,'wheel material kind classifier'),
        (0x190c9d8,0x190caad,'finite rounding bit manipulation'),
        (0x190cab0,0x190caf9,'float category classifier'),
        (0x42bf60,0x42bfda,'step-only curve evaluator, independent of curve flags'),
        (0x845260,0x845268,'local torque item adapter'),
        (0x843150,0x84317b,'four-wheel integer contact query from status base')]:
        raw=code.pe.get_data(begin,end-begin);ins=list(code.cs.disasm(raw,begin))
        if sum(i.size for i in ins)!=len(raw):raise ValueError('Incomplete reviewed leaf decode')
        leaves.append({'begin':hex(begin),'end':hex(end),'label':label,'instructions':[evidence(i) for i in ins]})
    source=['native/include/tm2020/recovered_vehicle.hpp','native/src/recovered_vehicle.cpp',
        'native/include/tm2020/recovered_material.hpp','native/src/recovered_material.cpp','native/src/recovered_vehicle_auxiliary.cpp',
        'native/include/tm2020/recovered_wheel.hpp','native/src/recovered_wheel.cpp',
        'native/include/tm2020/recovered_wheel_material.hpp','native/src/recovered_wheel_material.cpp',
        'native/include/tm2020/recovered_resistance.hpp','native/src/recovered_resistance.cpp']
    report={'schema':'tm2020_vehicle_arithmetic_evidence_v1','sha256':SHA,'procedures':records,'reviewedLeaves':leaves,
        'curve':{'flags':0,'pointPointer':8,'pointCount':0x10,'pointStride':8,'x':0,'y':4,
            'boundaryTolerance':1e-5,'flagsPrecedence':['1 step','2 smoothstep','0x10 Hermite','otherwise linear'],
            'zeroFinalHermiteTangentFlag':'0x20','emptyCurveValue':0,'actualRaceCurvesExtracted':False},
        'suspension':{'vehicleConfig':0x88,'vehicleRequireAllWheelContacts':0x171c,'wheelArray':0x1780,'wheelStride':0xb8,
            'wheelContactWord':0x34,'configMode':0x238,'configStiffness':0x23c,'configDamping':0x240,'configRestLength':0x244,
            'localVerticalForce':'(restLength-length)*stiffness - speed*damping',
            'localPoint':'selected wheel model +0x10','forceTorqueApplicationQualified':True,'modesZeroAndOneRecovered':False},
        'manager':{'modelsPointer':0x10,'rigidStatesPointer':0x70,'forceTorquePointer':0xa0,'itemToBodyIndexPointer':0xb0,'wakeQueuePointer':0x100,
            'rigidStateStride':0x58,'forceTorqueStride':0x18,'modelLocalCenterOfMass':0x40,'wakeQueueQualified':False},
        'forceTorque':{'worldForce':'rotation * localForce','worldPoint':'rotation * localPoint + translation',
            'worldCenterOfMass':'rotation * modelCenter + translation','angularIncrement':'(worldPoint-worldCenterOfMass) cross worldForce'},
        'surfaceMaterials':{'defaultTableRva':'0x1fa9a70','entries':80,'stride':8,'impactFriction':0,'restitution':4,
            'initializerSlice':['0x4df599','0x4dfbb8'],'effectiveRaceParametersVerified':False,
            'materialIdSelection':'low byte of each 16-bit surface ID','responseDynamicClassId':'runtime generated, supplied explicitly',
            'frictionSelectionIsContextDependent':True,'isCompleteTireModel':False},
        'auxiliaryVehicleForce':{'entry':'0x84da80','localVelocityContext':0x28,'localForwardVelocityGate':'z > 6',
            'magnitudeGate':'input >= 1e-5','vehicleScalars':[0x98,0x9c],'scalarActivationThreshold':.1,
            'rawStatusWords':[0x176c,0x1370],'configCoefficients':[0x1efc,0x1f00,0x1f04,0x1f08],
            'wheelForceGateWord':0x70,'gateWordIsContact34':False,'frontWheelIndices':[0,1],'rearWheelIndices':[2,3],
            'wakeQueueDisabled':True,'completeTireSlipModel':False},
        'wheelKinematics':{'entry':'0x844130','phasePeriodBits':'0x44c90fdb','phasePeriodIsTwoPi':False,
            'stateOffsets':{'length':0,'speed':4,'pendingCompression':8,'spinRate':0x1c,'contactWord':0x34,'materialByte':0x40,
                'normal':0x44,'phase':0x78,'angle':0x7c,'targetAngle':0x80},
            'globalAngleCurveOffset':0x19f8,'globalCurveCountAndGateOffset':0x1a08,'materialParametersSelectorOffset':0x1a48,
            'material14RemapGlobal':'0x1faa04c','materialCurveOffset':0xd8,'materialRateOffset':0x4c,
            'suspensionMode2And3ArithmeticQualified':True,'otherModesPreservePose':True,
            'renderCacheCopiesQualifiedAsOracleMetadata':True,'sdkOwnsRenderCache':False},
        'wheelSpin':{'entry':'0x843190','targetWheelField':0x1c,'specialMaterialIds':[74,3,21],
            'airborneIdleDecayBits':'0x3f7eb852','contactIdleRelaxationBits':'0x3f733333','blendDenominatorBaseBits':'0x3f800054',
            'futureTickOffset':0x13a0,'futureTickSentinel':'0xffffffff','unsignedTimerComparisons':True,
            'configurationOffsets':[0xd90,0xd94,0xd98,0x1ef4],'wheelRadiusModelOffset':8},
        'wheelMaterialBlend':{'entry':'0x845b60','curveAggregationEntry':'0x845880','nativeOutputStride':60,
            'floatOffsets':[0,4,8,12,16,20,24,28,32,36,44,48,52],'integerOffset':40,'flagsOffset':56,
            'sourceMaterialFloats':'0x18..0x3c, 0x44..0x4c','sourceMaterialInteger':'0x40','sourceMaterialFlags':'0x50',
            'positiveOnlyOptionalFields':['0x34','0x38'],'optionalOutputSentinel':-1,
            'integerRounding':'nearest, halfway away from zero; output zero unless at least three contacting materials have nonzero source word',
            'normalDegenerateFallback':[0,1,0],'classificationLastContactWins':True,'classificationUsesUnremappedId':True,
            'curveOffsetsInOutputOrder':['0x128','0x88','0x178','0x1c8'],'noContactCurveResponse':[1,1,1,0],
            'speedBlend':{'outputOffset':4,'floor':1.5,'startKmh':90,'endKmh':120},'effectiveRaceMaterialRecordsCaptured':False},
        'fastSinCos':{'entry':'0x18ce30','maximumAbsoluteArgument':1000000,'floatRangeReductionAndPolynomial':True,
            'sameImplementationAsPositionCorrectionTrig':False,'isLibmAccurateTrigClaim':False},
        'directionFactor':{'entry':'0x84f1a0','outputOffset':'0x14bc','quaternion':'0x12e0','velocity':'0x12fc',
            'scalar':'0x98','recoveryDurationUint':'0x324','minimum':'0x328'},
        'verticalResponse':{'entry':'0x8456b0','configOffsets':['0x19e4','0x19e8','0x19ec','0x19f0'],
            'input':'abs(vY/length(v))','interiorResponse':'1-fastCos(((ratio-begin)/(end-begin))*pi*0.5)'},
        'vehicleResistance':{'entry':'0x846010','localTorqueEntry':'0x7bdf40','wakeQueueDisabled':True,
            'rawStatusWords':['0x176c','0x1370'],'rawStatusBase':'0x1280','statusWordsAreNotBaseWord':True,
            'variantConfig':'0x1790','variantSelectionHasUnsignedEarlyGateAndSignedBrakingBranch':True,
            'earlyGateVehicleWord':'0x138c','brakingWord':'0x1408','mutableTimer':'0x1410','unsignedTickComparisons':True,
            'durationConfig':'0x1bdc','resistanceCoefficients':['0x17a8','0x17ac'],
            'curveOffsets':['0x9f8','0x17b8','0x2060'],'belowVariant4BrakingCurveIgnoresFlags':True,
            'airTorqueVelocity':'0x1308','airTorqueQuaternionConjugateThenMatrixRotation':True,'fullTireForceGenerator':False},
        'sourceHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source},
        'completeTireSlipModelRecovered':False,'completeVehicleForcesRecovered':False,'completePhysics':False}
    (ROOT/'local/recon/vehicle-arithmetic-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS VEHICLE_ARITHMETIC_EVIDENCE curve=true mode2_force_torque=true full_tire_model=false')


if __name__=='__main__':main()
