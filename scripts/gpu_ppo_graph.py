"""Captured float64 PPO minibatches; checkpoints and native shuffle stay unchanged."""
import math
import time
import numpy as np
import torch
import torch.nn.functional as F
from gpu_ppo import Optimizer,read_rollout


class CapturedBatch:
    def __init__(self,cp,count,device):
        self.nx,self.na,self.hidden=cp.nx,cp.na,cp.hidden
        self.an,self.cn=cp.actor_count,cp.critic_count
        self.mb=cp.minibatch;self.config=cp.config
        dtype=torch.float64
        self.p=torch.nn.Parameter(torch.zeros(len(cp.parameters),device=device,dtype=dtype))
        self.m=torch.zeros_like(self.p);self.v=torch.zeros_like(self.p)
        self.data=torch.zeros((count,cp.nx+cp.na+3),device=device,dtype=dtype)
        self.order=torch.arange(count,device=device,dtype=torch.int64)
        self.position=torch.arange(self.mb,device=device,dtype=torch.int64)
        self.offset=torch.zeros((),device=device,dtype=torch.int64)
        self.counter=torch.zeros((),device=device,dtype=torch.int64)
        self.corrections=torch.ones((cp.epochs*(count//self.mb),2),device=device,dtype=dtype)
        self.statistics=torch.zeros(4,device=device,dtype=dtype)
        self.finite=torch.ones((),device=device,dtype=torch.bool)
        stream=torch.cuda.Stream();stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            for _ in range(3):
                self.offset.zero_();self.counter.zero_();self.batch()
        torch.cuda.current_stream().wait_stream(stream)
        self.offset.zero_();self.counter.zero_()
        self.graph=torch.cuda.CUDAGraph()
        with torch.cuda.graph(self.graph):self.batch()

    def network(self,x,p,outputs):
        h=self.hidden;bias=self.nx*h;head=bias+h;tail=head+outputs*h
        return F.linear(torch.tanh(F.linear(x,p[:bias].reshape(h,self.nx),p[bias:head])),p[head:tail].reshape(outputs,h),p[tail:])

    def logp(self,x,z):
        mean=self.network(x,self.p[:self.an],self.na);ls=self.p[self.an+self.cn:]
        a=-2*z;jac=2*(math.log(2.)-z-(a.clamp_min(0)+torch.log1p(torch.exp(-torch.abs(a)))))
        d=(z-mean)*torch.exp(-ls)
        return (-.5*(d*d+1.8378770664093454836)-ls-jac).sum(-1)

    def batch(self):
        lr,_,_,clip,value_coefficient,entropy,maxnorm,_=self.config
        indices=self.order.index_select(0,self.position+self.offset)
        data=self.data.index_select(0,indices)
        x=data[:,:self.nx];z=data[:,self.nx:self.nx+self.na]
        old_logp,adv,target=data[:,self.nx+self.na:].unbind(-1)
        ratio=torch.exp((self.logp(x,z)-old_logp).clamp(-60,60));clipped=ratio.clamp(1-clip,1+clip)
        stop=((adv>=0)&(ratio>1+clip))|((adv<0)&(ratio<1-clip))
        ploss=-torch.where(stop,clipped*adv,ratio*adv).mean()
        error=self.network(x,self.p[self.an:self.an+self.cn],1).flatten()-target
        vloss=.5*(error*error).mean()
        loss=ploss+value_coefficient*vloss-entropy*self.p[self.an+self.cn:].sum()
        gradient=torch.autograd.grad(loss,self.p)[0];norm=gradient.norm()
        g=gradient*(maxnorm/norm).clamp(max=1.)
        with torch.no_grad():
            self.finite.logical_and_(torch.isfinite(g).all())
            self.m.mul_(.9).add_(g,alpha=.1);self.v.mul_(.999).addcmul_(g,g,value=.001)
            correction=self.corrections.index_select(0,self.counter.reshape(1)).flatten()
            self.p.sub_(lr*(self.m/correction[0])/(torch.sqrt(self.v/correction[1])+1e-8))
            self.p[self.an+self.cn:].clamp_(-5,2)
            self.statistics[0].add_(ploss.detach());self.statistics[1].add_(vloss.detach())
            self.statistics[2].add_(stop.to(torch.float64).mean());self.statistics[3].copy_(norm)
            self.offset.add_(self.mb);self.counter.add_(1)


class GraphOptimizer(Optimizer):
    def __init__(self,device='cuda'):
        super().__init__(device)
        if self.device.type!='cuda':raise ValueError('CUDA graph optimizer requires CUDA')
        self.cached=None;self.key=None

    def update(self,cp,rollout,envs,helper):
        self.synchronize();start=time.perf_counter()
        lr,gamma,lam,clip,value_coefficient,entropy,maxnorm,target_kl=cp.config
        arrays=read_rollout(rollout,cp.nx,cp.na,envs,gamma,lam);count=len(arrays['x'])
        if count%cp.minibatch:
            result=super().update(cp,rollout,envs,helper);result['cudaGraph']=False;return result
        key=(cp.nx,cp.na,cp.hidden,count,cp.minibatch,cp.epochs,cp.config)
        compiled=key!=self.key
        if compiled:self.cached=CapturedBatch(cp,count,self.device);self.key=key
        batch=self.cached
        packed=np.concatenate([arrays['x'],arrays['z'],arrays['old_logp'][:,None],arrays['advantage'][:,None],arrays['target'][:,None]],axis=1)
        with torch.no_grad():
            batch.p.copy_(torch.from_numpy(cp.parameters));batch.m.copy_(torch.from_numpy(cp.first));batch.v.copy_(torch.from_numpy(cp.second))
            batch.data.copy_(torch.from_numpy(packed));batch.offset.zero_();batch.counter.zero_();batch.statistics.zero_();batch.finite.fill_(True)
            corrections=np.array([(1-math.pow(.9,s),1-math.pow(.999,s)) for s in range(cp.step+1,cp.step+1+cp.epochs*(count//cp.minibatch))])
            batch.corrections.copy_(torch.from_numpy(corrections))
            x=batch.data[:,:cp.nx];z=batch.data[:,cp.nx:cp.nx+cp.na]
            old_logp=torch.as_tensor(arrays['old_logp'],device=self.device)
            old_value=torch.as_tensor(arrays['old_value'],device=self.device)
            err=(batch.logp(x,z)-old_logp).abs().max().item()
            verr=(batch.network(x,batch.p[cp.actor_count:cp.actor_count+cp.critic_count],1).flatten()-old_value).abs().max().item()
        if err>=1e-7 or verr>=1e-7:raise ValueError(f'GPU behavior identity failed: logp={err} value={verr}')
        metrics={'minibatches':0,'epochs':0,'kl_stopped':False}
        order=np.arange(count,dtype=np.uint32)
        for epoch in range(cp.epochs):
            with torch.no_grad():
                diff=batch.logp(x,z)-old_logp;kl=(torch.exp(diff.clamp(-60,60))-1-diff).mean().item()
            if kl>1.5*target_kl:metrics['kl_stopped']=True;break
            cp.shuffle,order=helper.shuffle(cp.shuffle,order)
            batch.order.copy_(torch.from_numpy(order.astype(np.int64)));batch.offset.zero_()
            for _ in range(count//cp.minibatch):batch.graph.replay()
            count_updates=count//cp.minibatch;cp.step+=count_updates
            metrics['minibatches']+=count_updates;metrics['epochs']+=1
        with torch.no_grad():
            diff=batch.logp(x,z)-old_logp;metrics['approx_kl']=(torch.exp(diff.clamp(-60,60))-1-diff).mean().item()
        if not batch.finite.item():raise ValueError('Nonfinite GPU gradient')
        values=batch.statistics.cpu().tolist()
        for name,value in zip(('policy_loss','value_loss','clip_fraction','gradient_norm'),values):metrics[name]=value
        for name in ('policy_loss','value_loss','clip_fraction'):
            if metrics['minibatches']:metrics[name]/=metrics['minibatches']
        cp.parameters=batch.p.detach().cpu().numpy().copy();cp.first=batch.m.cpu().numpy().copy();cp.second=batch.v.cpu().numpy().copy()
        self.synchronize();metrics.update(optimizerSeconds=time.perf_counter()-start,device=str(self.device),dtype='float64',
            behaviorLogpMaxError=err,behaviorValueMaxError=verr,cudaGraph=True,graphCapturedThisUpdate=compiled)
        return metrics
