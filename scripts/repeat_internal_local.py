#!/usr/bin/env python3
"""Maintain bounded internal workers for the user's manual local race resets.

No automatic menu/reset/driving inputs. Escape, STOP, map change, failed
qualification or an abnormal worker exit ends the session without restarting.
"""
import argparse
import fcntl
import hashlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
from prepare_fall_campaign import save_json
from proton_sdk import copy_immutable
from run_fast_ppo import ROOT

STOP=False
def stop(*_):
    global STOP
    STOP=True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--qualification',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--deployment',type=Path,required=True)
    p.add_argument('--local-solo',action='store_true');p.add_argument('--proc-debug-write',action='store_true')
    p.add_argument('--map',type=Path,default=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
    a=p.parse_args()
    if not(a.local_solo and a.proc_debug_write):p.error('Explicit local Solo test flags required')
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True)
    lock=(a.output/'SESSION.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    digest=hashlib.sha256(a.model.read_bytes()).hexdigest();model=a.output/f'candidate-{digest[:20]}.tmhyb'
    copy_immutable(a.model,model)
    qualification=json.loads(a.qualification.read_text())
    if not qualification.get('physicalConsumerQualified'):raise ValueError('Unqualified physical consumer')
    spawn=qualification.get('spawn',[1200,34.0015,1360]);uid=qualification['mapUid']
    state={'state':'starting','model':str(model),'modelSha256':digest,'mapUid':uid,
        'qualification':str(a.qualification.resolve()),'manualResetKey':'Delete','stopKey':'Escape',
        'stopFile':str(a.output/'STOP'),'hourlyMonitor':False,'autoReset':False,'gameFinishVerified':False}
    save_json(a.output/'status.json',state);index=0
    while not STOP and not(a.output/'STOP').exists():
        index+=1;folder=a.output/f'worker-{time.time_ns()}'
        command=[sys.executable,str(ROOT/'scripts/run_internal_live.py'),'--mode','control','--seconds','120',
            '--output',str(folder),'--model',str(model),'--qualification',str(a.qualification.resolve()),
            '--deployment',str(a.deployment.resolve()),'--map-uid',uid,'--spawn',*map(str,spawn),
            '--map',str(a.map.resolve()),
            '--local-solo','--proc-debug-write','--repeat-resets']
        started=time.monotonic();stop_sent=False
        with (a.output/(folder.name+'.log')).open('w') as log:
            child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            try:
                while child.poll() is None:
                    report_path=folder/'report.json'
                    try:report=json.loads(report_path.read_text())
                    except (OSError,json.JSONDecodeError):report=None
                    if report:
                        flag=Path(report['stopFile']);status=Path(str(flag)[:-5]+'.status')
                        text=status.read_text() if status.exists() else ''
                        state.update({'state':'waiting_for_manual_reset' if 'INTERNAL_INSTALLED' in text else 'installing',
                            'worker':index,'workerReport':str(report_path),'workerStopFile':str(flag),
                            'workerEvents':text.splitlines()[-12:],'updatedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')})
                        if STOP or (a.output/'STOP').exists():
                            flag.touch();stop_sent=True
                        save_json(a.output/'status.json',state)
                    if time.monotonic()-started>155:
                        if report:Path(report['stopFile']).touch()
                        raise RuntimeError('Worker deadline: neutral stop requested; session will not restart')
                    time.sleep(.25)
            finally:
                if child.poll() is None:
                    # Preserve the worker long enough to neutralize and detach;
                    # do not terminate the game's process or its Wine server.
                    try:
                        report=json.loads((folder/'report.json').read_text());Path(report['stopFile']).touch()
                    except (OSError,json.JSONDecodeError):pass
                    child.wait(timeout=15)
        report=json.loads((folder/'report.json').read_text())
        elapsed=time.monotonic()-started
        if child.returncode or not report.get('workerReturnedNormally'):
            state.update(state='failed',reason='worker did not return normally');save_json(a.output/'status.json',state)
            raise RuntimeError('Internal worker failed; session stopped')
        if stop_sent or elapsed<118:
            state.update(state='stopped',reason='Escape, map change, STOP or early safety stop');break
        # Normal 120-second lifetime only. The next worker waits for the next
        # verified manual race-zero reset; it never takes over mid-lap.
    state.update(state='stopped',updatedAt=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    save_json(a.output/'status.json',state)


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
