"""Cross-check sparse source capture, offline replay and complete native calls."""
import argparse
import hashlib
import json
from pathlib import Path

from reverse_physics import SHA
from force_worker_fixture import load_fixture, require


def audit(args):
    import pefile
    require(hashlib.sha256(args.exe.read_bytes()).hexdigest() == SHA, 'Unknown executable')
    pe = pefile.PE(str(args.exe), fast_load=True)
    capture = json.loads(args.capture.read_text())
    offline = json.loads(args.offline.read_text())
    require(capture['sha256'] == offline['sha256'] == SHA, 'Mixed builds')
    require(capture['readOnlyProcessHandle'] and capture['sourceBindingRecheckedAfterCapture'] and not capture['gameMemoryWritten'] and
            not capture['codeExecutedInGame'] and not capture['rawHeapPagesPersisted'] and
            not capture['sourceCodeBytesPersisted'], 'Invalid capture provenance')
    require(not capture['atomicSnapshot'] and not capture['playerOwnershipVerified'] and
            not capture['internalTickVerified'] and not capture['completePhysics'],
            'Capture overstates authority or scope')
    require(len(capture['trials']) == len(offline['fixtures']) >= 2, 'Missing trials')
    results = []
    emulated_by_name = {r['fixture']: r for r in offline['fixtures']}
    require(len(emulated_by_name) == len(offline['fixtures']), 'Duplicate offline input')
    for trial in capture['trials']:
        name = trial['trial']
        emulated = emulated_by_name[name+'.tmforce']
        f = load_fixture(args.fixtures/(name+'.tmforce'), pe)
        native = json.loads((args.native/(name+'.json')).read_text())
        require(trial['completed'] and trial['completeWorkerBoundarySelected'] and
                not trial['completeEnclosingCallbackQualified'] and not trial['faultReasons'],
                'Incomplete captured worker')
        require(f.sha256 == trial['sparseFixtureSha256'] == emulated['fixtureSha256'] ==
                native['fixtureSha256'] and native['sha256'] == SHA, 'Mixed/stale input fixture')
        require(emulated['allAccessesInsideCapturedByteMasks'], 'Replay accessed uncaptured bytes')
        for report in (emulated, native):
            require(report['allDataPagesBitExact'] and report['completeWorkerReturned'] and
                    not report['gameProcessAccessed'] and not report['functionsSkipped'] and
                    not report['originalCodeModified'], 'Worker differential failed')
            require(report['dataPages'] == len(f.data_pages) and
                    report['codePages'] == len(f.code_pages) and
                    report['retainedDataBytes'] == sum(sum(p.mask) for p in f.data_pages),
                    'Page/mask inventory differs')
        require(native['entryRva'] == '0x851f00' and native['originalExecutableRequired'] and
                not native['runtimePythonRequired'] and not native['wholeGameStepQualified'] and
                native['repetitions'] >= 10000 and native['independentInputCases'] == 1,
                'Native report scope/repetition count invalid')
        results.append(dict(name=name, sha256=f.sha256, dataPages=len(f.data_pages),
                            retainedDataBytes=native['retainedDataBytes'],
                            nativeRepetitions=native['repetitions'],
                            callsPerSecondIncludingRestoreAndComparison=
                            native['callsPerSecondIncludingRestoreAndComparison']))
    report = dict(schema='tm2020_complete_force_worker_qualification_v1', sha256=SHA,
                  entryRva='0x851f00', independentFrozenInputs=len(results), fixtures=results,
                  completeForceWorkerOfflineQualifiedForRetainedInputs=True,
                  completeForceWorkerNativeQualifiedForRetainedInputs=True,
                  originalExecutableRequired=True, runtimeGameRequired=False,
                  newPortablePhysicsOperations=0, completeEnclosingCallbackQualified=False,
                  completeVehicleStepQualified=False, fullHeadlessSimulatorReady=False)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print('PASS COMPLETE ORIGINAL FORCE WORKER:', len(results),
          'frozen inputs; complete data pages exact; no game access during replay')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('exe', 'capture', 'offline', 'fixtures', 'native', 'report'):
        p.add_argument('--'+name, type=Path, required=True)
    audit(p.parse_args())
