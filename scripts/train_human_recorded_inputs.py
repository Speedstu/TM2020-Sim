#!/usr/bin/env python3
"""BC + counterfactual MPC/DAgger, on normal recorded inputs only.

The retained champions are read-only. Learned 100Hz feedback is shared between
map-specific human route assets; pedals use the original human input prior.
All counterfactuals clone complete simulator states, including input history.
Qualification always runs from race zero without restores or teacher actions.
"""
import argparse,copy,hashlib,json,os,signal,struct,time
from pathlib import Path
import ctypes as C
import numpy as np
import torch
import torch.nn.functional as F
from hybrid_tracking import Hybrid,load_asset,save_asset
from prepare_fall_campaign import ROOT,save_json
from vector_physics import VectorPhysics
from tune_hybrid_tracking import NativeEvaluator
from fast_engine import State48

BASE=ROOT/'local/training/human-rework-0.70'
NATIVE=Path(os.environ.get('TM2020_HUMAN_NATIVE',ROOT/'native/build-human-0.70'))
PHYSICS=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so'
STOP=False
def stop(*_):
    global STOP;STOP=True
def canonical(s):
    x=np.asarray(s,dtype=np.float32);return np.sign(x)*np.floor(np.abs(np.clip(x,-1,1))*127+.5)/np.float32(127)
def rigid(s):return np.array(s.rigid_words,dtype=np.uint32).view(np.float32)
def net_parameters(model,mean,scale):
    w=model[0].weight.detach().cpu().numpy()/scale[None,:]
    b=model[0].bias.detach().cpu().numpy()-w@mean
    return np.r_[w.ravel(),b,model[2].weight.detach().cpu().numpy().ravel(),model[2].bias.detach().cpu().numpy()]


