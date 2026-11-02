#!/usr/bin/env python3
"""Explicit offline tick-synchronous deployment. No peripheral fallback.

First run --mode observe and inspect the physical consumer trace. A control run
requires a successful observation report from this exact process and map.
Finishing is never inferred from displacement or simulator geometry.
"""
import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
from proton_sdk import runtime,copy_immutable
from run_fast_ppo import ROOT,steam_packs

UID='ypPmohQofd72MyTsIsijKfrJH98'
BUILD_SHA='3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda'

def check_observed_assets(qualification,dll_sha,map_sha,spawn,input_recording=False):
    if not qualification.get('workerReturnedNormally') or qualification.get('dllSha256')!=dll_sha:
        raise RuntimeError('Repeat observation with this exact runtime; hook stage/build changed')
    if qualification.get('mapSha256')!=map_sha or list(qualification.get('spawn',[]))!=list(spawn):
        raise RuntimeError('Observed map content or spawn differs from this control run')
    if bool(qualification.get('inputRecordingRequested',False))!=input_recording:
        raise RuntimeError('Repeat observation with the same internal input/history mode')

def offline_proof(pid,local_solo=False):
    proc=Path('/proc')/str(pid);namespace=os.readlink(proc/'ns/net')
    isolated=namespace!=os.readlink('/proc/self/ns/net')
    routes=(proc/'net/route').read_text();ipv6=(proc/'net/ipv6_route').read_text()
    has_routes=any(line.split()[0]!='lo' for line in routes.splitlines()[1:] if line.split()) or any(line.split()[-1]!='lo' for line in ipv6.splitlines() if line.split())
    if not local_solo and (not isolated or has_routes):raise RuntimeError('Networked client needs explicit --local-solo for a user-confirmed local race')
    return {'hostPid':pid,'processStartTicks':(proc/'stat').read_text().rsplit(')',1)[1].split()[19],
            'netNamespace':namespace,'ipv4Routes':routes,'ipv6Routes':ipv6,'isolatedFromHost':isolated and not has_routes,
            'localSoloDeclaredByUser':local_solo}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['observe','control'],default='observe')
    p.add_argument('--seconds',type=float,default=8);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--local-solo',action='store_true',help='Explicit local Solo trial in the current logged-in client, even with network access')
    p.add_argument('--debug-write',action='store_true',help='Explicitly authorized test build: use the Windows debugger write API for the detour')
    p.add_argument('--proc-debug-write',action='store_true',help='Explicitly authorized Proton test: debugger memory file for the exact pinned detour only')
    p.add_argument('--repeat-resets',action='store_true',help='Keep the bounded hybrid worker armed for qualified manual restarts')
    p.add_argument('--input-recording',action='store_true',help='Experimental upstream internal input records plus physical consumer verification')
    p.add_argument('--model',type=Path);p.add_argument('--qualification',type=Path)
    p.add_argument('--map',type=Path,default=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
    p.add_argument('--map-uid',default=UID);p.add_argument('--packs',type=Path)
    p.add_argument('--spawn',type=float,nargs=3,default=(1200,34.0015,1360),metavar=('X','Y','Z'))
    p.add_argument('--deployment',type=Path,default=ROOT/'local/recon/deployment-0.46');a=p.parse_args()
    if not 0<a.seconds<=120:p.error('seconds must be in (0,120]')
    if a.debug_write and not a.local_solo:p.error('--debug-write requires the explicitly authorized --local-solo test')
    if a.proc_debug_write and (not a.local_solo or a.debug_write):p.error('--proc-debug-write requires --local-solo and cannot combine with --debug-write')
    if a.repeat_resets and (not a.proc_debug_write or a.mode!='control'):p.error('--repeat-resets needs explicit local proc control mode')
    if a.input_recording and (not a.proc_debug_write or a.repeat_resets):p.error('--input-recording needs local proc mode without repeat resets')
    build=a.deployment/'build.json'
    if build.exists() and json.loads(build.read_text()).get('rejectedForDeployment'):
        raise RuntimeError('This experimental runtime was rejected; select the qualified replacement build')
    if a.input_recording and (not build.exists() or not json.loads(build.read_text()).get('causalInputDecodeOnlyOwnedVerified')):
        raise RuntimeError('Normal-input mode requires an owned-verified decoder-only runtime; legacy physical overwrite prototypes are refused')
    pid,stage,command=runtime();proof=offline_proof(pid,a.local_solo)
    binding={}
    if a.mode=='control':
        if not a.model or not a.qualification:p.error('control needs --model and a successful --qualification report')
        qualification=json.loads(a.qualification.read_text())
        if not qualification.get('physicalConsumerQualified') or qualification.get('mapUid')!=a.map_uid or qualification.get('offlineProof',{}).get('processStartTicks')!=proof['processStartTicks'] or qualification.get('hostPid')!=pid:
            raise RuntimeError('No qualified physical trace for this exact client process and map')
        binding=qualification.get('binding',{})
        if not all(isinstance(binding.get(k),int) and binding[k]>0 for k in ('manager','vehicle','body')):raise RuntimeError('Qualification has no exact physical binding')
        if a.proc_debug_write and not isinstance(binding.get('raceStartMs'),int):raise RuntimeError('Repeat observation to qualify the reset timestamp')
    a.output.mkdir(parents=True,exist_ok=False)
    def staged(path):
        path=Path(path).resolve(strict=True);digest=hashlib.sha256(path.read_bytes()).hexdigest()
        dest=stage/(path.stem+'-'+digest[:20]+path.suffix)
        copy_immutable(path,dest)
        return 'C:\\tm2020-sdk\\'+dest.name,digest
    dll,dll_sha=staged(a.deployment/'tm2020_generalist_runtime.dll')
    loader,_=staged(a.deployment/'tm2020_local_dll_loader.exe')
    model,model_sha=staged(a.model) if a.model else ('',None)
    perception,_=staged(a.deployment/'tm2020_internal_perception.dll')
    map_file,map_sha=staged(a.map)
    if a.mode=='control':check_observed_assets(qualification,dll_sha,map_sha,a.spawn,a.input_recording)
    win=lambda path:'Z:'+str(Path(path).resolve(strict=True)).replace('/','\\')
    stem='internal-'+str(time.time_ns());config=stage/(stem+'.args');trace=stage/(stem+'.csv')
    tag='TM2020_INTERNAL_RUNTIME_V6_LOCAL_PROC_REPEAT' if a.repeat_resets else ('TM2020_INTERNAL_RUNTIME_V5_LOCAL_PROC_RESET' if a.proc_debug_write else ('TM2020_INTERNAL_RUNTIME_V3_LOCAL_DEBUG_WRITE' if a.debug_write else ('TM2020_INTERNAL_RUNTIME_V2_LOCAL_SOLO' if a.local_solo else 'TM2020_INTERNAL_RUNTIME_V1')))
    if a.input_recording:tag='TM2020_INTERNAL_RUNTIME_V7_LOCAL_PROC_INPUT'
    inner_pid=int(next(s.split()[-1] for s in Path(f'/proc/{pid}/status').read_text().splitlines() if s.startswith('NSpid:')))
    config.write_text('\n'.join([tag,a.mode,str(a.seconds),'C:\\tm2020-sdk\\'+trace.name,a.map_uid,
                                model,perception,map_file,win(a.packs or steam_packs()),' '.join(map(str,a.spawn)),
                                ' '.join(str(binding.get(k,0)) for k in ('manager','vehicle','body'))+(' '+str(binding.get('raceStartMs',0)) if a.proc_debug_write else ''),
                                f'Z:\\proc\\{inner_pid}\\mem' if a.proc_debug_write else ''])+'\n')
    report={'hostPid':pid,'offlineProof':proof,'mode':a.mode,'mapUid':a.map_uid,'spawn':a.spawn,'repeatManualResets':a.repeat_resets,'inputRecordingRequested':a.input_recording,'mapSha256':map_sha,'dllSha256':dll_sha,'modelSha256':model_sha,
            'stopFile':str(config)+'.STOP','physicalConsumerQualified':False,'raceFinishVerified':False,'explicitDebugWriteAuthorized':a.debug_write or a.proc_debug_write,'debugWriter':'proc' if a.proc_debug_write else ('win32' if a.debug_write else None)}
    report.update(deviceInputHistoryMode='normal' if a.input_recording else 'device input history unchanged',
        ordinaryReplayInputsVerified=False,startedUnixNs=time.time_ns())
    save=lambda:(a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save();print('INTERNAL_READY '+json.dumps(report),flush=True)
    # The loader and runtime independently reject networked/unsupported clients.
    result=subprocess.run(command+[loader,'--run-confirmed-local-game' if a.local_solo else '--run-local-game',dll,'C:\\tm2020-sdk\\'+config.name],
                          capture_output=True,text=True,timeout=160)
    (a.output/'loader.log').write_text(result.stdout+result.stderr)
    status=Path(str(config)+'.status');lines=status.read_text().splitlines() if status.exists() else []
    report['workerStatus']=lines;report['workerReturnedNormally']=result.returncode==0 and bool(lines) and lines[-1].startswith('RETURNED ')
    if status.exists():shutil.copy2(status,a.output/'worker.status')
    if trace.exists():
        shutil.copy2(trace,a.output/'physics.csv');rows=list(csv.DictReader(trace.open()))
        owners={r['vehicle'] for r in rows};qualified=[];bindings={}
        nearby={r['vehicle'] for r in rows if int(r['valid_state']) and int(r['valid_map']) and
                sum((float(r[k])-s)**2 for k,s in zip(('x','y','z'),a.spawn))<2.25 and 0<=int(r['tick_ms'])-int(r['race_start_ms'])<3000}
        for owner in owners:
            r=[v for v in rows if v['vehicle']==owner and int(v['bound_owner'])]
            ticks=[int(v['tick_ms']) for v in r]
            close=[v for v in r if sum((float(v[k])-s)**2 for k,s in zip(('x','y','z'),a.spawn))<2.25]
            deltas=[b-a for a,b in zip(ticks,ticks[1:])]
            if len(set(ticks))>=100 and close and deltas and all(d in (0,10) for d in deltas) and all(0<float(v['interval'])<=.010001 and int(v['valid_state']) and int(v['valid_map']) for v in r) and len({(v['manager'],v['body'],v['race_start_ms']) for v in r})==1:
                qualified.append(owner);bindings[owner]={k:int(r[0][k]) for k in ('manager','vehicle','body')};bindings[owner]['raceStartMs']=int(r[0]['race_start_ms'])
        bound=re.search(r'\bbound=(\d+)',lines[-1] if lines else '')
        bound=str(int(bound[1])) if bound else None
        report.update({'rows':len(rows),'candidateOwners':qualified,'nearStartOwners':sorted(nearby),'boundOwner':bound,'binding':bindings.get(bound),
                       'physicalConsumerQualified':a.mode=='observe' and report['workerReturnedNormally'] and len(qualified)==1 and qualified[0]==bound and nearby=={bound},
                       'directControlTicks':sum(int(r['wrote']) for r in rows)})
        input_rows=[r for r in rows if int(r['wrote']) and r.get('input_stage')=='1']
        report.update(inputRecordTicks=len(input_rows),
            inputRecordReadbackExact=bool(input_rows) and all(all(float(r[k])==float(r['record_'+k]) for k in ('gas','brake','steer')) for r in input_rows),
            physicalConsumerControlTicks=sum(int(r['wrote']) and r.get('input_stage','0')=='0' for r in rows))
        report.update(causalConsumerVerifiedTicks=sum(r.get('consumer_verified')=='1' for r in rows),
            nonNeutralPhysicalWrites=sum(r.get('physical_write')=='1' and any(float(r[k])!=0 for k in ('gas','brake','steer')) for r in rows))
    save();print(json.dumps(report,indent=2))
    if not report['workerReturnedNormally']:raise SystemExit(1)

if __name__=='__main__':main()
