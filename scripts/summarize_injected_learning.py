"""Recompute historical injected driving/learning qualification from artifacts.

Loader module observations are historical recorded observations; a replay's
finish needs separate screenshot + saved replay evidence. No physics claim.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = '3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def retained_path(text):
    path = Path(text).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('Missing/outside-workspace retained artifact')
    return path


trials = []
for path in sorted((ROOT/'local/recon').glob('injected-*.json')):
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema') != 'tm2020_injected_bot_execution_v1':
        continue
    result = {'evidence': path.relative_to(ROOT).as_posix(), 'injected_driving_verified': False,
              'ppo_update_verified': False, 'deterministic_evaluation_verified': False,
              'worker_returned_success': bool(data.get('finishedWorkerNormally'))}
    trials.append(result)
    try:
        module = retained_path(data['modulePath']); trace = retained_path(data['trace'])
        config = (ROOT/'local/runtime'/path.stem).with_suffix('.args')
        arguments = config.read_text(encoding='utf-8-sig').splitlines()
        if arguments[:2] != ['TM2020_LOCAL_BOT_ARGUMENTS_V1','--confirm-local-solo']:
            raise ValueError('Invalid retained worker configuration')
        manifest = retained_path(arguments[2]).read_text().splitlines()
        if manifest[0] != 'TM2020_POSE_CANDIDATES_V3' or int(manifest[1]) != data['processId'] or manifest[3] != BUILD:
            raise ValueError('Worker/manifest game identity mismatch')
        if retained_path(arguments[4]) != trace:
            raise ValueError('Worker configuration trace mismatch')
        status = Path(str(config)+'.status').read_text().splitlines()
        if status != data['workerStatus'] or status[:2] != ['TM2020_INJECTED_WORKER_STATUS_V1',str(data['processId'])]:
            raise ValueError('Worker status artifact mismatch')
        if digest(module) != data['moduleSha256'] or not data['modulePathVerified']:
            raise ValueError('Module evidence mismatch')
        if data.get('gameExeSha256', BUILD) != BUILD:
            raise ValueError('Wrong game executable build')
        if data.get('traceSha256') and digest(trace) != data['traceSha256']:
            raise ValueError('Trace was modified after qualification')
        with trace.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) < 100 or any(int(row['host_pid']) != data['processId'] for row in rows):
            raise ValueError('Insufficient in-process observations')
        points = [(float(r['x']),float(r['y']),float(r['z'])) for r in rows]
        if not all(math.isfinite(x) for point in points for x in point):
            raise ValueError('Non-finite driving trace')
        motion = max(math.dist(p, points[0]) for p in points)
        clocks = len({int(r['clock_candidate_ms']) for r in rows})
        response = sum(float(r['gas'])>.5 and float(r['measured_gas'])>.5 for r in rows)
        result.update(trace=trace.relative_to(ROOT).as_posix(), trace_sha256=digest(trace),
                      rows=len(rows), displacement_m=motion, distinct_clocks=clocks, throttle_response_rows=response)
        if motion<=10 or clocks<10 or response<10:
            raise ValueError('No measured vehicle motion/input response')
        result['injected_driving_verified'] = True
        metrics = data.get('ppoMetrics')
        if metrics and int(metrics['minibatches'])>0 and float(metrics['actor_parameter_l2_change'])>0:
            behavior = Path(str(trace)+'.behavior.tmppo'); rollout = Path(str(trace)+'.rollout.csv')
            audit = Path(str(trace)+'.audit.json')
            subprocess.run([str(ROOT/'native/build/tm2020_rollout_audit.exe'), str(behavior), str(rollout), str(audit)], check=True)
            checked = json.loads(audit.read_text())
            if checked['transitions'] != int(metrics['transitions']):
                raise ValueError('Rollout/update transition count mismatch')
            result.update(ppo_update_verified=True, transitions=checked['transitions'],
                          adam_restored=str(metrics['adam_state_restored']).lower() in ('true','1'),
                          behavior_sha256=digest(behavior), rollout_sha256=digest(rollout), audit=checked)
        evaluation = data.get('evaluationMetrics')
        if data.get('deterministicEvaluation') and evaluation and int(evaluation['optimizer_updates'])==0:
            result['deterministic_evaluation_verified'] = (evaluation['deterministic']=='true' and evaluation['no_exploration']=='true')
    except (ValueError,KeyError,TypeError,OSError,subprocess.CalledProcessError) as error:
        result['qualification_error'] = str(error)

report = {'schema':'tm2020_injected_learning_qualification_v1', 'all_retained_trials':trials,
          'injected_driving_verified':any(t['injected_driving_verified'] for t in trials),
          'real_game_ppo_updates':sum(t['ppo_update_verified'] for t in trials),
          'audited_real_game_transitions':sum(t.get('transitions',0) for t in trials),
          'real_game_adam_resume_verified':any(t.get('adam_restored',False) for t in trials),
          'deterministic_evaluation_verified':any(t['deterministic_evaluation_verified'] for t in trials),
          'game_strength_improvement_verified':False, 'authoritative_physics_owner_verified':False,
          'warning':'Historical local experiments on one development map. Updates and route progress do not prove race-time improvement. Failed sessions and their valid training prefixes remain visible.'}
(ROOT/'local/recon/injected-learning-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
print('INJECTED_LEARNING driving',report['injected_driving_verified'], 'updates',report['real_game_ppo_updates'],
      'audited_transitions',report['audited_real_game_transitions'], 'adam_resume',report['real_game_adam_resume_verified'])
