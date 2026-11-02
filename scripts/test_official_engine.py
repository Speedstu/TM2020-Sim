"""Real original-server differential tests for the continuous step backend."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import time

from official_engine import OfficialEngine, sha
from run_official_server_oracle import SERVER_SHA


def run_tape(engine, selector, edits_path=None):
    state = engine.reset()
    rows, edits = [], []
    while state is not None:
        action = selector(state)
        rows.append(state)
        if action is not None:
            s, g, b = action
            si = round(s * 127)
            if abs(si / 127 - s) > 1e-7 or g not in (0, 1) or b not in (0, 1):
                raise ValueError('Differential export requires representable ghost inputs')
            edits.append(f"{state['inputIndex']} {si} {int(g)} {int(b)}\n")
        state = engine.step(action)
    result = engine.result()
    if len(result) != 1:
        raise RuntimeError('One ghost must produce one original-server result')
    if edits_path is not None:
        edits_path.write_text(''.join(edits))
    return rows, result[0]


def state_bits(row):
    return bytes.fromhex(row['rawHex'])[-40:]


def digest(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update(struct.pack('<ii', row['raceMs'], row['inputIndex']))
        h.update(state_bits(row))
    return h.hexdigest()


def compare(a, b):
    # Vehicle construction precedes race zero and its transient buffers are not
    # a qualified deterministic state. Retain them, count differences explicitly,
    # and require every race-zero-and-later state without a fitted time shift.
    pre_a = {r['raceMs']:state_bits(r) for r in a if r['raceMs'] < 0}
    pre_b = {r['raceMs']:state_bits(r) for r in b if r['raceMs'] < 0}
    countdown_differences = sum(pre_a.get(t) != pre_b.get(t) for t in pre_a.keys() | pre_b.keys())
    a = [r for r in a if r['raceMs'] >= 0]
    b = [r for r in b if r['raceMs'] >= 0]
    if len(a) != len(b):
        raise AssertionError(f'Physical state count differs: {len(a)} vs {len(b)}')
    for left, right in zip(a, b):
        if left['raceMs'] != right['raceMs'] or left['inputIndex'] != right['inputIndex'] or state_bits(left) != state_bits(right):
            raise AssertionError(f"Physical state bits differ at {left['raceMs']} ms")
    return countdown_differences


def require(ok, message):
    if not ok: raise AssertionError(message)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('server', 'map', 'ghost', 'shim', 'tape-tool', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    meta = json.loads(subprocess.check_output([str(a.tape_tool.resolve()), 'info', str(a.ghost.resolve())]))
    started = time.monotonic()
    common = dict(server=a.server, track=a.map, ghost=a.ghost, shim=a.shim)
    with OfficialEngine(**common) as engine:
        reference, result = run_tape(engine, lambda _: None)
        repeated, repeated_result = run_tape(engine, lambda _: None)
        for name, data in [('reference', reference), ('repeated', repeated)]:
            (a.output / (name+'-states.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in data))
        repeat_countdown_differences = compare(reference, repeated)
        require(result == repeated_result, 'Fresh-process result differs')
        require(result['validatedMs'] == meta['declaredMs'], 'Reference finish differs')
        # Validation errors must not consume an action or change the boundary.
        initial = engine.reset()
        for invalid in ((float('nan'), 1, 0), (0, -1, 0), (2, 0, 0), (0, 1)):
            try:
                engine.step(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid action accepted')
            require(engine.state == initial, 'Rejected command consumed a boundary')
        engine.close()
    cases = []
    selectors = {
        'identity': lambda r: r['controls'] if 0 <= r['inputIndex'] < r['tapeCount'] else None,
        'brake': lambda r: (0, 0, 1) if 1000 <= r['raceMs'] < 1300 else None,
        'left': lambda r: (-25/127, 1, 0) if 500 <= r['raceMs'] < 800 else None,
        'right': lambda r: (25/127, 1, 0) if 500 <= r['raceMs'] < 800 else None,
        'coast': lambda r: (0, 0, 0) if 0 <= r['raceMs'] < 1000 else None,
    }
    for name, selector in selectors.items():
        edits = a.output / (name + '.tsv')
        ghost = a.output / (name + '.Ghost.Gbx')
        with OfficialEngine(**common) as engine:
            rows, actual = run_tape(engine, selector, edits)
        encoded = subprocess.run([str(a.tape_tool.resolve()), 'patch', str(a.ghost.resolve()),
                                  str(edits.resolve()), str(ghost.resolve())],
                                 check=True, capture_output=True, text=True)
        with OfficialEngine(a.server, a.map, ghost, a.shim) as engine:
            file_rows, file_result = run_tape(engine, lambda _: None)
        for suffix, data in [('active', rows), ('file', file_rows)]:
            (a.output / (name+'-'+suffix+'-states.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in data))
        countdown_differences = compare(rows, file_rows)
        require(actual['validatedMs'] == file_result['validatedMs'], 'Encoded finish differs')
        require(actual['validatedCheckpoints'] == file_result['validatedCheckpoints'], 'Encoded checkpoints differ')
        oracle = a.output / (name + '-plain.json')
        subprocess.run([sys.executable, str(Path(__file__).with_name('run_official_server_oracle.py')),
                        '--server', str(a.server), '--map', str(a.map), '--ghost', str(ghost),
                        '--output', str(oracle)], check=True, capture_output=True, text=True)
        plain = json.loads(oracle.read_text())['results'][0]
        require(actual['validatedMs'] == plain['validatedMs'], 'Uninstrumented finish differs')
        require(actual['validatedCheckpoints'] == plain['validatedCheckpoints'], 'Uninstrumented checkpoints differ')
        changed = sum(x['raceMs'] >= 0 and state_bits(x) != state_bits(y) for x, y in zip(reference, rows))
        if name == 'identity':
            compare(reference, rows)
        else:
            require(changed > 100, f'{name}: no causal physical response')
        for r in rows:
            require(r['raceMs'] == r['engineMs'] - r['originMs'], 'Race clock differs')
            require(r['inputIndex'] == (r['raceMs'] - meta['startOffsetMs']) // 10, 'Input clock differs')
            require(abs(sum(v*v for v in r['quaternionWxyz']) - 1) < 0.001, 'Quaternion norm differs')
        case = dict(name=name, frames=len(rows), raceFrames=sum(r['raceMs']>=0 for r in rows), stateSha256=digest(rows),
                    activeVsColdFileRaceStateBitsEqual=True, countdownStateMismatches=countdown_differences,
                    plainResultMatches=True,
                    validatedMs=plain['validatedMs'], validatedCheckpoints=plain['validatedCheckpoints'],
                    statesChangedFromReference=changed, codec=json.loads(encoded.stdout))
        case['activeServerIsValid'] = actual['serverIsValid']
        case['fileServerIsValid'] = file_result['serverIsValid']
        case['plainServerIsValid'] = plain['serverIsValid']
        case['activeDescription'] = actual['description']
        case['plainDescription'] = plain['description']
        cases.append(case)
        (a.output / (name + '-states.jsonl')).write_text(''.join(json.dumps(r)+'\n' for r in rows))
        print('PASS ORIGINAL_CONTROL_DIFFERENTIAL', name, len(rows), 'states', plain['validatedMs'], flush=True)
    report = dict(schema='tm2020_continuous_official_qualification_v1',
        serverSha256=SERVER_SHA, shimSha256=sha(a.shim), tapeToolSha256=sha(a.tape_tool),
        mapSha256=sha(a.map), ghostSha256=sha(a.ghost),
        referenceFrames=len(reference), freshProcessRepeatRaceStateBitsEqual=True,
        stateEqualityDomain='pre-input boundaries at raceMs >= 0',
        freshProcessCountdownStateMismatches=repeat_countdown_differences,
        countdownStateEqualityQualified=False,
        sourceInputMetadata=meta, cases=cases, wallSeconds=time.monotonic()-started,
        causalStep=True, fromStart=True, forkUsed=False,
        arbitraryStateRestore=False, completeIndependentSimulatorQualified=False,
        serverClientVersionEquivalenceQualified=False, generalRacePolicyQualified=False)
    (a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS OFFICIAL_STEP_QUALIFICATION', len(cases), 'counterfactual controls')


if __name__ == '__main__': main()
