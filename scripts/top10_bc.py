#!/usr/bin/env python3
"""Train one autonomous 100 Hz actor from verified reference controls."""
import argparse
import copy
import json
import signal
import time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from compare_hybrid_ppo import Policy,save_json
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights,atomic_torch
from top10_core import DIRECTORY,API,histories,evaluate,score
from vector_physics import VectorPhysics
from run_fast_ppo import ROOT

STOP=False
def stop(signum,frame):
    global STOP
    STOP=True


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--epochs',type=int,default=1500);p.add_argument('--eval-every',type=int,default=50)
    p.add_argument('--source',type=Path,default=ROOT/'local/training/time-main-20261030/best.pt')
    p.add_argument('--normalize',action='store_true')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    if not torch.cuda.is_available():raise RuntimeError('CUDA required')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True);torch.manual_seed(99049)
    helpers=Helpers();prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',helpers)
    model=Policy(prior,'continuous');load_weights(model,a.source)
    features=[];targets=[];values=[]
    for name in ('wr','direct'):
        path=DIRECTORY/('wr-100hz-demonstration.npy' if name=='wr' else 'direct-100hz-demonstration.npy')
        rows=np.load(path);features.append(histories(rows));targets.append(rows[:,48:51])
        end=19988 if name=='wr' else 20006
        values.append((100.-(end-np.arange(len(rows))*10.)/1000.)*.01)
    x=torch.as_tensor(np.concatenate(features),device='cuda');y=torch.as_tensor(np.concatenate(targets),device='cuda')
    mean=x.mean(0) if a.normalize else torch.zeros(x.shape[1],device='cuda',dtype=x.dtype)
    scale=x.std(0,unbiased=False).clamp_min(.01) if a.normalize else torch.ones_like(mean)
    with torch.no_grad():
        initial=model.actor[0].weight.clone()
        model.actor[0].weight.mul_(scale)
        model.actor[0].bias.add_(initial@mean)
    normalized=(x-mean)/scale
    def deployable():
        result=copy.deepcopy(model)
        with torch.no_grad():
            result.actor[0].weight.div_(scale)
            result.actor[0].bias.sub_(result.actor[0].weight@mean)
        return result
    target_value=torch.as_tensor(np.concatenate(values),device='cuda')
    # Bin ±127 must remain representable after i8 quantization. Clipping at
    # .995 would train the full-steer target into bin126 rather than bin127.
    latent=y[:,2].clamp(-.999,.999).atanh()
    optimizer=torch.optim.Adam([{'params':model.actor.parameters(),'lr':1e-4},
                               {'params':model.critic.parameters(),'lr':1e-4}],eps=1e-8)
    seeds=[36139877,99049001,99049002,99049003]
    started=time.monotonic();best=None;best_epoch=0;results=[]
    with VectorPhysics(4,decision_ticks=1,api_path=API) as env:
        for epoch in range(a.epochs+1):
            if STOP or (a.output/'STOP').exists():break
            loss=None
            if epoch:
                for idx in torch.randperm(len(x),device='cuda').split(512):
                    out=model.actor(normalized[idx]);steer=out[:,2].tanh()
                    actor=F.smooth_l1_loss(out[:,2],latent[idx],beta=.2)+.2*F.mse_loss(steer,y[idx,2])+.1*F.binary_cross_entropy_with_logits(out[:,:2],y[idx,:2])
                    critic=F.mse_loss(model.critic(x[idx]).flatten(),target_value[idx])
                    loss=actor+.2*critic;optimizer.zero_grad(set_to_none=True);loss.backward()
                    norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
                    if not torch.isfinite(norm):raise RuntimeError('Nonfinite imitation gradient')
                    optimizer.step()
            if epoch%a.eval_every==0 or epoch==a.epochs:
                exported=deployable();result=evaluate(exported,env,seeds);key=score(result)
                improved=best is None or key>best
                if improved:
                    best=key;best_epoch=epoch;atomic_torch(a.output/'best.pt',exported.state_dict())
                    temp=a.output/'best-next.tmppo';temp.unlink(missing_ok=True)
                    exported.export(prior,temp,helpers,decision_ticks=1);temp.replace(a.output/'best.tmppo')
                    save_json(a.output/'best-score.json',{'epoch':epoch,**result})
                event={'epoch':epoch,'improved':improved,'loss':float(loss) if loss is not None else None,**result}
                results.append(event);save_json(a.output/'evaluations.json',results)
                state={'stage':'reference-imitation','epoch':epoch,'epochs':a.epochs,'bestEpoch':best_epoch,
                       'last':result,'seconds':time.monotonic()-started,'rows':len(x),'decisionHz':100,
                       'source':str(a.source),'normalizedTraining':a.normalize,'referenceUsedAtDeployment':False,'realGameVerified':False}
                save_json(a.output/'status.json',state);print(json.dumps(state),flush=True)
                atomic_torch(a.output/'last.pt',{'model':exported.state_dict(),'normalizedModel':model.state_dict(),
                                               'normalizationMean':mean,'normalizationScale':scale,
                                               'optimizer':optimizer.state_dict(),'epoch':epoch})
    save_json(a.output/'report.json',{'state':'stopped' if STOP else 'complete','bestEpoch':best_epoch,
                                     'seconds':time.monotonic()-started,'best':json.loads((a.output/'best-score.json').read_text())})


if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);main()
