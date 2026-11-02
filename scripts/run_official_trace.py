"""Capture two real-server resumed trajectories using validator-owned car state."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from run_official_fork_check import SERVER_SHA, sha

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('server', 'map', 'ghost', 'fk', 'shim', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--checkpoint-fraction', type=float, default=0.5)
    a = p.parse_args()
    if a.output.exists() or not 0.05 <= a.checkpoint_fraction <= 0.9:
        raise ValueError('Use a new output directory and a bounded checkpoint fraction')
    paths = {key: getattr(a, key).resolve(strict=True) for key in ('server', 'map', 'ghost', 'fk', 'shim')}
    if sha(paths['server'] / 'TrackmaniaServer') != SERVER_SHA:
        raise ValueError('Unqualified official server')
    a.output.mkdir(parents=True)
    runs = []
    for i in range(2):
        out = (a.output / f'trajectory-{i}.csv').resolve()
        with tempfile.TemporaryDirectory(prefix='tm2020-validator-trace-') as temporary:
            command = [str(paths['fk']), 'trace', '--tape', str(paths['ghost']),
                '--map', str(paths['map']), '--server', str(paths['server']),
                '--shim', str(paths['shim']), '--at', 'frac:' + str(a.checkpoint_fraction),
                '--work', temporary, '--out', str(out)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
        log = result.stdout + result.stderr
        (a.output / f'run-{i}.log').write_text(log)
        match = re.search(r'self-check ok:\s*(\d+) rows', log)
        if result.returncode or not match or 'VALIDATOR CAR controller' not in log:
            raise RuntimeError('Validator-owned trace failed: ' + log[-3000:])
        with out.open(newline='') as stream:
            rows = list(csv.reader(stream))
        count = len(rows) - 1
        if count != int(match.group(1)) or count < 100:
            raise RuntimeError('Trace row count does not match self-check')
        runs.append(dict(rows=count, sha256=sha(out), log=log))
    identical = runs[0]['sha256'] == runs[1]['sha256']
    report = dict(schema='tm2020_validator_owned_official_trace_v1',
        serverSha256=SERVER_SHA, fkSha256=sha(paths['fk']), shimSha256=sha(paths['shim']),
        mapSha256=sha(paths['map']), ghostSha256=sha(paths['ghost']), runs=runs,
        byteIdenticalAcrossFreshProcesses=identical,
        controlledPlayerIdentityFromValidatorOwnership=True,
        resumedTrajectory=True, wholeRunPhysicalStateEquivalenceQualified=False,
        completeIndependentSimulatorQualified=False, arbitraryStateStepQualified=False)
    (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    if not identical:
        raise RuntimeError('Fresh-process resumed trajectories differed; evidence retained')
    print('PASS VALIDATOR_OWNED_TRACE', runs[0]['rows'], 'rows, two fresh processes byte-identical')

if __name__ == '__main__':
    main()
