#!/usr/bin/env python3
"""Finite, plateau-stopped assisted full-lap optimization in the native simulator.

Public reference reproduction is never counted as a controller result. All
qualification runs start at race zero without teacher forcing or state resets.
"""
import argparse
import fcntl
import hashlib
import json
import signal
import subprocess
import time
from pathlib import Path
import numpy as np
from hybrid_tracking import save_asset,load_asset,retime_pedals
from run_fast_ppo import ROOT,steam_packs
from tune_hybrid_tracking import NativeEvaluator
from prepare_fall_campaign import OUT,save_json
from campaign_targets import set_goal,milestone,cached_goal_passed

API=ROOT/'native/build-campaign/libtm2020_vector_physics.so'
EXPORT=ROOT/'cache/reward-study-target/release/tm2020-reference-export'
STOP=False


def stop(*_):
    global STOP
    STOP=True


def summary(rows,target):
    times=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    return {'finishes':len(times),'count':len(rows),'targetFinishes':sum(t<=target for t in times),
        'bestMs':min(times) if times else None,'meanMs':float(np.mean(times)) if times else None,
        'medianMs':float(np.median(times)) if times else None,'worstMs':max(times) if times else None,
        'trials':rows,'referenceAssisted':True,'measuredInGame':False}


def trial_cases(seed,count,length,perturbed=False):
    rng=np.random.default_rng(seed)
    return [{'seed':int(rng.integers(1,2**32-1)),
        'warm':int(rng.integers(50,max(51,length-50))),
        'duration':int(rng.integers(1,8)),
        'kick':float(rng.choice([-1,1])*rng.uniform(.02,.08)) if perturbed else 0.}
        for _ in range(count)]


def deform(ref,p,width=.045):
    """Smooth whole-track lateral target and feedforward changes, in metres/radians."""
    r=ref.copy();t=np.arange(len(ref))/max(1,len(ref)-1)
    centers=np.linspace(.05,.95,16);basis=np.exp(-.5*((t[:,None]-centers)/width)**2)
    # Preserve the exact spawn and countdown. Feedback is otherwise free to
    # discover a faster line; no fixed target lap time appears in the reward.
    basis*=np.clip(t[:,None]/.025,0,1)
    offset=basis@p[:16];steer=basis@p[16:32]
    r[:,9:12]+=offset[:,None]*ref[:,[0,3,6]]
    s=np.clip(r[:,24]+steer,-1,1)
    r[:,24]=np.sign(s)*np.floor(np.abs(s)*127+.5)/127
    return r


def deform_local(ref,p,window):
    """Compact kernels preserve the earlier successful prefix exactly."""
    lo=max(20,int(window[0]));hi=min(len(ref)-1,int(window[1]))
    if hi<=lo:raise ValueError('Empty local search window')
    radius=max(1.,(hi-lo)/6.);centers=np.linspace(lo+radius,hi-radius,16)
    z=(np.arange(len(ref))[:,None]-centers)/radius
    basis=np.maximum(0.,1.-z*z)**3
    mask=np.any(basis>0.,axis=1);r=ref.copy()
    r[mask,9:12]+=(basis@p[:16])[mask,None]*ref[mask][:,[0,3,6]]
    steer=np.clip(r[:,24]+basis@p[16:32],-1.,1.)
    r[mask,24]=(np.sign(steer)*np.floor(np.abs(steer)*127+.5)/127)[mask]
    return r


def update_search_spread(elite,minimum,initial,generation):
    # Generation zero is a deterministic baseline/pedal grid. Its identical
    # geometry coordinates contain no evidence that steering variance should
    # collapse. Actually sample the declared initial distribution first.
    floor=initial if generation==0 else minimum
    return np.maximum(elite.std(0),floor)


