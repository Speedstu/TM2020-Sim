"""Re-run native PPO histories in fresh official processes and audit successors."""
import argparse
import csv
import json
import math
from pathlib import Path

from official_engine import sha
from official_training import OfficialTraining, SCHEMA
from owned_ppo import OwnedPolicy


def require(ok, message):
    if not ok: raise AssertionError(message)


def main(a):
    if a.output.exists():
        raise ValueError('Never overwrite an audit')
    report = json.loads((a.run/'report.json').read_text())
    require(report['observationSchema'] == SCHEMA, 'Unsupported observation/action schema')
    require(report['shimSha256'] == sha(a.shim), 'Audit shim differs from collector')
    require(report['policyLibrarySha256'] == sha(a.policy_dll), 'Audit PPO library differs')
    require(report['mapSha256'] == sha(a.map) and report['ghostSha256'] == sha(a.ghost), 'Race fixtures differ')
    env = OfficialTraining(a.server, a.map, a.ghost, a.shim, report['horizon'], report['actionRepeat'])
    total, ticks, updates = 0, 0, []
    try:
        for update in report['updates']:
            folder = a.run/f"update-{update['index']:04d}"
            decisions = json.loads((folder/'decisions.json').read_text())
            with (folder/'rollout.csv').open() as stream:
                rows = list(csv.DictReader(stream))
            require(len(rows) == len(decisions) == update['acceptedTransitions'], 'Rollout row count differs')
            policy = OwnedPolicy(a.policy_dll, folder/'behavior.tmppo', SCHEMA)
            previous_episode, maximum_bootstrap_error = None, 0.0
            try:
                for i, (row, retained) in enumerate(zip(rows, decisions)):
                    if previous_episode != retained['episode']:
                        x = env.reset()
                        previous_episode = retained['episode']
                    require(x == retained['observation'] == [float(row[f'observation_{j}']) for j in range(13)],
                            'Causal policy observation differs')
                    sampled = [math.tanh(float(row[f'latent_{j}'])) for j in range(3)]
                    require(all(abs(x-y) < 1e-14 for x, y in zip(sampled, retained['action'])),
                            'Retained action differs from native rollout')
                    successor, reward, terminated, truncated, info = env.step(retained['action'])
                    require(successor == retained['successor'], 'Fresh-process successor observation differs')
                    for key in ('beforeRaceMs', 'afterRaceMs', 'controls', 'advancedTicks',
                                'traceSha256', 'beforeStateBits', 'afterStateBits'):
                        require(info[key] == retained[key], f'Original engine {key} differs')
                    require(reward == retained['reward'] == float(row['reward']), 'Displacement reward differs')
                    _, bootstrap = policy.predict(successor)
                    error = abs(bootstrap-float(row['next_value']))
                    maximum_bootstrap_error = max(maximum_bootstrap_error, error)
                    require(error < 1e-12, 'Successor critic bootstrap differs')
                    boundary = i+1 == len(decisions) or decisions[i+1]['episode'] != retained['episode']
                    require(truncated == boundary == retained['truncated'] == bool(int(row['truncated'])) and
                            not terminated and not retained['terminated'] and int(row['terminated']) == 0,
                            'Terminal or truncation semantics differ')
                    require(info['advancedTicks']/report['actionRepeat'] == float(row['elapsed_steps']),
                            'Final partial action duration differs')
                    total += 1
                    ticks += info['advancedTicks']
                    x = successor
            finally:
                policy.close()
            updates.append(dict(index=update['index'], transitions=len(rows),
                allOriginalStateBitsExact=True, observationsExact=True, rewardsExact=True,
                boundariesAndDurationsExact=True, bootstrapMaximumError=maximum_bootstrap_error))
    finally:
        env.close()
    require(total == report['totalAcceptedTransitions'], 'Report total differs')
    result = dict(schema='tm2020_continuous_official_ppo_audit_v1', transitions=total,
        originalPhysicsTicksReplayed=ticks, updates=updates,
        collectorReportSha256=sha(a.run/'report.json'), shimSha256=sha(a.shim),
        policyLibrarySha256=sha(a.policy_dll), sourceControlsUsedInObservations=False,
        freshProcessReplay=True, forkUsed=False,
        completeIndependentSimulatorQualified=False, generalRacePolicyQualified=False)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print('PASS ORIGINAL_SERVER_PPO_AUDIT', total, 'decisions', ticks, 'physics ticks')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'server', 'map', 'ghost', 'shim', 'policy-dll', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    main(p.parse_args())
