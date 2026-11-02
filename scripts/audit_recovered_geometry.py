"""Fail closed on missing/mismatched geometry and vehicle qualification evidence."""
import csv
import hashlib
import json
from pathlib import Path
from reverse_physics import ROOT,SHA


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def main():
    specs=[('cooking-oracle/recovered-cooking-oracle.json',1,'cases','bitExact'),
        ('bounds-oracle/recovered-bounds-oracle.json',1,'cases','bitExact'),
        ('recovered-tree-builder-oracle.json',1,'cases','bit_exact'),
        ('recovered-mesh-oracle.json',2,'cases_per_operation','bit_exact'),
        ('recovered-convex-oracle.json',2,'cases_per_operation','bit_exact_defined_outputs'),
        ('recovered-polygon-oracle.json',3,'cases_per_operation','bit_exact'),
        ('recovered-vehicle-kernel-oracle.json',3,'cases_per_operation','bit_exact'),
        ('material-oracle/recovered-material-oracle.json',2,'cases','bitExact'),
        ('recovered-features-oracle.json',5,'cases_per_operation','bit_exact'),
        ('convex-collision-oracle/recovered-convex-collision-oracle.json',1,'cases','bitExactDefinedOutputs'),
        ('convex-mesh-oracle/recovered-convex-mesh-oracle.json',1,'cases','bitExactDefinedOutputs'),
        ('solver-oracle/recovered-solver-oracle.json',1,'cases','bitExact'),
        ('recovered-joints-oracle.json',3,'cases_per_operation','bit_exact'),
        ('joint-solver-oracle/recovered-solver-oracle.json',1,'cases','bitExact'),
        ('recovered-vehicle-auxiliary-oracle.json',2,'cases_per_operation','bit_exact'),
        ('patch-oracle/recovered-patch-oracle.json',1,'cases','bitExactDefinedOutputs'),
        ('recovered-wheel-update-oracle.json',1,'cases_per_operation','bit_exact'),
        ('recovered-wheel-spin-oracle.json',1,'cases_per_operation','bit_exact'),
        ('recovered-joint-position-oracle.json',4,'cases_per_operation','bit_exact'),
        ('position-island-oracle/recovered-position-island-oracle.json',1,'cases','bitExact'),
        ('recovered-frame-oracle.json',1,'cases_per_operation','bit_exact'),
        ('recovered-wheel-material-oracle.json',4,'cases_per_operation','bit_exact'),
        ('recovered-resistance-oracle.json',2,'cases_per_operation','bit_exact'),
        ('recovered-step-parameter-oracle.json',2,'cases_per_operation','bit_exact'),
        ('recovered-activation-oracle.json',2,'cases_per_operation','bit_exact'),
        ('recovered-steering-surface-oracle.json',4,'cases_per_operation','bit_exact')]
    proofs=[]
    for name,operations,count,exact in specs:
        path=ROOT/'local/recon'/name;data=json.loads(path.read_text())
        if data['sha256']!=SHA or data[count]!=20000 or data[exact] is not True:raise ValueError('Invalid original differential: '+name)
        if data.get('operations',operations)!=operations:raise ValueError('Operation count differs: '+name)
        if data.get('gameProcessAccessed',data.get('game_process_accessed',False)) is not False:raise ValueError('Unexpected live access')
        if data.get('originalCodeModified',data.get('original_code_modified',False)) or data.get('functionsSkipped',False):raise ValueError('Modified original code')
        proofs.append({'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':digest(path),'operations':operations,'casesEach':20000})
    for name in ['mesh-convex-evidence.json','vehicle-arithmetic-evidence.json','constraint-evidence.json',
        'step-parameter-evidence.json','activation-evidence.json','steering-surface-evidence.json']:
        data=json.loads((ROOT/'local/recon'/name).read_text())
        if data['sha256']!=SHA:raise ValueError('Executable evidence mismatch')
        for path,expected in data['sourceHashes'].items():
            if digest(ROOT/path)!=expected:raise ValueError('Stale source evidence: '+path)
    manifest=json.loads((ROOT/'local/recon/ghidra/manifest.json').read_text())
    with (ROOT/'local/recon/ghidra/decompiled/decompile-report.tsv').open(newline='') as f:rows=list(csv.DictReader(f,delimiter='\t'))
    if manifest['sha256']!=SHA or len(rows)!=manifest['functions'] or not all(r['completed']=='true' for r in rows):raise ValueError('Incomplete Ghidra research export')
    for row in rows:
        path=ROOT/f"local/recon/ghidra/decompiled/{int(row['rva'],16):08x}.c"
        if SHA not in path.read_text()[:250]:raise ValueError('Unpinned decompilation evidence')
    sources=list((ROOT/'native/include/tm2020').glob('recovered_*.hpp'))+list((ROOT/'native/src').glob('recovered_*.cpp'))
    report={'schema':'tm2020_geometry_vehicle_qualification_v1','sha256':SHA,'newPublicOperations':sum(p['operations'] for p in proofs),
        'totalPublicOperationsWithPrior20':20+sum(p['operations'] for p in proofs),'proofs':proofs,
        'currentSourceHashes':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in sources},
        'sdkStaticLibrarySha256':digest(ROOT/'native/build/libtm2020_sdk.a'),
        'ghidraCompletedResearchFunctions':len(rows),'ghidraOutputIsVerifiedPhysicsPort':False,
        'retainedUndefinedPolygonBranchQualified':False,'convexManifoldsPortedWithinDefinedDomain':True,
        'contactIslandScheduleQualifiedWithJointSpansEmpty':True,'jointVelocityIslandScheduleQualifiedWithExternalCallbacksEmpty':True,
        'preparedGeneralJointPositionPassesQualified':True,'generalJointPreparationQualified':False,
        'positionIslandOrderQualifiedWithinScalarTrigDomain':True,'modelCenterFrameShiftQualified':True,
        'completeTireSlipModelPorted':False,'fullSimulatorReady':False}
    scene=json.loads((ROOT/'local/recon/rigid-mesh-demo.json').read_text())
    if scene['ticks']<1000 or not scene['snapshotReplayBitExact'] or scene['gameRequired'] or not scene['syntheticGeometryAndTuning'] or scene['completeVehiclePhysics']:raise ValueError('Autonomous rigid scene qualification mismatch')
    report['autonomousRigidMeshCompositionValidated']=True
    report['completeGameStepInstructionOracleQualified']=False
    fma=json.loads((ROOT/'local/recon/recovered-position-fma-oracle.json').read_text())
    if fma['sha256']!=SHA or fma['cases_per_sign_and_sweep']!=20000 or not fma['bit_exact'] or fma['math_dispatch_flag']!=1 or not fma['loader_owned_profiler_tls_null_branch'] or fma['functionsSkipped'] or fma['originalCodeModified']:raise ValueError('Invalid native FMA differential')
    capture=json.loads((ROOT/'local/recon/effective-materials-qualification.json').read_text())
    if capture['sha256']!=SHA or capture['materials']!=80 or capture['capturedCurves']!=412 or capture['mathDispatchObserved']!=1 or capture['authoritativeOwnerVerified']:raise ValueError('Invalid retained parameter audit')
    if capture['sourceProbeSha256']!=digest(ROOT/'native/src/vehicle_parameter_probe.cpp'):raise ValueError('Stale capture probe evidence')
    material=json.loads((ROOT/'local/recon/recovered-wheel-material-oracle.json').read_text())
    if material['captured_material_cases']!=10000 or material['integer_material_coefficient_maximum_qualified']!=1000000:raise ValueError('Real material coefficient/curve coverage missing')
    report['boundedFmaPositionSweepsQualified']=True
    report['retainedEffectiveMaterials']=80;report['retainedEffectiveCurves']=412
    report['capturedMaterialDifferentialCases']=10000
    report['originalCompleteFmaPositionIslandLoopQualified']=False
    if report['newPublicOperations']!=52:raise ValueError('Operation inventory changed')
    (ROOT/'local/recon/geometry-vehicle-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS GEOMETRY_VEHICLE_AUDIT operations_beyond_prior20=52 total_operations=72 cases_each=20000 autonomous_rigid_mesh=true full_vehicle_simulator=false')


if __name__=='__main__':main()
