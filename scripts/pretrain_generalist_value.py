"""Fit only the PPO critic to complete on-policy episode returns on CUDA."""
import argparse
import copy
import json
import math
from pathlib import Path
import time
import numpy as np
import torch
from gpu_ppo import Checkpoint,Helpers,read_rollout


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--rollout',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--environments',type=int,default=16)
    p.add_argument('--steps',type=int,default=1000);p.add_argument('--actor-learning-rate',type=float,default=3e-7)
    a=p.parse_args()
    if a.output.exists():p.error('Never overwrite a retained initialization')
    if not 1<=a.steps<=10000 or not 1<=a.environments<=256 or not 0<a.actor_learning_rate<=.001:p.error('Invalid bounded settings')
    a.output.mkdir(parents=True);helper=Helpers();cp=Checkpoint.load(a.source,helper)
    actor=cp.parameters[:cp.actor_count].copy();torch.set_num_threads(1);torch.manual_seed(45026)
    if not torch.cuda.is_available():raise RuntimeError('CUDA is required')
    arrays=read_rollout(a.rollout,cp.nx,cp.na,a.environments,1.,1.)
    # Exclude incomplete final episodes: no value bootstrap is treated as an
    # observed Monte Carlo outcome. Validation keeps entire episodes together.
    raw=np.fromfile(a.rollout,dtype='<f8',offset=24).reshape(-1,7+cp.na+cp.nx)
    include=np.zeros(len(raw),bool);groups=np.empty(len(raw),np.int64)
    for env in range(a.environments):
        indices=np.arange(env,len(raw),a.environments);boundaries=indices[raw[indices,4]!=0]
        if not len(boundaries):continue
        include[indices[indices<=boundaries[-1]]]=True
        episode=0
        for i in indices:
            groups[i]=env+episode*a.environments
            if raw[i,4]:episode+=1
    valid=include&(groups%5==0);train=include&~valid
    if not train.any() or not valid.any():raise ValueError('Complete train/validation episodes are required')
    source_x=arrays['x'];mean=source_x[train].mean(0);scale=np.maximum(source_x[train].std(0),.05)
    x=torch.tensor((source_x-mean)/scale,device='cuda',dtype=torch.float32)
    target=torch.tensor(arrays['target'][:,None],device='cuda',dtype=torch.float32)
    train_ids=torch.as_tensor(np.flatnonzero(train),device='cuda');valid_ids=torch.as_tensor(np.flatnonzero(valid),device='cuda')
    net=torch.nn.Sequential(torch.nn.Linear(cp.nx,cp.hidden),torch.nn.Tanh(),torch.nn.Linear(cp.hidden,1)).cuda()
    with torch.no_grad():
        net[0].weight.normal_(0,1/math.sqrt(cp.nx));net[0].bias.zero_();net[2].weight.zero_();net[2].bias.fill_(float(arrays['target'][train].mean()))
    optimizer=torch.optim.Adam(net.parameters(),lr=.001);best=None;best_mse=math.inf;history=[];start=time.perf_counter()
    for step in range(a.steps+1):
        if step%25==0 or step==a.steps:
            with torch.no_grad():error=torch.nn.functional.mse_loss(net(x[valid_ids]),target[valid_ids]).item()
            history.append({'step':step,'validationMse':error})
            if error<best_mse:best_mse=error;best=copy.deepcopy(net.state_dict())
        if step==a.steps:break
        ids=train_ids[torch.randint(len(train_ids),(2048,),device='cuda')]
        loss=torch.nn.functional.mse_loss(net(x[ids]),target[ids]);optimizer.zero_grad(set_to_none=True)
        loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),1.);optimizer.step()
    net.load_state_dict(best)
    first=net[0].weight.detach().double().cpu().numpy()/scale[None,:]
    bias=net[0].bias.detach().double().cpu().numpy()-first@mean
    last=net[2].weight.detach().double().cpu().numpy();tail=net[2].bias.detach().double().cpu().numpy()
    cp.parameters[cp.actor_count:cp.actor_count+cp.critic_count]=np.concatenate([first.ravel(),bias,last.ravel(),tail])
    assert np.array_equal(cp.parameters[:cp.actor_count],actor),'Critic pretraining changed the actor'
    cp.first.fill(0.);cp.second.fill(0.);cp.step=0;cp.epochs=4;cp.minibatch=1024
    cp.config=(a.actor_learning_rate,1.,.995,.1,.5,0.,.5,.003)
    cp.save(a.output/'ready.checkpoint',helper);cp.export_policy(a.output/'ready.tmppo',helper)
    report={'actorBitwisePreserved':True,'completeRows':int(include.sum()),'incompleteRowsExcluded':int((~include).sum()),
            'trainRows':int(train.sum()),'validationRows':int(valid.sum()),'initialValidationMse':history[0]['validationMse'],
            'bestValidationMse':best_mse,'steps':a.steps,'device':torch.cuda.get_device_name(),
            'seconds':time.perf_counter()-start,'ppoLearningRate':a.actor_learning_rate,'history':history}
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='history'}),flush=True)

if __name__=='__main__':main()
