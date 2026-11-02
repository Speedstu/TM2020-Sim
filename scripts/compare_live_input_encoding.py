"""Compare actual visual InputSteer to the game's saved raw replay events.

Uses a fixed zero clock shift and settled event intervals, rather than fitting
against GBX.NET's lossy packed-state labels. No game actions or memory access.
"""
import bisect
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
dataset = ROOT / 'local/recon/bot-tracking-v4-dataset.json'
trace = ROOT / 'local/recon/codex-follower-tracking-v4.csv'
ghost = json.loads(dataset.read_text())['ghosts'][0]['result']
times, values = [], []
for event in ghost['inputEventTimeline']:
    if event['steerRaw'] is not None:
        times.append(event['tMs']); values.append(event['steerRaw'])
errors_live, errors_packed = [], []
with trace.open(newline='') as stream:
    for row in csv.DictReader(stream):
        time = int(row['race_ms'])
        index = bisect.bisect_right(times, time) - 1
        if index < 0 or time - times[index] < 30:
            continue
        if index + 1 < len(times) and times[index + 1] - time < 30:
            continue
        measured, raw = float(row['measured_steer']), values[index]
        errors_live.append(abs(measured - max(-1, raw / 127)))
        errors_packed.append(abs(measured - (2 * raw - 1) / 255))
if len(errors_live) < 100:
    raise ValueError('Insufficient settled input intervals')
report = {
    'schema': 'tm2020_live_vs_packed_input_encoding_v1', 'fixed_clock_shift_ms': 0,
    'settled_samples': len(errors_live), 'live_signed_127_mae': sum(errors_live) / len(errors_live),
    'gbx_packed_center_mae': sum(errors_packed) / len(errors_packed),
    'trace_sha256': hashlib.sha256(trace.read_bytes()).hexdigest(),
    'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
    'note': 'GBX packed-state labels and live actuator values have distinct quantizers. Preserve legacy packed labels; use live_steer_from_raw for input replay.',
}
(ROOT / 'local/recon/live-input-encoding.json').write_text(json.dumps(report, indent=2) + '\n')
print('LIVE_INPUT_ENCODING', report['settled_samples'], report['live_signed_127_mae'], report['gbx_packed_center_mae'])
