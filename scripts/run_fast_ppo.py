"""Build and run the Linux headless simulator/PPO with installed Steam assets.

Examples:
  python scripts/run_fast_ppo.py build
  python scripts/run_fast_ppo.py checks --output local/my-checks
  python scripts/run_fast_ppo.py train --output local/my-training --updates 8
  python scripts/run_fast_ppo.py eval --output local/my-evaluation --model local/my-training/best.tmppo
"""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT/'cache/fast-training-final-target'
LIBRARY = TARGET/'release/libtm2020_fast.so'
TRAINER = ROOT/'native/build-linux/tm2020_fast_train'


def steam_packs():
    configured = os.environ.get('TM2020_PACKS')
    if configured:
        packs = Path(configured).expanduser().resolve(strict=True)
        if not (packs/'Stadium.pak').is_file():
            raise FileNotFoundError(f'TM2020_PACKS does not contain Stadium.pak: {packs}')
        return packs
    home = Path.home()
    roots = [home/'.steam/steam', home/'.local/share/Steam',
             home/'.var/app/com.valvesoftware.Steam/.local/share/Steam']
    for root in list(roots):
        file = root/'steamapps/libraryfolders.vdf'
        if file.exists():
            roots.extend(Path(p.replace('\\\\', '\\')) for p in
                         re.findall(r'"path"\s+"([^"]+)"', file.read_text()))
    for root in roots:
        packs = root/'steamapps/common/Trackmania/Packs'
        if (packs/'Stadium.pak').is_file():
            return packs.resolve()
    raise FileNotFoundError('Packs/Stadium.pak absent des bibliothèques Steam ; utiliser --packs.')


def run(argv):
    subprocess.run([str(x) for x in argv], cwd=ROOT, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('mode', choices=['build', 'checks', 'bench', 'train', 'eval'])
    p.add_argument('--packs', type=Path)
    p.add_argument('--map', type=Path, default=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
    p.add_argument('--route', type=Path, default=ROOT/'local/replays/tmtas-4634.Replay.Gbx')
    p.add_argument('--output', type=Path)
    p.add_argument('--model', type=Path)
    p.add_argument('--updates', type=int, default=8)
    p.add_argument('--trials', type=int, default=10)
    p.add_argument('--controller', choices=['geometric', 'anticipation'],
                   help='anticipation physique pour le bot ; geometric pour le débit brut')
    p.add_argument('--resume', type=Path, help='Reprendre Adam et les RNG ; les courses repartent de nouveaux resets')
    p.add_argument('--seed', type=int, default=2026)
    a = p.parse_args()
    if a.mode == 'build':
        run([sys.executable, ROOT/'scripts/prepare_fast_training.py'])
        run(['cargo', 'build', '--release', '--offline', '--locked', '--manifest-path',
             ROOT/'integrations/fast-training/Cargo.toml', '--target-dir', TARGET])
        run(['cmake', '-S', ROOT/'native', '-B', ROOT/'native/build-linux', '-DCMAKE_BUILD_TYPE=Release'])
        run(['cmake', '--build', ROOT/'native/build-linux', '--target', 'tm2020_fast_train',
             'tm2020_fast_warmstart', 'tm2020_rollout_audit', 'tm2020_policy', '-j', '8'])
        return
    if a.output is None:
        p.error('--output est requis et doit désigner un nouveau dossier')
    if a.output.exists():
        p.error('Le dossier de sortie existe déjà ; les preuves ne sont jamais écrasées.')
    if a.mode == 'eval' and a.model is None:
        p.error('--model est requis pour évaluer une politique')
    packs = (a.packs or steam_packs()).resolve(strict=True)
    common = ['--library', LIBRARY, '--map', a.map.resolve(strict=True), '--packs', packs,
              '--route', a.route.resolve(strict=True), '--output', a.output.resolve()]
    if a.mode == 'checks':
        run([sys.executable, ROOT/'scripts/test_fast_engine.py', *common])
        return
    controller = a.controller or ('geometric' if a.mode == 'bench' else 'anticipation')
    planned = controller == 'anticipation'
    args = [TRAINER, '--mode', a.mode, *common, '--seed', a.seed,
            '--environments', '16', '--threads', '16', '--actions', '1',
            '--planner', int(planned), '--residual', '.05' if planned else '1.5',
            '--noise', '.008' if planned else '.035', '--horizon', '2600' if planned else '4000']
    if a.model:
        args += ['--model', a.model.resolve(strict=True)]
    if a.resume:
        args += ['--resume', a.resume.resolve(strict=True)]
    if a.mode == 'train':
        args += ['--updates', a.updates, '--curriculum', '1', '--bank-probability', '.8',
                 '--bank-decay', max(1, a.updates//2), '--eval-every', '10',
                 '--rollout', '64' if planned else '256']
    if a.mode == 'eval':
        args += ['--trials', a.trials]
    run(args)


if __name__ == '__main__':
    main()
