#!/usr/bin/env python3
"""Owned Windows DLL/detour and cross-platform perception checks, offline.

Uses a separate Wine prefix and an isolated network namespace. Never attaches
to Trackmania and never changes the game's prefix/server.
"""
import json
import csv
import argparse
import threading
import time
import os
from pathlib import Path
import subprocess
import numpy as np
from generalist_engine import GeneralistEngine
from run_fast_ppo import ROOT,steam_packs

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--proc-debug-write',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'local/recon/internal-0.46')
    parser.add_argument('--deployment',type=Path,default=ROOT/'local/recon/deployment-0.46')
    parser.add_argument('--model100',type=Path);parser.add_argument('--weights100',type=Path)
    parser.add_argument('--model-preview',type=Path);parser.add_argument('--weights-preview',type=Path)
    parser.add_argument('--model-hybrid',type=Path)
    parser.add_argument('--repeat-fixture',action='store_true')
    parser.add_argument('--library',type=Path,default=ROOT/'cache/reward-study-target/release/libtm2020_speed.so')
    args=parser.parse_args()
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True);deployment=args.deployment.resolve()
    cfg=json.loads((ROOT/'local/recon/internal-0.46/offline-launch.json').read_text())
    library=args.library
    map_path=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx';packs=steam_packs()
    raws=[];expected=[]
    with GeneralistEngine(library,map_path,packs,horizon=4000) as env:
        env.reset(46601)
        for t in range(256):
            raw=env.raw()
            if args.model_preview:
                raw=(*raw,*np.asarray(env.state.rigid_words,dtype=np.uint32).view(np.float32)[19:22])
                expected.append(env.observe_preview(raw,t==0))
            else:expected.append(env.observe(raw,t==0))
            raws.append(raw)
            if env.state.terminated:env.reset(46601+t)
            env.step_controls([1,0,.15 if t//32%2 else -.15])
    np.asarray(raws,dtype='<f4').tofile(output/'perception-input.f32')
    env=dict(cfg['environment']);env['WINEPREFIX']=str(output/'owned-wine-prefix')
    env['WINEDLLOVERRIDES']='winemenubuilder.exe=d';env['WINEDEBUG']='-all'
    def windows(path):return 'Z:'+str(Path(path).resolve()).replace('/','\\')
    wine=cfg['wine'];server=str(Path(wine).with_name('wineserver'))
    loader=windows(deployment/'tm2020_local_dll_loader.exe');runtime=windows(deployment/'tm2020_generalist_runtime.dll')
    probe=windows(deployment/'tm2020_internal_perception_probe.exe')
    perception=windows(deployment/'tm2020_internal_perception.dll')
    # The same runtime now also runs actual exported policies and in-process
    # Rust perception in its owned hooked consumer (no scripted fixture action).
    parity=ROOT/'local/recon/internal-0.46/export-parity';arms=['continuous','discrete17','discrete33']
    if not all((parity/(arm+'.tmppo')).exists() for arm in arms):raise RuntimeError('Run test_hybrid_export.py first')
    models={arm:parity/(arm+'.tmppo') for arm in arms}
    if args.model100:
        if not args.weights100:raise ValueError('--weights100 required with --model100')
        arms.append('continuous100');models['continuous100']=args.model100.resolve()
    if args.model_preview:
        if not args.weights_preview:raise ValueError('--weights-preview required')
        arms.append('preview');models['preview']=args.model_preview.resolve()
    if args.model_hybrid:arms.append('trajectory');models['trajectory']=args.model_hybrid.resolve()
    fixture=output/'owned-pipeline.args'
    # A failed/aborted child must never borrow traces from an earlier run.
    (output/'owned-windows-final.json').unlink(missing_ok=True)
    for arm in arms:(output/('owned-pipeline-'+arm+'.csv')).unlink(missing_ok=True)
    Path(str(fixture)+'.status').unlink(missing_ok=True)
    fixture.write_text('\n'.join(['TM2020_INTERNAL_FIXTURE_V1',perception,windows(map_path),windows(packs),
        *[value for arm in arms for value in (windows(models[arm]),windows(output/('owned-pipeline-'+arm+'.csv')))]] )+'\n')
    env['TM2020_INTERNAL_FIXTURE_ARGS']=windows(fixture)
    if args.repeat_fixture:env['TM2020_TEST_REPEAT_CYCLE']='1'
    handoff=Path(str(fixture)+'.proc');handoff.unlink(missing_ok=True)
    if args.proc_debug_write:env['TM2020_TEST_PROC_DEBUG']='1'
    # All children share one namespace. Always stop only this private prefix's
    # Wine server so subsequent tests cannot attach across sibling namespaces.
    script='"$1" "$3" --selftest-internal "$4" && "$1" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}"; result=$?; "$2" -k; exit "$result"'
    command=['flatpak','run','--unshare=network','--filesystem='+str(ROOT),'--command=env','com.valvesoftware.Steam',
             *[k+'='+v for k,v in env.items()],'sh','-c',script,'owned-test',wine,server,loader,runtime,probe,perception,
             windows(map_path),windows(packs),windows(output/'perception-input.f32'),windows(output/'perception-windows.f64'),
             windows(output/'perception-max-us.txt')]
    if args.model_preview:
        command[command.index(script)]=script.replace('"${11}"','"${11}" "${12}"')
        command.append('--preview')
    stop=threading.Event();handoff_errors=[]
    def find_owned_child():
        try:
            while not stop.is_set():
                for proc in Path('/proc').iterdir():
                    if not proc.name.isdigit():continue
                    try:
                        argv=(proc/'cmdline').read_bytes().split(b'\0')
                        if b'--fixture-child' not in argv:continue
                        if argv[0].decode(errors='replace').replace('\\','/').rsplit('/',1)[-1].lower()!='tm2020_local_dll_loader.exe':continue
                        prefix=next((v.split(b'=',1)[1].decode() for v in (proc/'environ').read_bytes().split(b'\0') if v.startswith(b'WINEPREFIX=')),None)
                        if prefix!=env['WINEPREFIX']:continue
                        ns=int(next(s.split()[-1] for s in (proc/'status').read_text().splitlines() if s.startswith('NSpid:')))
                        temp=Path(str(handoff)+'.tmp');temp.write_text(f'Z:\\proc\\{ns}\\mem\n');temp.replace(handoff);return
                    except (OSError,StopIteration):continue
                stop.wait(.02)
        except Exception as error:handoff_errors.append(str(error))
    thread=threading.Thread(target=find_owned_child,daemon=True) if args.proc_debug_write else None
    if thread:thread.start()
    try:result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
    finally:
        stop.set()
        if thread:thread.join(timeout=1)
    if handoff_errors:raise RuntimeError(handoff_errors)
    (output/'owned-windows-final.log').write_text(result.stdout);print(result.stdout[-5000:])
    if result.returncode:raise RuntimeError(f'Owned Windows test returned {result.returncode}')
    progress=Path(str(fixture)+'.status').read_text()
    if progress.count('detached_and_dumped')!=len(arms) or not progress.rstrip().endswith('fixture_complete'):
        raise RuntimeError('Incomplete owned fixture; refusing stale/partial pipeline evidence')
    width=72 if args.model_preview else 48
    actual=np.fromfile(output/'perception-windows.f64',dtype='<f8').reshape(-1,width)
    expected=np.asarray(expected);error=float(np.max(np.abs(expected-actual)))
    if actual.shape!=expected.shape or not np.isfinite(actual).all() or error>1e-7:raise RuntimeError(f'Perception parity failed: {error}')
    report={'ownedDetour':True,'perceptionRows':len(actual),'maxObservationError':error,
            'maxPerceptionMicroseconds':float((output/'perception-max-us.txt').read_text()),'gameAccessed':False,'debugWriter':'proc' if args.proc_debug_write else 'win32'}
    from compare_hybrid_ppo import Policy,quantized
    from gpu_ppo import Checkpoint,Helpers
    import torch
    prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',Helpers())
    report['fullInternalPipeline']={}
    for arm in arms:
        period=1 if arm in ('continuous100','trajectory') else 5
        if arm=='trajectory':
            from hybrid_tracking import Hybrid
            controller=Hybrid(args.model_hybrid,1)
            rows=list(csv.DictReader((output/'owned-pipeline-trajectory.csv').open()))
            controlled=[r for r in rows if int(r['wrote']) and int(r['tick_ms'])<1000 and r.get('input_stage','0')=='0']
            if len(controlled)!=100:raise RuntimeError('Wrong hybrid tick count')
            class Fixture:pass
            state=Fixture();env_ref=Fixture();env_ref.states=[state]
            try:
                for row in controlled:
                    rigid=np.array([float(row[k]) for k in ('r00','r01','r02','r10','r11','r12','r20','r21','r22','x','y','z','qw','qx','qy','qz','vx','vy','vz','wx','wy','wz')],dtype=np.float32)
                    state.rigid_words=rigid.view(np.uint32);state.tick=int(row['tick_ms'])//10
                    expected_control=controller.act(env_ref)[0]
                    actual_control=np.array([float(row[k]) for k in ('gas_after','brake_after','steer_after')],dtype=np.float32)
                    if not np.array_equal(expected_control,actual_control):raise RuntimeError('Internal hybrid differs from native simulation controller')
            finally:controller.close()
            report['fullInternalPipeline'][arm]={'decisions':100,'controlledTicks':100,'nativeSimulationControlsBitExact':True,'referenceAssisted':True}
            if args.repeat_fixture:
                second=[r for r in rows if int(r['wrote']) and 2000<=int(r['tick_ms'])<3000]
                if len(second)!=100 or any(int(r['fault'])!=0 for r in second) or 'repeat_reset_passed' not in progress:
                    raise RuntimeError('Repeat reset fixture failed')
                first_controls=[[r[k] for k in ('gas_after','brake_after','steer_after')] for r in controlled]
                second_controls=[[r[k] for k in ('gas_after','brake_after','steer_after')] for r in second]
                if first_controls!=second_controls:raise RuntimeError('Repeat produced different commands on identical physical state')
                report['fullInternalPipeline'][arm]['repeatResetVerified']=True
            continue
        if arm=='preview':
            from preview_ppo import PreviewPolicy
            model=PreviewPolicy(prior,args.weights_preview)
        else:
            model=Policy(prior,'continuous' if period==1 else arm)
            weights=args.weights100 if period==1 else ROOT/f'local/recon/internal-0.46/ppo-comparison/46601-{arm}/best.pt'
            if weights.exists():model.load_state_dict(torch.load(weights,weights_only=True))
        rows=list(csv.DictReader((output/('owned-pipeline-'+arm+'.csv')).open()))
        controlled=[row for row in rows if int(row['wrote']) and int(row['tick_ms'])<1000 and row.get('input_stage','0')=='0']
        expected_ticks=100 if period==1 else 98
        if len(controlled)!=expected_ticks:raise RuntimeError(f'{arm}: wrong bound tick count')
        history=None;previous=[0.,0.,0.]
        with GeneralistEngine(library,map_path,packs,horizon=4000) as reference,torch.no_grad():
            for decision,row in enumerate(controlled[::period]):
                # Fixture body is intentionally static, with identity R and
                # gear 0. This tests plumbing and decoding, never game physics.
                raw=[float(row[k]) for k in ('x','y','z')]+[1,0,0,0,1,0,0,0,1]+[0,0,0]+previous+[0,0,0]
                x=np.asarray(reference.observe_preview(raw+[0.,0.,0.],decision==0) if arm=='preview' else reference.observe(raw,decision==0));x[13:15]=0
                history=np.tile(x,5) if history is None else np.r_[history[len(x):],x]
                expected_control=quantized(model.action(torch.tensor(history[None,:],device='cuda'),True)[0].cpu().numpy())[0]
                consumer=np.array([float(row[k]) for k in ('gas_after','brake_after','steer_after')],dtype=np.float32)
                if not np.array_equal(consumer,expected_control):raise RuntimeError(f'{arm} internal pipeline decision {decision} differs')
                previous=expected_control.tolist()
        report['fullInternalPipeline'][arm]={'decisions':100//period,'controlledTicks':expected_ticks,'consumerControlsBitExactToCuda':True}
    (output/'owned-windows-final.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