def export(m,d):
    path=d/'reference.f32';meta=d/'reference.json'
    if not(path.exists() and meta.exists()):
        if path.exists():path.unlink()  # Only an uncommitted interrupted export.
        r=subprocess.run([str(EXPORT),m['map'],str(steam_packs()),m['referenceGhost'],str(path)],
            capture_output=True,text=True,timeout=180)
        (d/'reference-export.log').write_text(r.stderr)
        if r.returncode:raise RuntimeError(r.stderr[-1800:])
        metadata=json.loads(r.stdout);save_json(meta,metadata)
    metadata=json.loads(meta.read_text())
    if metadata['mapUid']!=m['mapUid'] or metadata['finishMs']!=m['referenceMs']:
        raise ValueError('Reference identity/time differs')
    ref=np.fromfile(path,dtype='<f4').reshape(-1,25)
    if len(ref)!=metadata['rows'] or not np.isfinite(ref).all():raise ValueError('Invalid reference array')
    return ref,metadata


def optimize(m,out,generations,plateau,initial_asset=None,*,api=API,library=None,internal_controls=False,
             seed_offset=0,line_width=.045,spread_scale=1.,fast_evaluation=False,launch_randomization=False,transfer_priority=False,
             local_window=None,pedal_timing=False):
    d=out/f"{m['index']:02d}";ref,metadata=export(m,d)
    target=m['targetMs'];horizon=min(10000,len(ref)+1000);seed=52000+m['index']*100
    p=np.zeros(40 if pedal_timing else 37);g=np.array([-.035,-.029,.65,-.30,.008,0.])
    if m['index']==1:
        ref,g,_=load_asset(ROOT/'local/training/hybrid-20261031/robust-candidate.tmhyb')
        prior=ROOT/'local/training/hybrid-20261031/pursuit/best.tmhyb'
        if prior.exists():ref,g,_=load_asset(prior)
    if initial_asset:ref,g,_=load_asset(initial_asset,map_path=m['map'],uid=m['mapUid'])
    elif (d/'warm-start.tmhyb').exists():ref,g,_=load_asset(d/'warm-start.tmhyb',map_path=m['map'],uid=m['mapUid'])
    p[32:36]=g[:4];p[36]=np.log10(max(1e-5,g[4]))
    asset=d/'initial.tmhyb'
    def parameters_gains(params):return [*params[32:36],10.**params[36],0.]
    def write(path,params):
        r=deform_local(ref,params,local_window) if local_window is not None else deform(ref,params,line_width)
        if pedal_timing:
            lo,hi=local_window if local_window is not None else (20,len(ref))
            r=retime_pedals(r,int(np.rint(params[37])),int(np.rint(params[38])),lo,hi,int(np.rint(params[39])))
        save_asset(path,r,parameters_gains(params),map_path=m['map'],uid=m['mapUid'])
    write(asset,p)
    save_json(d/'protocol.json',{'schema':'tm2020_campaign_search_v1','map':m,
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'nativeApiSha256':hashlib.sha256(api.read_bytes()).hexdigest(),
        'physicsSha256':hashlib.sha256((library or ROOT/'cache/reward-study-target/release/libtm2020_speed.so').read_bytes()).hexdigest(),
        'internalPhysicalControls':internal_controls,'deviceInputHistoryFrozen':internal_controls,
        'fastWholeRaceEvaluation':fast_evaluation,
        'launchRandomization':launch_randomization,
        'transferPriority':transfer_priority,
        'localWindow':local_window,'pedalTimingSearch':pedal_timing,
        'initialLateralSigmaM':(.5 if local_window is not None else .12)*spread_scale,
        'initialSteeringSigma':(.08 if local_window is not None else .008)*spread_scale,
        'preserveExplorationAfterBaselineGrid':True,
        'initialAssetSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
        'population':16,'developmentCases':4,'nominalHoldout':64,'perturbedHoldout':64,
        'maxGenerations':generations,'plateauGenerations':plateau,'horizon':horizon,
        'seed':seed,'objective':'finish reliability then minimum measured time; no target time reward',
        'candidateSeed':seed+seed_offset,'lineWidth':line_width,'spreadScale':spread_scale,
        'gameAccessed':False,'onlineWrites':False})
    extra={'library':library} if library else {}
    ev=NativeEvaluator(64,asset,api_path=api,map_path=m['map'],horizon=horizon,internal_controls=internal_controls,fast_evaluation=fast_evaluation,**extra)
    rng=np.random.default_rng(seed+seed_offset);dev=trial_cases(seed+1,4,len(ref),False)
    # Fixed common random numbers for fair comparison, plus an independent
    # nominal/perturbed holdout after search. Holdouts do not choose winners.
    dev[0]['seed']=metadata['seed'] or dev[0]['seed']
    if internal_controls:
        # Frozen device history deliberately removes seed-triggered input
        # perturbations. Use actual control disturbances for distinct cases.
        dev[1].update(warm=5,duration=2,kick=.02)
        dev[2].update(duration=2,kick=-.02)
        dev[3].update(warm=15,duration=2,kick=-.02)
    if launch_randomization:
        for c,delta in zip(dev,(-.01,0.,-.02,.01)):c['launchDeltaMps']=delta
        # The nominal development case matches the measured launch bias;
        # other cases explicitly retain the unperturbed simulator as well.
        dev[0]['kick']=0.
    save_json(d/'development-cases.json',dev)
    minimum=np.array(([.08]*16+[.01]*16 if local_window is not None else [.025]*16+[.002]*16)+
        [.001,.001,.015,.005,.03]+([1.5,1.5,1.5] if pedal_timing else []))
    initial_spread=np.array(([.5]*16+[.08]*16 if local_window is not None else [.12]*16+[.008]*16)+
        [.004,.004,.06,.025,.2]+([6.,6.,6.] if pedal_timing else []))*spread_scale
    best=None;mean=p.copy();spread=initial_spread.copy();stale=0
    section_passed=False
    started=time.monotonic();history=d/'search.jsonl';generation=-1
    try:
        for generation in range(generations+1):
            if STOP:break
            generation_started=time.monotonic()
            population=mean+rng.normal(size=(16,len(p)))*spread
            population[:,:16]=np.clip(population[:,:16],-2,2)
            population[:,16:32]=np.clip(population[:,16:32],-.20,.20)
            population[:,32:36]=np.clip(population[:,32:36],[-.5,-.5,-4,-2],[.5,.5,4,2])
            population[:,36]=np.clip(population[:,36],-5,2)
            if pedal_timing:population[:,37:40]=np.clip(population[:,37:40],-15,15)
            if local_window is not None:population[:,32:37]=p[32:37]
            population[0]=p if best is None else best['parameters']
            if generation==0:
                if local_window is None and not pedal_timing:population[:]=p
                if pedal_timing:
                    offsets=[(0,0,-2),(0,0,-1),(0,0,1),(0,0,2),(-1,0,0),(1,0,0),(-2,0,0),(2,0,0),(0,-1,0),(0,1,0),(-1,0,1),(1,0,-1),(0,0,-4),(0,0,4),(0,0,0)]
                    population[:]=p
                    for k,pedals in enumerate(offsets,1):population[k,37:40]=pedals
                elif m['index']!=1 and local_window is None:
                    # Test several stable controllers and time-indexed replay
                    # as baselines instead of assuming Fall 01's gains transfer.
                    for i in range(16):
                        population[i,32:36]=[0,0,0,0] if i%4==0 else np.array([-.035,-.029,.65,-.30])*(.15,.5,1.,1.5)[i%4]
                        population[i,36]=[-4,-2,-.5,2][i//4]
                    population[-1]=p # Always evaluate the retained incumbent unchanged.
            assets=[]
            for i,params in enumerate(population):
                path=d/f'candidate-{i}.tmhyb';write(path,params);assets.extend([path]*4)
            preparation_seconds=time.monotonic()-generation_started
            gains=np.repeat(np.asarray([parameters_gains(v) for v in population]),4,axis=0)
            rows,seconds=ev.evaluate(gains,dev*16,assets=assets)
            ranked=[];improved=False
            for i,params in enumerate(population):
                trials=rows[i*4:(i+1)*4];s=summary(trials,target)
                penalty=float(np.mean([r['finishMs'] if r['finishMs'] is not None else horizon*10 for r in trials]))
                # Millisecond finish stamps flatten the objective near a WR.
                # Break equal-time ties by continuous forward phase at the
                # terminal tick. The anchor is fixed across all candidates;
                # never publish this proxy as an official measured lap time.
                velocity=ref[-1,16:19].astype(np.float64);speed2=float(velocity@velocity)
                sub_tick=[]
                for r in trials:
                    if r['finishMs'] is not None and r.get('finalPosition') is not None and speed2>1:
                        phase=float((np.asarray(r['finalPosition'])-ref[-1,9:12])@velocity)/speed2*1000
                        sub_tick.append(r['tick']*10-phase)
                    else:sub_tick.append(horizon*10)
                phase_cost=float(np.mean(sub_tick))
                # Finish reliability first, then unrestricted minimum lap time.
                score=(s['finishes'],-penalty,-phase_cost,sum(r['checkpoints'] for r in trials),
                    sum(r.get('maximumReferenceIndex',0) for r in trials))
                if transfer_priority:
                    nominal=trials[0]
                    score=(int(nominal['finishMs'] is not None),nominal['checkpoints'],
                        -nominal['finishMs'] if nominal['finishMs'] is not None else nominal.get('maximumReferenceIndex',0),
                        s['finishes'],-penalty,-phase_cost)
                ranked.append((score,i))
                if best is None or score>tuple(best['score']):
                    best={'generation':generation,'parameters':params.tolist(),'gains':parameters_gains(params),
                        'score':score,'development':s};improved=True
                    write(d/'best.tmhyb',params);save_json(d/'best.json',best)
            stale=0 if improved else stale+1
            ranked.sort(reverse=True);elite=population[[i for _,i in ranked[:4]]]
            mean=elite.mean(0)
            spread=update_search_spread(elite,minimum,initial_spread,generation)
            state={'generation':generation,'stale':stale,'seconds':seconds,'wallSeconds':time.monotonic()-started,
                'best':{k:v for k,v in best.items() if k not in ('parameters','development')},
                'bestDevelopment':{k:v for k,v in best['development'].items() if k!='trials'},
                'simulatorOnly':True,'state':'optimizing','targetMs':target,'mapIndex':m['index']}
            state.update(milestone(best['development'],m))
            state.update(targetRank=m.get('targetRank'),top10TargetMs=m.get('top10TargetMs'),worldBestMs=m.get('worldBestMs'))
            total_seconds=time.monotonic()-generation_started
            ticks=sum(r['tick'] for r in rows)
            state.update(preparationSeconds=preparation_seconds,generationSeconds=total_seconds,
                simulatedTicks=ticks,nativeStepsPerSecond=ticks/seconds if seconds else None,
                generationStepsPerSecond=ticks/total_seconds if total_seconds else None,
                fastWholeRaceEvaluation=fast_evaluation)
            save_json(d/'status.json',state)
            with history.open('a') as f:f.write(json.dumps(state)+'\n')
            if generation%8==0:print(json.dumps(state),flush=True)
            if best['development']['targetFinishes']==4:
                break
            if local_window is not None:
                nominal=best['development']['trials'][0]
                section_passed=nominal['finishMs'] is None and nominal.get('maximumReferenceIndex',0)>local_window[1]+100
                if section_passed:break
            if stale>=plateau:break
        ev.asset=d/'best.tmhyb'
        result={'map':m,'referenceReproduction':metadata,'generation':generation,
            'stopReason':'signal' if STOP else ('target_on_development' if best['development']['targetFinishes']==4 else (
                'local_section_passed' if section_passed else ('plateau' if stale>=plateau else 'budget'))),
            'model':str(d/'best.tmhyb'),'modelSha256':hashlib.sha256((d/'best.tmhyb').read_bytes()).hexdigest(),
            'assisted':True,'gameVerified':False,'development':best['development']}
        for name,perturbed in [('nominal64',False),('perturbed64',True)]:
            cases=trial_cases(seed+(91 if perturbed else 90),64,len(ref),perturbed)
            if launch_randomization:
                noise=np.random.default_rng(seed+(191 if perturbed else 190))
                for c in cases:c['launchDeltaMps']=float(noise.uniform(-.03,.01)) if perturbed else -.01
            rows,seconds=ev.evaluate(best['gains'],cases)
            report=summary(rows,target);report['seconds']=seconds
            report['internalPhysicalControls']=internal_controls
            report['launchRandomization']=launch_randomization
            if launch_randomization:report['nominalLaunchDeltaMps']=-.01
            if internal_controls and not perturbed:
                report['effectiveDistinctNominalConditions']=1
                report['seedAloneChangesNoDeviceInputHistory']=True
            save_json(d/(name+'.json'),report);result[name]={k:v for k,v in report.items() if k!='trials'}
        result['simGoalPassed']=result['nominal64']['targetFinishes']==64
        result['robustSimGoalPassed']=result['simGoalPassed'] and result['perturbed64']['targetFinishes']==64
        save_json(d/'result.json',result)
        save_json(d/'status.json',dict(state,state='stopped',stopReason=result['stopReason'],simGoalPassed=result['simGoalPassed']))
        print(json.dumps({'mapIndex':m['index'],'result':{k:v for k,v in result.items() if k in ('simGoalPassed','nominal64','perturbed64','stopReason')}}),flush=True)
        return result
    finally:ev.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=OUT)
    p.add_argument('--maps',type=int,nargs='+',default=list(range(1,26)))
    p.add_argument('--generations',type=int,default=128);p.add_argument('--plateau',type=int,default=32)
    p.add_argument('--initial-asset',type=Path)
    p.add_argument('--wait-lock',action='store_true')
    p.add_argument('--api',type=Path,default=API);p.add_argument('--physics',type=Path)
    p.add_argument('--internal-controls',action='store_true');p.add_argument('--lock-name',default='OPTIMIZE')
    p.add_argument('--target-rank',type=int,choices=(1,10))
    p.add_argument('--seed-offset',type=int,default=0);p.add_argument('--line-width',type=float,default=.045)
    p.add_argument('--spread-scale',type=float,default=1.)
    p.add_argument('--fast-evaluation',action='store_true')
    p.add_argument('--launch-randomization',action='store_true')
    p.add_argument('--transfer-priority','--nominal-priority',dest='transfer_priority',action='store_true')
    p.add_argument('--local-window',type=int,nargs=2)
    p.add_argument('--pedal-timing',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if not .005<=a.line_width<=.2 or not .1<=a.spread_scale<=4:p.error('Invalid search width/spread')
    if not a.lock_name.replace('-','').isalnum():p.error('Invalid lock name')
    lock=(a.output/(a.lock_name+'.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|(0 if a.wait_lock else fcntl.LOCK_NB))
    result_path=a.output/(f'results-{a.lock_name}.json' if a.lock_name!='OPTIMIZE' else 'results.json')
    results=[];errors=[]
    for index in a.maps:
        if STOP:break
        path=a.output/f'{index:02d}'
        try:
            m=json.loads((path/'map.json').read_text())
            if a.target_rank:m=set_goal(m,json.loads((path/'leaderboard.json').read_text()),a.target_rank)
            initial=a.initial_asset
            if (path/'result.json').exists():
                previous=json.loads((path/'result.json').read_text())
                if cached_goal_passed(previous,m):results.append(previous);continue
                raise RuntimeError('Previous run did not reach this target; use a new stage directory to preserve its evidence')
            results.append(optimize(m,a.output,a.generations,a.plateau,initial,api=a.api,library=a.physics,internal_controls=a.internal_controls,
                seed_offset=a.seed_offset,line_width=a.line_width,spread_scale=a.spread_scale,fast_evaluation=a.fast_evaluation,launch_randomization=a.launch_randomization,transfer_priority=a.transfer_priority,
                local_window=a.local_window,pedal_timing=a.pedal_timing))
        except Exception as e:
            error={'index':index,'error':str(e)};errors.append(error);save_json(path/'error.json',error)
            print(json.dumps(error),flush=True)
        save_json(result_path,{'results':results,'errors':errors,'simulatorOnly':True,'allGoalsPassed':False})
    save_json(result_path,{'results':results,'errors':errors,'simulatorOnly':True,
        'allGoalsPassed':len(results)==25 and all(r['simGoalPassed'] for r in results)})


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
