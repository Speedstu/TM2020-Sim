#!/usr/bin/env python3
"""Observe, qualify, reset and run one internal PPO trial in the current map.

Only reset/menu input uses XTest. Every driving action uses the DLL's physical
consumer. Client result screenshots/replays remain separate finish evidence.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import csv
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',type=Path,default=ROOT/'local/recon/deployment-0.46/candidate.tmppo')
    p.add_argument('--deployment',type=Path,default=ROOT/'local/recon/deployment-0.46')
    p.add_argument('--map',type=Path,default=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
    p.add_argument('--map-uid',default='ypPmohQofd72MyTsIsijKfrJH98')
    p.add_argument('--spawn',type=float,nargs=3,default=(1200,34.0015,1360))
    p.add_argument('--seconds',type=float,default=36);p.add_argument('--local-solo',action='store_true')
    p.add_argument('--proc-debug-write',action='store_true');p.add_argument('--input-recording',action='store_true');p.add_argument('--capture',action='store_true');a=p.parse_args()
    a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False)
    flags=(['--local-solo'] if a.local_solo else [])+(['--proc-debug-write'] if a.proc_debug_write else [])+(['--input-recording'] if a.input_recording else [])
    def phase(mode,seconds,qualification=None):
        out=a.output/mode;log_path=a.output/(mode+'.log')
        command=[sys.executable,str(ROOT/'scripts/run_internal_live.py'),*flags,'--deployment',str(a.deployment),'--mode',mode,'--seconds',str(seconds),'--output',str(out),
            '--map',str(a.map),'--map-uid',a.map_uid,'--spawn',*map(str,a.spawn)]
        if qualification:command+=['--model',str(a.model),'--qualification',str(qualification)]
        pre_reset_at=None
        if mode=='observe':
            from play_internal_campaign import reset_local_map
            reset_local_map();pre_reset_at=time.monotonic()
        with log_path.open('w') as log:
            process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+seconds+90;reset_at=pre_reset_at;last=-1;stop=None
            while process.poll() is None:
                report_path=out/'report.json'
                try:report=json.loads(report_path.read_text())
                except (OSError,json.JSONDecodeError):report=None
                if report:
                    stop=Path(report['stopFile']);status=Path(str(stop)[:-5]+'.status')
                    text=status.read_text() if status.exists() else ''
                    if reset_at is None and 'INTERNAL_INSTALLED' in text:
                        from local_game_ui import focus_trackmania
                        active=focus_trackmania()
                        cx=active['at'][0]+active['size'][0]//2;cy=active['at'][1]+active['size'][1]//2
                        subprocess.run(['hyprctl','dispatch','movecursor',f'{cx} {cy}'],check=True,stdout=subprocess.DEVNULL)
                        time.sleep(.2);subprocess.run([sys.executable,str(ROOT/'scripts/local_game_ui.py'),'--key','Delete'],check=True)
                        reset_at=time.monotonic();print(mode+': installed; race reset',flush=True)
                    if a.capture and mode=='control' and reset_at is not None:
                        elapsed=time.monotonic()-reset_at;index=int(elapsed//2)
                        if index!=last:
                            active=json.loads(subprocess.check_output(['hyprctl','activewindow','-j'],text=True))
                            from local_game_ui import is_trackmania_window
                            if is_trackmania_window(active):
                                frames=out/'frames';frames.mkdir(exist_ok=True);target=frames/f'{index:03d}.png'
                                x,y=active['at'];width,height=active['size']
                                subprocess.run(['grim','-g',f'{x},{y} {width}x{height}',str(target)],check=True)
                                after=json.loads(subprocess.check_output(['hyprctl','activewindow','-j'],text=True))
                                if not is_trackmania_window(after):target.unlink(missing_ok=True)
                                else:
                                    with (frames/'times.jsonl').open('a') as f:f.write(json.dumps({'file':f'{index:03d}.png','secondsAfterReset':elapsed})+'\n')
                            last=index
                if time.monotonic()>deadline:
                    if stop:stop.touch()
                    raise RuntimeError('Trial deadline exceeded; requested neutral stop, game was not terminated')
                time.sleep(.05)
            if process.returncode:raise RuntimeError(log_path.read_text()[-1800:])
        result=json.loads((out/'report.json').read_text())
        if not result['workerReturnedNormally']:raise RuntimeError('Worker did not detach normally: '+str(out))
        return result,out
    observation,folder=phase('observe',6)
    if not observation['physicalConsumerQualified']:raise RuntimeError('Observation did not qualify this physical owner')
    control,folder=phase('control',a.seconds,folder/'report.json')
    rows=list(csv.DictReader((folder/'physics.csv').open()));driving=[r for r in rows if int(r['wrote']) and r.get('input_stage','0')=='0']
    unexpected=Counter(r['fault'] for r in driving if r['fault'] not in ('0','6'))
    exact=all(all(float(r[a])==float(r[b]) for a,b in [('gas','gas_after'),('brake','brake_after'),('steer','steer_after')]) for r in driving)
    result={'observation':str(a.output/'observe/report.json'),'control':str(folder/'report.json'),
            'internalControlTicks':len(driving),'consumerReadbackExact':exact,'unexpectedFaults':dict(unexpected),
            'workerDetachedNormally':True,'raceFinishVerified':False,
            'finishEvidenceRequired':'Client result screenshot/replay; never infer a finish from hook return or displacement'}
    result.update(inputRecordingRequested=a.input_recording,inputRecordTicks=control.get('inputRecordTicks',0),
        inputRecordReadbackExact=control.get('inputRecordReadbackExact',False),ordinaryReplayInputsVerified=False,
        causalConsumerVerifiedTicks=control.get('causalConsumerVerifiedTicks',0),nonNeutralPhysicalWrites=control.get('nonNeutralPhysicalWrites',0))
    (a.output/'trial.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not driving or unexpected or not exact or (a.input_recording and (not result['inputRecordReadbackExact'] or result['causalConsumerVerifiedTicks']<100 or result['nonNeutralPhysicalWrites'])):raise SystemExit(1)

if __name__=='__main__':main()
