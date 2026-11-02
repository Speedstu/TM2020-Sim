#!/usr/bin/env python3
"""Run a bundled Fall 2026-01 controller in the standalone simulator only."""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'models/fall-2026-01'


def main():
    manifest = json.loads((MODEL_DIR / 'manifest.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--champion', choices=[a['id'] for a in manifest['artifacts']], required=True)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--packs', type=Path, required=True)
    parser.add_argument('--seed', type=int)
    parser.add_argument('--horizon', type=int, default=3500, help='Maximum number of 10 ms ticks')
    parser.add_argument('--output', type=Path, help='New JSON report; existing files are never overwritten')
    args = parser.parse_args()
    if not 1 <= args.horizon <= 10000:
        parser.error('--horizon must be in 1..10000')
    if args.seed is not None and not 0 <= args.seed < 2**32:
        parser.error('--seed must fit an unsigned 32-bit integer')
    if args.output and args.output.exists():
        parser.error('--output already exists')
    if not (args.packs / 'Stadium.pak').is_file():
        parser.error('--packs must contain Stadium.pak')
    item = next(a for a in manifest['artifacts'] if a['id'] == args.champion)
    asset = MODEL_DIR / item['file']
    if hashlib.sha256(asset.read_bytes()).hexdigest() != item['sha256']:
        parser.error('Bundled model checksum differs from its manifest')
    if not args.map.is_file() or hashlib.sha256(args.map.read_bytes()).hexdigest() != manifest['mapSha256']:
        parser.error('Map file differs from the exact Fall 2026-01 version bound to this model')
    os.environ['TM2020_PACKS'] = str(args.packs.resolve())
    os.environ['TM2020_HYBRID_CORE'] = str(ROOT / 'build/native/libtm2020_trajectory.so')
    from hybrid_tracking import Hybrid, load_asset
    from vector_physics import VectorPhysics
    load_asset(asset, map_path=args.map, uid=manifest['mapUid'])
    seed = item['defaultSeed'] if args.seed is None else args.seed
    normal = item['controlMode'] == 'normal-recorded-inputs'
    with VectorPhysics(1, decision_ticks=1,
                       api_path=ROOT / 'build/native/libtm2020_vector_physics.so',
                       library=ROOT / 'cache/source-speed-target/release/libtm2020_speed.so',
                       map_path=args.map.resolve(), horizon=args.horizon,
                       normal_inputs=normal, internal_controls=not normal) as env, Hybrid(asset, 1) as bot:
        env.reset(0, seed)
        for _ in range(args.horizon):
            controls = bot.act(env)
            bot.commit(0, float(controls[0, 2]))
            env.step(controls)
            if env.states[0].terminated or env.states[0].truncated:
                break
        state = env.states[0]
        finish = int(state.finish_ms) if state.finish_ms >= 0 else None
        report = {'champion': item['id'], 'modelSha256': item['sha256'],
                  'mapUid': manifest['mapUid'], 'seed': seed,
                  'controlMode': item['controlMode'], 'finishMs': finish,
                  'checkpoints': int(state.checkpoints), 'ticks': int(state.tick),
                  'defaultSeedResultMatches': finish == item['expectedSeedFinishMs'] if seed == item['defaultSeed'] else None,
                  'gameStarted': False, 'trainingStarted': False,
                  'onlineRankVerified': False}
    if args.output:
        with args.output.open('x') as stream:
            stream.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return int(finish is None or report['defaultSeedResultMatches'] is False)


if __name__ == '__main__':
    raise SystemExit(main())
