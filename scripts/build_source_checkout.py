#!/usr/bin/env python3
"""Build the source distribution on Linux. Never starts training or a game."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/native'
TARGETS = [
    'tm2020_sdk', 'tm2020_trajectory', 'tm2020_vector_physics',
    'tm2020_trajectory_hybrid_test', 'tm2020_internal_tick_test',
    'tm2020_input_statistics_test', 'tm2020_hybrid_actions_test',
]


def run(args):
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--offline', action='store_true')
    p.add_argument('--native-only', action='store_true')
    args = p.parse_args()
    if sys.platform != 'linux':
        p.error('The standalone simulator build currently targets Linux.')
    if not 1 <= args.jobs <= 128:
        p.error('--jobs must be in 1..128')
    run(['cmake', '-S', ROOT / 'native', '-B', NATIVE, '-DCMAKE_BUILD_TYPE=Release'])
    run(['cmake', '--build', NATIVE, '--parallel', args.jobs, '--target', *TARGETS])
    for name in ('tm2020_trajectory_hybrid_test', 'tm2020_internal_tick_test',
                 'tm2020_input_statistics_test', 'tm2020_hybrid_actions_test'):
        run([NATIVE / name])
    if not args.native_only:
        for adapter, target in [('fast-training', 'source-fast-target'),
                                ('speed-training', 'source-speed-target'),
                                ('training-metadata', 'source-metadata-target')]:
            run(['cargo', 'build', '--release', '--locked', '--jobs', args.jobs,
                 *(['--offline'] if args.offline else []),
                 '--manifest-path', ROOT / 'integrations' / adapter / 'Cargo.toml',
                 '--target-dir', ROOT / 'cache' / target])
        run(['cargo', 'check', '--locked', '--lib',
             *(['--offline'] if args.offline else []),
             '--manifest-path', ROOT / 'rust/tm2020-sdk/Cargo.toml'])
    print(json.dumps({'nativeBuild': str(NATIVE), 'nativeTestsPassed': 4,
                      'rustBuilt': not args.native_only,
                      'trainingStarted': False, 'gameStarted': False}, indent=2))


if __name__ == '__main__':
    main()
