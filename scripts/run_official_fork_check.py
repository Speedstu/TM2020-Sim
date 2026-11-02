"""Bounded real-server fork versus whole-run validation; Linux/WSL only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

SERVER_SHA = '3b6107824feea402bd32c888e994dcd6df4a10afc8676a2647ac9560ccf0d779'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('server', 'map', 'ghost', 'fk', 'shim', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--checkpoint-tick', type=int, default=60)
    p.add_argument('--candidates', type=int, default=20)
    p.add_argument('--span', type=int, default=60)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Never overwrite fork-check evidence')
    if not 1 <= a.candidates <= 100 or not 1 <= a.span <= 1000 or a.checkpoint_tick < 0:
        raise ValueError('Unbounded or invalid fork check')
    paths = {key: getattr(a, key).resolve(strict=True) for key in ('server', 'map', 'ghost', 'fk', 'shim')}
    if sha(paths['server'] / 'TrackmaniaServer') != SERVER_SHA:
        raise ValueError('Unqualified official server build')
    if not (paths['server'] / 'Packs').is_dir():
        raise ValueError('Missing server Packs')
    with tempfile.TemporaryDirectory(prefix='tm2020-fork-check-') as temporary:
        command = [str(paths['fk']), 'server', 'check',
            '--tape', str(paths['ghost']), '--map', str(paths['map']),
            '--server', str(paths['server']), '--shim', str(paths['shim']),
            '--at', 'tick:' + str(a.checkpoint_tick), '--work', temporary,
            '--n', str(a.candidates), '--span', str(a.span)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    output = result.stdout + result.stderr
    exact = re.search(r'exactness:\s*(\d+)/(\d+) identical.*?(\d+) MISMATCHES', output)
    repeat = re.search(r'oracle repeatability:\s*(\d+) of (\d+) candidates differ', output)
    if result.returncode != 0 or not exact or not repeat:
        raise RuntimeError('Fork check failed: ' + output[-4000:])
    identical, total, mismatch = map(int, exact.groups())
    different, repeated = map(int, repeat.groups())
    if (identical, total, mismatch, different, repeated) != (a.candidates, a.candidates, 0, 0, a.candidates):
        raise RuntimeError('Fork check did not prove candidate equivalence: ' + output[-4000:])
    report = dict(schema='tm2020_official_fork_check_v1', officialServerSha256=SERVER_SHA,
        mapSha256=sha(paths['map']), ghostSha256=sha(paths['ghost']),
        fkSha256=sha(paths['fk']), shimSha256=sha(paths['shim']),
        checkpointTick=a.checkpoint_tick, candidateCount=a.candidates, span=a.span,
        exactCandidates=identical, forkVsWholeRunMismatches=mismatch,
        wholeRunRepeatabilityMismatches=different,
        report=output, originalGamePhysicsExecuted=True,
        completeIndependentSimulatorQualified=False,
        arbitraryStateResetStepQualified=False)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS OFFICIAL_FORK_CHECK {identical}/{total} whole-run identical')

if __name__ == '__main__':
    main()
