#!/usr/bin/env python3
"""Explicit local campaign session; fresh physical qualification per map.

Only the retained DLL drives. Official shared telemetry selects an already
frozen model; the helper never opens game process memory. One Delete reset
qualifies each map, then the user controls subsequent attempt resets.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import fcntl
from campaign_play_bundle import check_entry,check_qualification
from prepare_fall_campaign import save_json
from proton_sdk import runtime,copy_immutable
from run_fast_ppo import ROOT

STOP=False
def stop(*_):
    global STOP
    STOP=True


def process_start(pid):return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]


class Telemetry:
    def __init__(self,probe):
        self.pid,stage,command=runtime();self.start_ticks=process_start(self.pid)
        digest=hashlib.sha256(probe.read_bytes()).hexdigest();dest=stage/f'campaign-telemetry-{digest[:20]}.exe'
        copy_immutable(probe,dest)
        self.stop_file=stage/f'campaign-telemetry-{time.time_ns()}.STOP'
        self.sample={};self.when=0.;self.lock=threading.Lock()
        self.child=subprocess.Popen(command+['C:\\tm2020-sdk\\'+dest.name,'C:\\tm2020-sdk\\'+self.stop_file.name,'86400'],
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
        self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()
    def read(self):
        for line in self.child.stdout:
            try:value=json.loads(line)
            except json.JSONDecodeError:continue
            with self.lock:self.sample=value;self.when=time.monotonic()
    def current(self):
        if process_start(self.pid)!=self.start_ticks:raise RuntimeError('Client process changed; session stopped')
        with self.lock:s=dict(self.sample);when=self.when
        if time.monotonic()-when>3:return {}
        return s
    def close(self):
        self.stop_file.touch()
        try:self.child.wait(timeout=5)
        except subprocess.TimeoutExpired:self.child.terminate()
        self.thread.join(timeout=2)


def request_worker_stop(report_path):
    try:Path(json.loads(report_path.read_text())['stopFile']).touch()
    except (OSError,json.JSONDecodeError):pass


def reset_local_map():
    from local_game_ui import focus_trackmania
    w=focus_trackmania()
    x,y=w['at'];a,b=w['size']
    subprocess.run(['hyprctl','dispatch','movecursor',f'{x+a//2} {y+b//2}'],check=True,stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable,str(ROOT/'scripts/local_game_ui.py'),'--key','Delete'],check=True)


class QualificationUnavailable(RuntimeError):
    """A normally detached observation did not acquire enough stable ticks."""


def qualify(telemetry,entry,deployment,directory,stopping):
    directory.mkdir(exist_ok=True,parents=True);report=directory/'report.json'
    command=[sys.executable,str(ROOT/'scripts/run_internal_live.py'),'--mode','observe','--seconds','8',
        '--output',str(directory/'trace'),'--map',entry['map'],'--map-uid',entry['mapUid'],
        '--spawn',*map(str,entry['spawn']),'--deployment',str(deployment),'--local-solo','--proc-debug-write']
    raw=directory/'trace/report.json';started=time.monotonic();cancelled=False
    # Reset BEFORE the observer can bind the old vehicle. Resetting after
    # INTERNAL_INSTALLED can leave it attached to a retired spawn instance.
    sample=telemetry.current()
    if stopping() or not sample.get('valid') or sample.get('state')!=2 or sample.get('mapUid')!=entry['mapUid']:
        raise QualificationUnavailable('Map changed before physical observation')
    reset_local_map()
    with (directory/'observe.log').open('w') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                s=telemetry.current()
                if stopping() or not s.get('valid') or s.get('state')!=2 or s.get('mapUid')!=entry['mapUid']:
                    cancelled=True
                    request_worker_stop(raw)
                if time.monotonic()-started>30:raise RuntimeError('Physical observation deadline exceeded')
                time.sleep(.1)
        finally:
            if child.poll() is None:request_worker_stop(raw);child.wait(timeout=10)
    value=json.loads(raw.read_text())
    if not value.get('workerReturnedNormally'):raise RuntimeError('Observation did not detach normally')
    if child.returncode:raise RuntimeError('Observation failed; no controller activated')
    if cancelled or not value.get('physicalConsumerQualified'):
        raise QualificationUnavailable('Observation detached normally without enough stable qualified ticks')
    check_qualification(value,entry,telemetry.pid,telemetry.start_ticks)
    save_json(report,value);return report


def play(telemetry,entry,qualification,deployment,directory,stopping,state,save_state):
    directory.mkdir(exist_ok=True,parents=True);session=directory/'session'
    session.mkdir(exist_ok=True)
    command=[sys.executable,str(ROOT/'scripts/repeat_internal_local.py'),'--model',entry['model'],
        '--qualification',str(qualification),'--map',entry['map'],'--output',str(session),
        '--deployment',str(deployment),'--local-solo','--proc-debug-write']
    started=time.monotonic();changed=False
    with (directory/'play.log').open('w') as log:
        child=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        try:
            while child.poll() is None:
                s=telemetry.current()
                changed=not s.get('valid') or s.get('state')!=2 or s.get('mapUid')!=entry['mapUid']
                if stopping() or changed:(session/'STOP').touch()
                try:
                    live=json.loads((session/'status.json').read_text())
                    state.update(state='active' if live.get('state')=='waiting_for_manual_reset' else live.get('state'),
                        workerEvents=live.get('workerEvents',[]),sessionStatus=str(session/'status.json'))
                    save_state()
                except (FileNotFoundError,json.JSONDecodeError):pass
                if time.monotonic()-started>86400:raise RuntimeError('Client session day budget reached')
                time.sleep(.25)
        finally:
            if child.poll() is None:
                (session/'STOP').touch();child.wait(timeout=20)
    if child.returncode:raise RuntimeError('Internal session failed; do not install another controller')
    return changed


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--deployment',type=Path,required=True)
    p.add_argument('--probe',type=Path,required=True);p.add_argument('--local-solo',action='store_true')
    p.add_argument('--proc-debug-write',action='store_true');a=p.parse_args()
    if not(a.local_solo and a.proc_debug_write):p.error('Explicit authorized local Solo test flags required')
    out=a.output.resolve();out.mkdir(exist_ok=True,parents=True)
    lock=(out/'SESSION.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifest=json.loads((a.bundle/'manifest.json').read_text());entries={e['mapUid']:e for e in manifest['maps']}
    required=manifest.get('requiredRuntimeSha256')
    if required and hashlib.sha256((a.deployment/'tm2020_generalist_runtime.dll').read_bytes()).hexdigest()!=required:
        raise RuntimeError('This bundle requires the corrected, register-preserving runtime')
    for e in entries.values():check_entry(e)
    telemetry=Telemetry(a.probe.resolve());state={'state':'waiting_for_prepared_map','readyMaps':[e['index'] for e in entries.values()],
        'manualResetKey':'Delete','mapLeaveKey':'Escape','stopFile':str(out/'STOP'),'actualClientFinishVerified':False}
    def stopping():return STOP or (out/'STOP').exists()
    def save_state():
        state['updatedAt']=time.strftime('%Y-%m-%dT%H:%M:%S%z');save_json(out/'status.json',state)
    blocked=None;seen=None;stable=0;last=0.;qualification_attempts={}
    try:
        save_state()
        while not stopping():
            sample=telemetry.current();uid=sample.get('mapUid') if sample.get('valid') and sample.get('state')==2 else None
            if uid and blocked and uid!=blocked:blocked=None
            if uid==seen:stable+=1
            else:seen=uid;stable=0
            if uid in entries and uid!=blocked and stable>=3:
                e=entries[uid];check_entry(e);d=out/f"map-{e['index']:02d}-{time.time_ns()}"
                state.update(state='qualifying_map',mapIndex=e['index'],mapUid=uid,modelSha256=e['modelSha256'],
                    simulatedMs=e['nominalMs'],qualificationDirectory=str(d/'qualification'),workerEvents=[]);save_state()
                state.pop('qualification',None);state.pop('sessionStatus',None);state['observedMapUid']=uid;save_state()
                try:
                    qualification=qualify(telemetry,e,a.deployment.resolve(),d/'qualification',stopping)
                except QualificationUnavailable as error:
                    attempt=qualification_attempts.get(uid,0)+1;qualification_attempts[uid]=attempt
                    state.update(state='waiting_for_qualification_retry',qualificationAttempts=attempt,
                        lastQualificationIssue=str(error),workerEvents=[])
                    if attempt>=3:
                        blocked=uid;state['state']='qualification_failed_on_map'
                    save_state();stable=0;time.sleep(.5);continue
                qualification_attempts.pop(uid,None);state.pop('lastQualificationIssue',None);state.pop('qualificationAttempts',None)
                if stopping():break
                state.update(state='installing_controller',qualification=str(qualification));save_state()
                changed=play(telemetry,e,qualification,a.deployment.resolve(),d/'control',stopping,state,save_state)
                blocked=None if changed else uid
                state.update(state='waiting_for_map_change' if blocked else 'waiting_for_prepared_map');save_state()
            if time.monotonic()-last>1:
                state['observedMapUid']=uid;save_state();last=time.monotonic()
            time.sleep(.25)
    except Exception as e:
        state.update(state='failed',error=str(e));save_state();raise
    finally:
        telemetry.close()
        if state.get('state')!='failed':state.update(state='stopped');save_state()


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
