"""Minimum-time PPO credit ablation; native physics and action policy unchanged."""
import time
import numpy as np
import torch
from torch import nn


def potential(observations):
    """Bounded, observable distance potential. No replay or route ordinal."""
    x=np.asarray(observations)
    if x.ndim!=2 or x.shape[1]!=48 or not np.isfinite(x).all():
        raise ValueError('Expected finite 48-feature observations')
    return -2.*np.linalg.norm(x[:,6:9],axis=1)


def shape_reward(reward,before,after,done):
    """Gamma=1; force terminal potential to zero before auto-reset observations."""
    return reward+.01*(np.where(done,0.,after)-before)


def gae(reward,done,values,bootstrap,lam):
    if not 0. <= lam <= 1.:
        raise ValueError('GAE lambda outside [0,1]')
    carry=torch.zeros_like(bootstrap)
    advantages=torch.empty_like(reward)
    value=bootstrap
    for t in range(len(reward)-1,-1,-1):
        alive=(~done[t]).double()
        delta=reward[t]+alive*value-values[t]
        carry=delta+lam*alive*carry
        advantages[t]=carry
        value=values[t]
    return advantages,advantages+values


def update(policy,episodes,optimizer,rollout,gae_lambda=.995):
    # Keep the historical optimizer, clipping, minibatches and KL guard equal.
    n=episodes.n;fields={k:[] for k in ('x','z','logp','value','reward','done')};start=time.monotonic()
    for _ in range(rollout):
        x=episodes.cuda_history if hasattr(episodes,'cuda_history') else torch.as_tensor(episodes.history.copy(),device='cuda')
        with torch.no_grad():action,z,lp,value=policy.action(x)
        reward,done=episodes.step(action.cpu().numpy())
        for key,val in (('x',x),('z',z),('logp',lp),('value',value),('reward',torch.tensor(reward,device='cuda')),('done',torch.tensor(done,device='cuda'))):fields[key].append(val)
    data={k:torch.stack(v) for k,v in fields.items()}
    with torch.no_grad():
        bootstrap=policy.critic(episodes.cuda_history if hasattr(episodes,'cuda_history') else torch.as_tensor(episodes.history,device='cuda')).flatten()
        advantages,target=gae(data['reward'],data['done'],data['value'],bootstrap,gae_lambda)
        advantages=(advantages-advantages.mean())/(advantages.std(unbiased=False)+1e-8)
    x=data['x'].flatten(0,1);z=data['z'].flatten(0,1);old=data['logp'].flatten();adv=advantages.flatten();target=target.flatten();count=n*rollout
    with torch.no_grad():identity=(policy.logp(x,z)-old).abs().max().item()
    if identity>1e-7:raise RuntimeError(f'Behavior identity error {identity}')
    kl=0.;minibatches=0
    for epoch in range(4):
        with torch.no_grad():
            diff=policy.logp(x,z)-old;kl=(diff.exp()-1-diff).mean().item()
        if kl>.0045:break
        for indices in torch.randperm(count,device='cuda').split(1024):
            ratio=(policy.logp(x[indices],z[indices])-old[indices]).clamp(-60,60).exp()
            actor=-torch.minimum(ratio*adv[indices],ratio.clamp(.9,1.1)*adv[indices]).mean()
            critic=.5*(policy.critic(x[indices]).flatten()-target[indices]).square().mean()
            loss=actor+.5*critic;optimizer.zero_grad(set_to_none=True);loss.backward()
            norm=nn.utils.clip_grad_norm_(policy.parameters(),.5)
            if not torch.isfinite(norm):raise RuntimeError('Nonfinite PPO gradient')
            optimizer.step();minibatches+=1
            with torch.no_grad():policy.logstd.clamp_(-5,0)
    return {'seconds':time.monotonic()-start,'transitions':count,'behaviorLogpError':identity,
            'kl':kl,'minibatches':minibatches,'gaeLambda':gae_lambda}