def prepare(index,folder):
    src=ROOT/f'local/training/fall-campaign-0.52/{index:02d}';meta=json.loads((src/'map.json').read_text())
    demo=json.loads((src/'reference.json').read_text());ref=np.fromfile(src/'reference.f32',dtype='<f4').reshape(-1,25).copy()
    original=json.loads((BASE/f'corpus/{index:02d}/leaderboard-rank1/decoded-original.json').read_text())['ghosts'][0]
    ticks={}
    for group in original['groups']:
        assert group['truncated_at'] is None
        for k,c in enumerate(group['ticks']):ticks[group['start_offset_ms']//10+k]=[float(c['gas']),float(c['brake']),max(-1,c['steer']/127)]
    raw=np.array([ticks[k] for k in range(len(ref))],dtype=np.float32);ref[:,22:]=raw
    asset=folder/f'{index:02d}-initial.tmhyb';save_asset(asset,ref,[0,0,0,0,.01,.25],map_path=meta['map'],uid=meta['mapUid'],version=4)
    # Genuine demonstration states enter BC only; they are never substituted
    # for a simulated training or evaluation state.
    features=[];targets=[];fake=type('DemoObservation',(),{})();fake.states=[State48()];sources=[]
    with Hybrid(asset,1) as actor:
        for path in sorted((BASE/f'normal-demonstrations/{index:02d}').glob('*.npz')):
            report=json.loads(path.with_suffix('.json').read_text())
            if not report['acceptedForBC']:continue
            data=np.load(path);actor.reset(0);accepted=0;excluded=0
            for k,(body,command) in enumerate(zip(data['rigid'],data['controls'])):
                fake.states[0].tick=k;C.memmove(fake.states[0].rigid_words,body.ctypes.data,88)
                actor.act(fake);x=actor.features[0].copy()
                if x[11]!=1:break
                delta=(command[2]-x[9])/.25;ix=actor.cursor_index(0)
                if abs(delta)<=.999 and np.array_equal(command[:2],ref[ix,22:24]):
                    features.append(x);targets.append(delta);accepted+=1
                else:excluded+=1
                actor.commit(0,command[2])
            sources.append({'source':str(path),'rows':accepted,'excludedUnrepresentableOrPedalMismatch':excluded})
    if not len(features):raise RuntimeError('No normal-interface verified demonstrations for BC')
    save_json(folder/f'bc-sources-{index:02d}.json',{'sources':sources,'statesSubstitutedDuringSimulation':False})
    return {'index':index,'meta':meta,'reference':ref,'demo':demo,'asset':asset},np.array(features),np.array(targets)


def evaluate(asset,info,trials):
    ref=info['reference'];g=np.array([0,0,0,0,.01,.25]);rows=[]
    ev=NativeEvaluator(8,asset,api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
        map_path=info['meta']['map'],horizon=len(ref)+600,internal_controls=False,fast_evaluation=True)
    try:
        for k in range(0,len(trials),8):rows.extend(ev.evaluate(g,trials[k:k+8])[0])
    finally:ev.close()
    ts=[r['finishMs'] for r in rows if r['finishMs'] is not None]
    return {'finishes':len(ts),'count':len(rows),'meanMs':float(np.mean(ts)) if ts else None,
        'medianMs':float(np.median(ts)) if ts else None,'bestMs':min(ts) if ts else None,'worstMs':max(ts) if ts else None,'trials':rows}


def teacher_episode(info,asset,seed,output,plan_ticks=50,commit_ticks=5,student_probability=.15):
    ref=info['reference'];n=10;inputs=[];targets=[];commands=[];positions=[];splits=[];last_cp=0;planned_steps=0
    # Reference steering-step P99 is 26/127 on 03 and 33/127 on 06.
    # The previous +/-6-bin, 250ms teacher could not recover the 06 approach.
    # Plan a genuine 50ms correction, then normal reference inputs, over 500ms.
    started=time.monotonic();delta=np.array([-31,-12,-3,-1,0,1,3,12,31],dtype=np.float32)/127
    rng=np.random.default_rng(seed+411);previous_actual=0.;student_ticks=0
    with VectorPhysics(n,decision_ticks=1,api_path=NATIVE/'libtm2020_vector_physics.so',library=PHYSICS,
            map_path=info['meta']['map'],horizon=len(ref)+600,normal_inputs=True) as env,Hybrid(asset,1) as actor:
        env.reset(0,seed)
        while not STOP:
            state=env.states[0]
            if state.reserved or state.terminated or state.truncated:break
            actor.act(env);x=actor.features[0].copy()
            actor.commit(0,previous_actual)
            if x[11]!=1:break
            # The actual reference cursor is available independently of v4's
            # learned feature schema. Never infer it from a steering feature.
            phase=actor.cursor_index(0)
            env.save_checkpoint(0,0)
            for i in range(n):env.restore_checkpoint(i,0,seed)
            for k in range(plan_ticks):
                actions=np.tile(ref[min(phase+k,len(ref)-1),22:25],(n,1)).astype(np.float32)
                if k<commit_ticks:actions[1:,2]=canonical(actions[1:,2]+delta)
                actions[:,2]=canonical(actions[:,2])
                # Finished branches are absorbing. The wrapper accepts their
                # no-op steps; never restore them to invented poses.
                planned_steps+=sum(not(s.terminated or s.truncated) for s in env.states[:n]);env.step(actions)
            target=ref[min(phase+plan_ticks,len(ref)-1)];cost=[]
            for i in range(1,n):
                s=env.states[i]
                if s.finish_ms>=0:cost.append(-1e6+s.finish_ms);continue
                if s.reserved:cost.append(1e9);continue
                b=rigid(s);dp=b[9:12]-target[9:12];dv=b[16:19]-target[16:19]
                right=target[[0,3,6]];forward=target[[2,5,8]];up=target[[1,4,7]]
                lateral=float(dp@right);heading=float(b[[2,5,8]]@right)
                cost.append((lateral/.25)**2+.3*float(dp@forward/3)**2+(float(dp@up)/2)**2+
                    .4*float(dv@right/2)**2+.1*float(dv@forward/5)**2+(heading/.03)**2+
                    .001*(float(delta[i-1])*127)**2)
            chosen=int(np.argmin(cost));correction=delta[chosen]
            env.restore_checkpoint(0,0,seed)
            use_student=bool(rng.random()<student_probability)
            for k in range(commit_ticks):
                s=env.states[0]
                if s.reserved or s.terminated or s.truncated:break
                student_action=actor.act(env)[0];x=actor.features[0].copy()
                if x[11]!=1:break
                ix=actor.cursor_index(0);a=ref[ix,22:25].copy();a[2]=canonical(a[2]+correction)
                inputs.append(x);targets.append(float((a[2]-x[9])/.25))
                if use_student:a=student_action;student_ticks+=1
                commands.append([int(s.tick)*10,*a]);positions.append(rigid(s)[9:12])
                if s.checkpoints>last_cp:splits.append([int(s.checkpoints),int(s.tick)*10]);last_cp=s.checkpoints
                previous_actual=float(a[2]);actor.commit(0,previous_actual);env.step_one(0,a)
            if (output.parent/'STOP').exists():break
        final=env.states[0];result={'map':info['index'],'seed':seed,'finishMs':int(final.finish_ms) if final.finish_ms>=0 else None,
            'checkpoints':int(final.checkpoints),'committedTicks':len(inputs),'plannedPhysicsSteps':planned_steps,
            'seconds':time.monotonic()-started,'normalInputHistory':True,'bodyCorrections':False,'checkpointSplits':splits,
            'studentExecutedTicks':student_ticks,'studentProbability':student_probability,'labelsFromCounterfactualTeacher':True}
    np.savez_compressed(output,features=np.asarray(inputs).reshape(-1,12),targets=np.asarray(targets).reshape(-1),commands=np.asarray(commands).reshape(-1,4),positions=np.asarray(positions).reshape(-1,3),seed=seed)
    save_json(output.with_suffix('.json'),result);print(json.dumps({'teacherEpisode':result}),flush=True)
    return np.array(inputs),np.array(targets),result


def fit(model,optimizer,x,y,mean,scale,epochs,device,anchor_count=0):
    tx=torch.tensor((x-mean)/scale,device=device,dtype=torch.float64);ty=torch.tensor(y,device=device,dtype=torch.float64).clamp(-.999,.999)
    for _ in range(epochs):
        for ids in torch.randperm(len(tx),device=device).split(512):
            pred=model(tx[ids]).flatten().tanh();loss=F.smooth_l1_loss(pred,ty[ids],beta=.03)+1e-5*sum(p.square().mean() for p in model.parameters())
            anchored=ids<anchor_count
            if anchored.any():
                # Preserve real demonstrated i8 actions to within the same
                # quantization bin. This trains the actor, not a post-filter.
                raw_error=(pred[anchored]-ty[ids][anchored])*(.25*127)
                loss=loss+.1*F.relu(raw_error.abs()-.35).square().mean()
            optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
    return float(loss.detach())


def main():
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--rounds',type=int,default=0)
    p.add_argument('--maps',type=int,nargs='+',default=[1,3,6]);p.add_argument('--teacher-episodes',type=int,default=1)
    p.add_argument('--bc-epochs',type=int,default=10);p.add_argument('--epochs',type=int,default=20);p.add_argument('--qualify-every',type=int,default=1)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);torch.set_num_threads(1);torch.manual_seed(700031)
    if not torch.cuda.is_available():raise RuntimeError('CUDA is required for this training profile')
    torch.cuda.set_per_process_memory_fraction(.2);device='cuda';infos=[];xx=[];yy=[]
    for i in a.maps:
        info,x,y=prepare(i,a.output);infos.append(info);xx.append(x);yy.append(y)
    x0=np.concatenate(xx);y0=np.concatenate(yy);mean=x0.mean(0);scale=np.maximum(x0.std(0),.01)
    # Scale small physical tracking errors explicitly. The transform is folded
    # into portable weights; no game-side Python or CUDA runtime is needed.
    mean[:7]=0;scale[:7]=[.02,.02,.02,.02,.1,.1,.05]
    model=torch.nn.Sequential(torch.nn.Linear(12,32),torch.nn.Tanh(),torch.nn.Linear(32,1)).double().to(device)
    with torch.no_grad():model[2].weight.zero_();model[2].bias.zero_()
    optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4,weight_decay=1e-5)
    started=time.monotonic();datasets=[];history=[];best=None;stale=0;round_id=0
    checkpoint=a.output/'latest.pt'
    if checkpoint.exists():
        old=torch.load(checkpoint,map_location=device,weights_only=False);model.load_state_dict(old['model']);optimizer.load_state_dict(old['optimizer'])
        mean=old['mean'];scale=old['scale'];best=old['best'];round_id=int(old['round'])+1
    for file in sorted(a.output.glob('round-*/teacher-*.npz'))[-12:]:
        data=np.load(file)
        if len(data['features']):datasets.append((data['features'].reshape(-1,12),data['targets'].reshape(-1)))
    existing=[int(p.name.split('-')[1]) for p in a.output.glob('round-*') if p.is_dir()]
    if existing:round_id=max(round_id,max(existing)+1)
    protocol={'algorithm':'human BC + normal-history MPC/DAgger','device':device,'maps':a.maps,'physics':str(PHYSICS),
        'physicsSha256':hashlib.sha256(PHYSICS.read_bytes()).hexdigest(),'controlInterface':'normal binary pedals + i8/127 steer at 100Hz',
        'teacherUsesCompleteStateClones':True,'qualificationHasNoTeacherOrRestores':True,'referenceAssisted':True,
        'teacherPlanTicks':50,'teacherCommitTicks':5,'teacherCorrectionRawBins':[-31,-12,-3,-1,0,1,3,12,31],
        'pedals':'original human raw input prior, not learned by the feedback head','workers':os.environ.get('TM2020_PHYSICS_WORKERS'),
        'legacyChampionsReadOnly':True,'clientDeploymentAutomatic':False,'rounds':a.rounds,'stopEachPlateauRounds':5}
    save_json(a.output/'protocol.json',protocol)
    if not checkpoint.exists():
        fit(model,optimizer,x0,y0,mean,scale,a.bc_epochs,device,anchor_count=len(x0))
        temp=a.output/'latest.pt.tmp';torch.save({'model':model.state_dict(),'optimizer':optimizer.state_dict(),'round':-1,'mean':mean,'scale':scale,'best':best},temp);temp.replace(checkpoint)
    while not STOP and (not a.rounds or round_id<a.rounds):
        folder=a.output/f'round-{round_id:04d}';folder.mkdir(exist_ok=True)
        weights=net_parameters(model,mean,scale);current={}
        for info in infos:
            asset=folder/f'{info["index"]:02d}.tmhyb';save_asset(asset,info['reference'],[0,0,0,0,.01,.25],weights,map_path=info['meta']['map'],uid=info['meta']['mapUid'],version=4);current[info['index']]=asset
        for info in infos:
            for k in range(a.teacher_episodes):
                if STOP:break
                seed=7000000+round_id*1000+info['index']*10+k
                success=best['key'][0]/(8*len(infos)) if best else 0
                x,y,r=teacher_episode(info,current[info['index']],seed,folder/f'teacher-{info["index"]:02d}-{k}.npz',student_probability=.35 if success>=.8 else .15)
                if len(x):datasets.append((x,y))
                save_json(a.output/'status.json',{'phase':'teacher_collection','round':round_id,'latestEpisode':r,'protocol':protocol,'elapsedSeconds':time.monotonic()-started})
        if STOP:break
        datasets=datasets[-12:];x=np.concatenate([x0,*[v[0] for v in datasets]]);y=np.concatenate([y0,*[v[1] for v in datasets]])
        loss=fit(model,optimizer,x,y,mean,scale,a.epochs,device,anchor_count=len(x0));weights=net_parameters(model,mean,scale);development={}
        for info in infos:
            asset=folder/f'{info["index"]:02d}-trained.tmhyb';save_asset(asset,info['reference'],[0,0,0,0,.01,.25],weights,map_path=info['meta']['map'],uid=info['meta']['mapUid'],version=4)
            cases=[{'seed':7010000+info['index']*100+j,'warm':0,'duration':0,'kick':0.} for j in range(8)]
            development[info['index']]=evaluate(asset,info,cases)
        key=(sum(v['finishes'] for v in development.values()),-sum(sum(r['finishMs'] or 60000 for r in v['trials']) for v in development.values()))
        if best is None or tuple(key)>tuple(best['key']):best={'round':round_id,'key':key,'directory':str(folder)};stale=0
        else:stale+=1
        temp=a.output/'latest.pt.tmp';torch.save({'model':model.state_dict(),'optimizer':optimizer.state_dict(),'round':round_id,'mean':mean,'scale':scale,'best':best},temp);temp.replace(a.output/'latest.pt')
        result={'phase':'trained','round':round_id,'loss':loss,'development':development,'best':best,'staleRounds':stale,
            'datasetRows':len(x),'cudaAllocatedMb':torch.cuda.memory_allocated()/2**20,'seconds':time.monotonic()-started,'clientVerified':False}
        history.append(result);save_json(folder/'result.json',result);save_json(a.output/'status.json',result)
        print(json.dumps({'trainingRound':round_id,'loss':loss,'developmentFinishes':key[0],'count':8*len(infos),'rows':len(x)}),flush=True)
        if (round_id+1)%a.qualify_every==0:
            from qualify_human_recorded_inputs import qualify
            qualify(infos,folder,a.output,round_id)
        round_id+=1
        if stale>=5:break
    save_json(a.output/'completion.json',{'stoppedByUserOrService':STOP,'rounds':round_id,'bestDevelopment':best,'plateau':stale>=5,'clientVerified':False})


if __name__=='__main__':main()
