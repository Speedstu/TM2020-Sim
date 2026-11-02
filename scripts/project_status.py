#!/usr/bin/env python3
"""Read project paths, actual processes and frozen-model hashes. Never launches work."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def processes(root):
    result = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            argv = (proc / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            if not argv or not Path(argv[0]).name.startswith(('python', 'tm2020_')):
                continue
            if (proc / 'cwd').resolve() != root and not any(str(root) in a for a in argv):
                continue
            scripts = [Path(a).name for a in argv[1:] if a.endswith('.py')]
            if any(s.startswith(('train_', 'run_hardcode_', 'monitor_', 'search_campaign_',
                                 'run_internal_', 'repeat_internal_')) for s in scripts) or \
                    Path(argv[0]).name.startswith('tm2020_'):
                result.append({'pid': int(proc.name), 'command': ' '.join(a for a in argv if a)})
        except (OSError, ValueError):
            continue
    return result


def service(name):
    try:
        run = subprocess.run(
            ['systemctl', '--user', 'show', name, '--property=ActiveState,SubState,UnitFileState'],
            capture_output=True, text=True, timeout=5)
        return dict(line.split('=', 1) for line in run.stdout.splitlines() if '=' in line)
    except (OSError, subprocess.TimeoutExpired):
        return {'ActiveState': 'unavailable'}


def status(root=ROOT):
    config = json.loads((root / 'config/project.json').read_text())
    paths = {key: {'path': p, 'exists': (root / p).exists()}
             for key, p in config['paths'].items()}
    models = []
    for item in config['frozenModels']:
        p = root / item['path']
        digest = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        models.append({**item, 'actualSha256': digest, 'unchanged': digest == item['sha256']})
    campaigns = []
    for path in config['trainingRoots']:
        journal = root / path / 'campaign-status.json'
        try:
            state = json.loads(journal.read_text())
        except (OSError, ValueError):
            state = None
        campaigns.append({'path': path, 'journal': state,
                          'stopRequested': (root / path / 'CAMPAIGN_STOP').exists()})
    return {'requestedState': config['requestedState'], 'processes': processes(root),
            'services': {name: service(name) for name in
                         (config['legacyService'], config['historicalMonitor'])},
            'paths': paths, 'frozenModels': models, 'campaigns': campaigns,
            'knownLimitations': config['knownLimitations']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = status()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print('Consigne :', report['requestedState'])
        print('Processus de training/monitoring/contrôle détectés :', len(report['processes']))
        for proc in report['processes']:
            print(f"  PID {proc['pid']}: {proc['command']}")
        for name, state in report['services'].items():
            print(f"{name}: {state.get('ActiveState', 'unknown')}, {state.get('UnitFileState', 'unknown')}")
        for model in report['frozenModels']:
            print(f"Modèle {model['map']}: {'empreinte intacte' if model['unchanged'] else 'ABSENT OU MODIFIÉ'}")
        missing = [v['path'] for v in report['paths'].values() if not v['exists']]
        print('Chemins de travail :', 'tous présents' if not missing else ', '.join(missing))
        print('Voir docs/WORKSPACE.md ; aucun training lancé par cette commande.')
    return int(any(not m['unchanged'] for m in report['frozenModels']) or
               any(not p['exists'] for p in report['paths'].values()))


if __name__ == '__main__':
    raise SystemExit(main())
