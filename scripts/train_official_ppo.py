"""Native C++ PPO on continuous original-server physics; a bounded driving task."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from official_engine import sha
from official_training import OfficialTraining, SCHEMA, OBSERVATIONS
from owned_ppo import OwnedPpo
from run_official_server_oracle import SERVER_SHA


def main(a):
    if not 1 <= a.updates <= 1000 or not 1 <= a.episodes <= 100 or not 8 <= a.hidden <= 256:
        raise ValueError('Invalid bounded native PPO run')
    a.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = dict(schema='tm2020_continuous_official_ppo_v1', serverSha256=SERVER_SHA,
        shimSha256=sha(a.shim), policyLibrarySha256=sha(a.policy_dll),
        mapPath=str(a.map.resolve()), mapSha256=sha(a.map),
        ghostPath=str(a.ghost.resolve()), ghostSha256=sha(a.ghost),
        observationSchema=SCHEMA, observations=OBSERVATIONS, hidden=a.hidden,
        seed=a.seed, horizon=a.horizon, actionRepeat=a.repeat,
        actionMapping='gas=a0>=0; brake=a1>=0; steer=round(127*a2)/127 as float32',
        reward='displacement along initial forward direction, metres',
        sourceControlsUsedInObservations=False, originalGamePhysicsExecuted=True,
        forkUsed=False, resetStartsFreshProcess=True, updates=[],
        completeIndependentSimulatorQualified=False, generalRacePolicyQualified=False)
    trainer = OwnedPpo(a.policy_dll, OBSERVATIONS, 3, SCHEMA, a.seed, hidden=a.hidden)
    env = OfficialTraining(a.server, a.map, a.ghost, a.shim, a.horizon, a.repeat)
    try:
        initial = a.resume
        if initial is None:
            initial = a.output / 'initial.checkpoint'
            subprocess.run([str(a.initializer.resolve()), str(OBSERVATIONS), '3', str(a.hidden),
                            str(a.seed), SCHEMA, str(initial.resolve())], check=True, capture_output=True)
        trainer.file('resume', initial)
        report['initialCheckpointSha256'] = sha(initial)
        report['resumed'] = a.resume is not None
        for update in range(a.updates):
            folder = a.output / f'update-{update:04d}'
            folder.mkdir()
            behavior = folder / 'behavior.tmppo'
            trainer.file('export', behavior)
            decisions, episodes = [], []
            for episode in range(a.episodes):
                x = env.reset()
                score, index = 0.0, 0
                while True:
                    action = trainer.sample(x)
                    try:
                        successor, reward, terminated, truncated, info = env.step(action)
                    except Exception:
                        trainer.cancel()
                        raise
                    trainer.observe(reward, successor, terminated=terminated, truncated=truncated,
                                    duration=info['advancedTicks']/a.repeat)
                    decisions.append(dict(episode=episode, index=index, action=action,
                        observation=x, successor=successor, reward=reward,
                        terminated=terminated, truncated=truncated, **info))
                    score += reward
                    index += 1
                    x = successor
                    if terminated or truncated: break
                episodes.append(dict(episode=episode, transitions=index, ticks=env.ticks,
                                     reward=score))
                print('OFFICIAL_PPO_EPISODE', update, episode, index, 'transitions', score, flush=True)
            trainer.file('rollout_csv', folder / 'rollout.csv')
            (folder / 'decisions.json').write_text(json.dumps(decisions, separators=(',', ':')) + '\n')
            subprocess.run([str(a.auditor.resolve()), str(behavior.resolve()),
                str((folder/'rollout.csv').resolve()), str((folder/'behavior-audit.json').resolve()),
                '--multiple-episodes'], check=True, capture_output=True)
            metrics = trainer.update()
            trainer.file('checkpoint', folder / 'training.checkpoint')
            trainer.file('export', folder / 'updated.tmppo')
            report['updates'].append(dict(index=update, acceptedTransitions=len(decisions),
                episodes=episodes, metrics=metrics, behaviorSha256=sha(behavior),
                updatedModelSha256=sha(folder/'updated.tmppo'),
                behaviorAudit=json.loads((folder/'behavior-audit.json').read_text())))
            report['totalAcceptedTransitions'] = sum(u['acceptedTransitions'] for u in report['updates'])
            report['wallSeconds'] = time.monotonic()-started
            (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    finally:
        env.close()
        trainer.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('server', 'map', 'ghost', 'shim', 'policy-dll', 'initializer', 'auditor', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--resume', type=Path)
    p.add_argument('--updates', type=int, default=2)
    p.add_argument('--episodes', type=int, default=3)
    p.add_argument('--horizon', type=int, default=503)
    p.add_argument('--repeat', type=int, default=5)
    p.add_argument('--hidden', type=int, default=32)
    p.add_argument('--seed', type=int, default=2026)
    main(p.parse_args())
