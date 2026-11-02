"""Evaluate configured/learned policies on the same declared bounded task."""
import argparse
import json
from pathlib import Path

from official_engine import sha
from official_training import OfficialTraining, SCHEMA
from owned_ppo import OwnedPolicy


def main(a):
    if a.output.exists(): raise ValueError('Never overwrite evaluation evidence')
    cases = []
    with OfficialTraining(a.server, a.map, a.ghost, a.shim, a.horizon, a.repeat) as env:
        for model in [None] + a.models:
            policy = OwnedPolicy(a.policy_dll, model, SCHEMA) if model else None
            try:
                observation, score, count = env.reset(), 0.0, 0
                while True:
                    action = policy.predict(observation)[0] if policy else [1.0, -1.0, 0.0]
                    observation, reward, terminated, truncated, _ = env.step(action)
                    score += reward
                    count += 1
                    if terminated or truncated: break
                cases.append(dict(model=str(model.resolve()) if model else 'fixed_full_throttle',
                    modelSha256=sha(model) if model else None, forwardDisplacementMetres=score,
                    transitions=count, ticks=env.ticks))
            finally:
                if policy: policy.close()
    report = dict(schema='tm2020_official_bounded_task_evaluation_v1',
        horizon=a.horizon, repeat=a.repeat, cases=cases,
        mapSha256=sha(a.map), ghostSha256=sha(a.ghost), shimSha256=sha(a.shim),
        fullRaceEvaluation=False, generalRacePolicyQualified=False)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS OFFICIAL_POLICY_EVALUATION', [(r['model'],r['forwardDisplacementMetres']) for r in cases])


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('server', 'map', 'ghost', 'shim', 'policy-dll', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--models', type=Path, nargs='+', required=True)
    p.add_argument('--horizon', type=int, default=503)
    p.add_argument('--repeat', type=int, default=5)
    main(p.parse_args())
