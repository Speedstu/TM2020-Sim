"""GPU imitation, selected by complete unassisted native races, then export for PPO/SDK."""
import argparse
import copy
import json
import math
from pathlib import Path
import time
import numpy as np
import torch
import torch.nn.functional as F
from gpu_ppo import Helpers,Checkpoint
from evaluate_stream import Evaluator
from train_continuous import score
from observation_history import ObservationHistory,schema_suffix


def read(datasets):
    rows=[];group=0
    for path in datasets:
        data=np.loadtxt(path,delimiter=',',skiprows=1,ndmin=2)
        if data.shape[1]!=52 or not np.isfinite(data).all():raise ValueError('DAgger dataset differs')
        # Keep whole episodes together across independent collection jobs.
        data[:,49]+=group;group=int(data[:,49].max())+1;rows.append(data)
    return np.concatenate(rows)


def initialize(template,hidden,seed):
    cp=copy.deepcopy(template);cp.hidden=hidden
    an=cp.actor_count;cn=cp.critic_count;rng=np.random.default_rng(seed)
    critic=np.concatenate([rng.normal(0,1/math.sqrt(cp.nx),hidden*cp.nx),np.zeros(hidden),np.zeros(hidden),[.78]])
    cp.parameters=np.concatenate([np.zeros(an),critic,[math.log(.015)]])
    cp.first=np.zeros_like(cp.parameters);cp.second=np.zeros_like(cp.parameters);cp.step=0
    cp.config=(2e-6,1.,1.,.1,.5,0.,.5,.001);cp.minibatch=1024
    return cp


