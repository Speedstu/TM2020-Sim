"""Build and qualify continuous original-server stepping and optional native PPO.

Uses the private transfer's local server/Packs and pinned TAS checkout. No game
installation, account, Openplanet, Python ML library or online session needed.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from official_engine import sha

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT/'cache/TrackmaniaServer-official-2026-05-15'
FIXTURES = ROOT/'cache/trackmania-tas-upstream-036a65b/tools/testdata'
REVISION = '036a65ba6aaef87b4579b8ee5a770729341dc572'


def main(a):
    if platform.system() != 'Linux' or platform.machine().lower() not in ('x86_64', 'amd64'):
        raise ValueError('The official original-engine adapter requires Linux x86-64 (native or WSL)')
    a.output = a.output.resolve()
    a.output.mkdir(parents=True, exist_ok=False)
    logs = a.output/'logs'
    logs.mkdir()
    def run(name, command, timeout=180):
        print('RUN', name, flush=True)
        # Preserve failures and never turn a failed measurement into a number.
        with (logs/(name+'.log')).open('x') as log:
            subprocess.run(list(map(str, command)), cwd=ROOT, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=timeout)
    compat = ROOT/'cache/trackmania-tas-compat-0.35'
    revision = subprocess.check_output(['git', '-C', str(compat), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('Unexpected TAS codec revision; restore the pinned checkout')
    (a.server/'TrackmaniaServer').chmod((a.server/'TrackmaniaServer').stat().st_mode | 0o111)
    build = ROOT/'native/build-linux'
    run('cmake-configure', ['cmake', '-S', ROOT/'native', '-B', build, '-DCMAKE_BUILD_TYPE=Release'])
    run('cmake-build', ['cmake', '--build', build, '-j', str(min(os.cpu_count() or 1, 8))], 600)
    run('ctest', ['ctest', '--test-dir', build, '--output-on-failure', '-j', '4'])
    run('tape-build', ['cargo', 'build', '--manifest-path', ROOT/'integrations/official-step/Cargo.toml',
        '--release', '--locked', '--offline', '--target-dir', ROOT/'cache/official-step-rust-target'], 600)
    bins = a.output/'bin'
    bins.mkdir()
    for file in ('libtm2020_official_step.so', 'libtm2020_policy.so',
                 'tm2020_init_headless_policy', 'tm2020_rollout_audit'):
        shutil.copy2(build/file, bins/file)
    if (build/'tm2020_official_train').exists():
        shutil.copy2(build/'tm2020_official_train', bins/'tm2020_official_train')
    shutil.copy2(ROOT/'cache/official-step-rust-target/release/tm2020-official-tape', bins/'tm2020-official-tape')
    common = ['--server', a.server.resolve(), '--map', a.map.resolve(), '--ghost', a.ghost.resolve(),
              '--shim', bins/'libtm2020_official_step.so']
    def script(name): return [sys.executable, ROOT/'scripts'/name]
    run('control-qualification', script('test_official_engine.py')+common+[
        '--tape-tool', bins/'tm2020-official-tape', '--output', a.output/'controls'], 300)
    # Independent driver on a second human file. Its source controls are not fitted.
    run('second-human', script('official_engine.py')+[
        '--server', a.server.resolve(), '--map', FIXTURES/'map2.Map.Gbx',
        '--ghost', FIXTURES/'human_23013.Ghost.Gbx', '--shim', bins/'libtm2020_official_step.so',
        '--output', a.output/'second-human'])
    if a.train:
        training = ['--policy-dll', bins/'libtm2020_policy.so',
                    '--initializer', bins/'tm2020_init_headless_policy',
                    '--auditor', bins/'tm2020_rollout_audit']
        run('native-ppo', script('train_official_ppo.py')+common+training+[
            '--output', a.output/'ppo', '--updates', str(a.updates), '--episodes', str(a.episodes)], 600)
        audit = ['--policy-dll', bins/'libtm2020_policy.so']
        run('native-ppo-replay-audit', script('audit_official_ppo.py')+common+audit+[
            '--run', a.output/'ppo', '--output', a.output/'ppo/audit.json'], 600)
        latest = a.output/f'ppo/update-{a.updates-1:04d}'
        run('native-ppo-resume', script('train_official_ppo.py')+common+training+[
            '--resume', latest/'training.checkpoint', '--updates', '1', '--episodes', '2',
            '--output', a.output/'resumed'], 300)
        run('native-ppo-resume-audit', script('audit_official_ppo.py')+common+audit+[
            '--run', a.output/'resumed', '--output', a.output/'resumed/audit.json'], 300)
        # Resuming the same checkpoint must reproduce sampling, optimizer and shuffle RNGs.
        run('native-ppo-resume-repeat', script('train_official_ppo.py')+common+training+[
            '--resume', latest/'training.checkpoint', '--updates', '1', '--episodes', '2',
            '--output', a.output/'resumed-repeat'], 300)
        for name in ('training.checkpoint', 'updated.tmppo', 'rollout.csv', 'decisions.json'):
            if sha(a.output/'resumed/update-0000'/name) != sha(a.output/'resumed-repeat/update-0000'/name):
                raise AssertionError('Native resumed training is not byte-reproducible: '+name)
        if (bins/'tm2020_official_train').exists():
            run('fully-native-training', [bins/'tm2020_official_train', a.server.resolve(),
                a.map.resolve(), a.ghost.resolve(), bins/'libtm2020_official_step.so',
                a.output/'ppo/initial.checkpoint', a.output/'fully-native', str(a.episodes), '503', '5'], 300)
            for name in ('behavior.tmppo', 'rollout.csv', 'updated.tmppo', 'training.checkpoint'):
                if sha(a.output/'fully-native'/name) != sha(a.output/'ppo/update-0000'/name):
                    raise AssertionError('Fully native/Python-orchestrated training differs: '+name)
            with (a.output/'fully-native/physics.csv').open() as stream:
                native_rows = list(csv.DictReader(stream))
            python_rows = json.loads((a.output/'ppo/update-0000/decisions.json').read_text())
            if len(native_rows) != len(python_rows):
                raise AssertionError('Native physical transition count differs')
            for native, retained in zip(native_rows, python_rows):
                for key, other in [('trace_sha256','traceSha256'), ('before_hex','beforeStateBits'),
                                   ('after_hex','afterStateBits')]:
                    if native[key] != retained[other]:
                        raise AssertionError('Native intermediate physical state differs: '+key)
                if any(int(native[key]) != retained[other] for key, other in
                       [('episode','episode'), ('index','index'), ('advanced_ticks','advancedTicks')]):
                    raise AssertionError('Native decision boundary differs')
        run('policy-evaluation', script('evaluate_official_ppo.py')+common+audit+[
            '--models', a.output/'ppo/update-0000/behavior.tmppo', latest/'updated.tmppo',
            a.output/'resumed/update-0000/updated.tmppo', '--output', a.output/'evaluation.json'])
    report = dict(schema='tm2020_continuous_official_milestone_v1',
        controls=json.loads((a.output/'controls/report.json').read_text()),
        secondHuman=json.loads((a.output/'second-human/report.json').read_text()),
        frozenBinaries={p.name:sha(p) for p in bins.iterdir()},
        nativeTestsPassed=True, trainingRun=a.train,
        arbitraryStateRestore=False, completeIndependentSimulatorQualified=False,
        generalRacePolicyQualified=False)
    source_paths = ['native/CMakeLists.txt', 'native/src/bridge.cpp',
        'integrations/official-step/step_shim.cpp', 'integrations/official-step/native_train.cpp', 'integrations/official-step/tape.rs',
        'integrations/official-step/Cargo.toml', 'integrations/official-step/Cargo.lock'] + [
        'scripts/'+name for name in ('official_engine.py', 'official_training.py',
        'train_official_ppo.py', 'audit_official_ppo.py', 'test_official_engine.py',
        'evaluate_official_ppo.py', 'run_official_checks.py')]
    report['sourceSha256'] = {name:sha(ROOT/name) for name in source_paths}
    if a.train:
        report.update(training=json.loads((a.output/'ppo/report.json').read_text()),
            audit=json.loads((a.output/'ppo/audit.json').read_text()),
            resumedAudit=json.loads((a.output/'resumed/audit.json').read_text()),
            deterministicResumeBytesEqual=True,
            evaluation=json.loads((a.output/'evaluation.json').read_text()))
        if (a.output/'fully-native/report.json').exists():
            report['fullyNativeTraining'] = json.loads((a.output/'fully-native/report.json').read_text())
            report['fullyNativeRolloutOptimizerAndPhysicalBitsEqual'] = True
    (a.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print('PASS OFFICIAL_CONTINUOUS_MILESTONE', a.output, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--server', type=Path, default=SERVER)
    p.add_argument('--map', type=Path, default=FIXTURES/'map2.Map.Gbx')
    p.add_argument('--ghost', type=Path, default=FIXTURES/'human_22730.Ghost.Gbx')
    p.add_argument('--train', action='store_true')
    p.add_argument('--updates', type=int, default=2)
    p.add_argument('--episodes', type=int, default=3)
    main(p.parse_args())
