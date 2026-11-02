#!/usr/bin/env python3
"""Verify an original, newly saved replay against a completed internal trial.

Copies the unchanged client file only after freshness checks. Does not invent
inputs, fit a clock shift, or infer a real arrival from hook return values.
"""
import argparse
import json
from pathlib import Path
from audit_replay_controls import audit,decode
from prepare_fall_campaign import save_json
from proton_sdk import copy_immutable


def check_fresh(report,replay_mtime_ns,map_uid):
    if report.get('mode')!='control' or not report.get('workerReturnedNormally'):
        raise ValueError('A completed control trial is required')
    if not isinstance(report.get('startedUnixNs'),int) or replay_mtime_ns<report['startedUnixNs']:
        raise ValueError('Replay predates this trial; refusing an old PB autosave')
    if report.get('mapUid')!=map_uid:raise ValueError('Replay belongs to another map')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True);p.add_argument('--map-index',type=int,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=json.loads((a.trial/'control/report.json').read_text());original=a.replay.resolve(strict=True)
    value,_=decode(original);check_fresh(report,original.stat().st_mtime_ns,value['mapUid'])
    snapshot=a.trial/'client-autosave.Replay.Gbx';copy_immutable(original,snapshot)
    result=audit(a.map_index,a.trial,a.output)
    result.update(originalClientReplay=str(original),clientFinishIndependentlyVerified=False,
        inputStreamVerified=result['replayInputsMatchActuation'],clockShiftFitted=False)
    save_json(a.output/'replay-verification.json',result)
    if not result['inputStreamVerified']:raise SystemExit('Original replay inputs do not match the complete actuation trace')


if __name__=='__main__':main()