def train(a):
    output=a.output;output.mkdir(parents=True,exist_ok=False);data=read(a.dataset)
    helper=Helpers();template=Checkpoint.load(a.source,helper)
    if template.nx!=48 or template.na!=1:raise ValueError('Steering-only route-free source required')
    torch.set_num_threads(1);torch.manual_seed(a.seed);device='cuda'
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    groups=np.unique(data[:,49]);valid_groups=groups[::5]
    valid=np.isin(data[:,49],valid_groups);train_rows=~valid
    if not train_rows.any() or not valid.any():raise ValueError('At least two distinct whole episodes required')
    features=np.empty((len(data),48*a.history))
    history=None;previous_episode=None
    for i,row in enumerate(data):
        if previous_episode!=row[49]:history=ObservationHistory(a.history);history.reset(row[:48]);previous_episode=row[49]
        else:history.push(row[:48])
        features[i]=history.values
    mean=features[train_rows].mean(0);raw_std=features[train_rows].std(0);scale=np.maximum(raw_std,.05)
    constant_features=raw_std<1e-8
    x=torch.tensor((features-mean)/scale,dtype=torch.float32,device=device)
    y=torch.tensor(data[:,48:49],dtype=torch.float32,device=device)
    ids=torch.as_tensor(np.flatnonzero(train_rows),dtype=torch.int64,device=device)
    validation_ids=torch.as_tensor(np.flatnonzero(valid),dtype=torch.int64,device=device)
    inputs=48*a.history
    actor=torch.nn.Sequential(torch.nn.Linear(inputs,a.hidden),torch.nn.Tanh(),torch.nn.Linear(a.hidden,1)).to(device)
    with torch.no_grad():
        actor[0].weight.normal_(0,1/math.sqrt(inputs));actor[0].bias.zero_();actor[2].weight.normal_(0,.01/math.sqrt(a.hidden));actor[2].bias.zero_()
    if a.initialize:
        old=Checkpoint.load(a.initialize,helper)
        if old.nx not in (48,144,inputs) or old.nx>inputs or old.na!=1 or a.hidden%old.hidden:raise ValueError('Initialization architecture differs')
        p=old.parameters[:old.actor_count];h=old.hidden;head=h*(old.nx+1)
        weight=p[:h*old.nx].reshape(h,old.nx);bias=p[h*old.nx:head];last=p[head:head+h].reshape(1,h);tail=p[-1:]
        if old.nx!=inputs:weight=np.concatenate([np.zeros((h,inputs-old.nx)),weight],axis=1)
        copies=a.hidden//h;weight=np.repeat(weight,copies,axis=0);bias=np.repeat(bias,copies);last=np.repeat(last,copies,axis=1)/copies
        with torch.no_grad():
            actor[0].weight.copy_(torch.tensor(weight*scale[None,:],dtype=torch.float32,device=device))
            actor[0].bias.copy_(torch.tensor(bias+weight@mean,dtype=torch.float32,device=device))
            actor[2].weight.copy_(torch.tensor(last,dtype=torch.float32,device=device));actor[2].bias.copy_(torch.tensor(tail,dtype=torch.float32,device=device))
            if copies>1:
                delta=torch.randn((1,a.hidden//2),device=device)*.001
                actor[2].weight[:,0::2].add_(delta);actor[2].weight[:,1::2].sub_(delta)
    optimizer=torch.optim.AdamW(actor.parameters(),lr=a.learning_rate,weight_decay=1e-5)
    template.nx=inputs;template.schema=template.schema.replace('|policy_actions=',schema_suffix(a.history)+'|policy_actions=')
    checkpoint=initialize(template,a.hidden,a.seed);best_score=None;history=[];started=time.perf_counter()
    def export(folder):
        folder.mkdir()
        first=actor[0].weight.detach().double().cpu().numpy()/scale[None,:]
        first[:,constant_features]=0.
        bias=actor[0].bias.detach().double().cpu().numpy()-first@mean
        head=actor[2].weight.detach().double().cpu().numpy();tail=actor[2].bias.detach().double().cpu().numpy()
        checkpoint.parameters[:checkpoint.actor_count]=np.concatenate([first.ravel(),bias,head.ravel(),tail])
        checkpoint.save(folder/'training.checkpoint',helper);checkpoint.export_policy(folder/'policy.tmppo',helper)
        return folder/'policy.tmppo'
    with Evaluator(output/'native-evaluator') as evaluator:
        if a.initialize:
            initial_model=export(output/'epoch-00000');initial_eval=evaluator.evaluate(initial_model,a.eval_trials,a.eval_seed)
            initial_row={'epoch':0,'evaluation':initial_eval,'seconds':time.perf_counter()-started}
            from train_continuous import atomic_copy
            atomic_copy(initial_model,output/'best.tmppo');atomic_copy(output/'epoch-00000/training.checkpoint',output/'best.checkpoint')
            best_score=(initial_eval['finishes']/initial_eval['trials'],-initial_eval['meanFinishMs'] if initial_eval['finishes'] else -1e9, -1e9)
            (output/'best.json').write_text(json.dumps(initial_row,indent=2)+'\n');history.append(initial_row);print(json.dumps(initial_row),flush=True)
        for epoch in range(1,a.epochs+1):
            order=ids[torch.randperm(len(ids),device=device)]
            for at in range(0,len(order),a.batch_size):
                batch=order[at:at+a.batch_size];latent=actor(x[batch]);prediction=latent.tanh()
                target_latent=y[batch].clamp(-.995,.995).atanh()
                loss=F.smooth_l1_loss(prediction,y[batch],beta=.05)+a.latent_loss_weight*F.mse_loss(latent,target_latent)
                optimizer.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(actor.parameters(),1.);optimizer.step()
            if epoch%a.eval_every==0 or epoch==a.epochs:
                with torch.no_grad():mse=F.mse_loss(actor(x[validation_ids]).tanh(),y[validation_ids]).item()
                folder=output/f'epoch-{epoch:05d}';model=export(folder);evaluation=evaluator.evaluate(model,a.eval_trials,a.eval_seed)
                row={'epoch':epoch,'validationMse':mse,'evaluation':evaluation,'seconds':time.perf_counter()-started}
                history.append(row);print(json.dumps(row),flush=True)
                current=(evaluation['finishes']/evaluation['trials'],-evaluation['meanFinishMs'] if evaluation['finishes'] else -mse,-mse)
                if best_score is None or current>best_score:
                    best_score=current
                    from train_continuous import atomic_copy
                    atomic_copy(model,output/'best.tmppo');atomic_copy(folder/'training.checkpoint',output/'best.checkpoint')
                    (output/'best.json').write_text(json.dumps(row,indent=2)+'\n')
                (output/'history.json').write_text(json.dumps(history,indent=2)+'\n')
    report={'device':device,'gpu':torch.cuda.get_device_name(),'rows':len(data),'trainEpisodes':int(len(groups)-len(valid_groups)),
            'validationEpisodes':int(len(valid_groups)),'hidden':a.hidden,'historyFrames':a.history,'previousSteerObserved':True,
            'selectedByUnassistedFullRaces':True,'teacherUsedAtDeployment':False,'policySchema':checkpoint.schema,
            'constantFeatureWeightsZeroed':np.flatnonzero(constant_features).tolist(),
            'seconds':time.perf_counter()-started,'best':json.loads((output/'best.json').read_text())}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,action='append',required=True)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--hidden',type=int,choices=[128,256,512,1024],default=256);p.add_argument('--epochs',type=int,default=1000)
    p.add_argument('--history',type=int,choices=[1,3,5],default=1);p.add_argument('--initialize',type=Path)
    p.add_argument('--eval-every',type=int,default=50);p.add_argument('--eval-trials',type=int,default=5)
    p.add_argument('--eval-seed',type=int,default=921042);p.add_argument('--batch-size',type=int,default=256)
    p.add_argument('--learning-rate',type=float,default=.0005);p.add_argument('--seed',type=int,default=45026)
    p.add_argument('--latent-loss-weight',type=float,default=.01)
    a=p.parse_args()
    if not 1<=a.epochs<=10000 or a.eval_every<1 or not 1<=a.eval_trials<=100 or a.batch_size<1:p.error('Invalid bounded training settings')
    train(a)
