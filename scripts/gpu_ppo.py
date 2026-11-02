"""CUDA PPO matching the native SDK layout, GAE, shuffle and Adam equations.

Only optimization moves to CUDA. Native collectors and SDK inference stay intact.
Native checkpoints preserve weights, Adam moments/step and both native RNG texts.
"""
import ctypes as C
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import time
import numpy as np
import torch
import torch.nn.functional as F

ROOT=Path(__file__).resolve().parents[1]

class Helpers:
    def __init__(self,path=ROOT/'native/build-linux/libtm2020_gpu_helpers.so'):
        self.lib=C.CDLL(str(Path(path).resolve(strict=True)))
        self.lib.tmppo_checksum.argtypes=[C.c_void_p,C.c_size_t];self.lib.tmppo_checksum.restype=C.c_uint64
        self.lib.tmppo_shuffle.argtypes=[C.c_char_p,C.POINTER(C.c_uint32),C.c_uint32,C.c_void_p,C.c_size_t]
    def checksum(self,data):
        buffer=C.create_string_buffer(data)
        return self.lib.tmppo_checksum(buffer,len(data))
    def shuffle(self,state,order):
        order=np.ascontiguousarray(order,dtype=np.uint32);out=C.create_string_buffer(32769)
        n=self.lib.tmppo_shuffle(state.encode(),order.ctypes.data_as(C.POINTER(C.c_uint32)),len(order),out,len(out))
        if n<=0:raise ValueError('Native shuffle state/order rejected')
        return out.value.decode(),order

@dataclass
class Checkpoint:
    nx:int; na:int; hidden:int; schema:str; step:int
    config:tuple; epochs:int; minibatch:int
    parameters:np.ndarray; first:np.ndarray; second:np.ndarray
    shuffle:str; sampler:str
    @property
    def actor_count(self):return self.hidden*self.nx+self.hidden+self.na*self.hidden+self.na
    @property
    def critic_count(self):return self.hidden*self.nx+2*self.hidden+1
    @classmethod
    def load(cls,path,helper):
        b=Path(path).read_bytes()
        if len(b)<136 or len(b)>64*1024*1024 or b[:8]!=b'TMTRAIN1':raise ValueError('Invalid native checkpoint')
        if helper.checksum(b[:-8])!=struct.unpack_from('<Q',b,len(b)-8)[0]:raise ValueError('Native checkpoint checksum mismatch')
        version,nx,na,h,ns,reserved=struct.unpack_from('<6I',b,8)
        if version!=1 or reserved or not(1<=nx<=4096 and 1<=na<=64 and 1<=h<=1024 and 1<=ns<=4096):raise ValueError('Checkpoint architecture rejected')
        step=struct.unpack_from('<Q',b,32)[0];config=struct.unpack_from('<8d',b,40)
        epochs,mb=struct.unpack_from('<2Q',b,104);nshuffle,nsampler=struct.unpack_from('<2I',b,120)
        offset=128;schema=b[offset:offset+ns].decode();offset+=ns
        actor=h*nx+h+na*h+na;critic=h*nx+2*h+1;n=actor+critic+na
        vectors=[]
        for _ in range(3):
            vectors.append(np.frombuffer(b,dtype='<f8',count=n,offset=offset).copy());offset+=n*8
        if not all(np.isfinite(v).all() for v in vectors) or (vectors[2]<0).any():raise ValueError('Nonfinite/invalid Adam state')
        shuffle=b[offset:offset+nshuffle].decode();offset+=nshuffle
        sampler=b[offset:offset+nsampler].decode();offset+=nsampler
        if offset!=len(b)-8 or not (0<epochs<=1000 and mb>0):raise ValueError('Checkpoint lengths/configuration rejected')
        return cls(nx,na,h,schema,step,config,epochs,mb,*vectors,shuffle,sampler)
    def save(self,path,helper):
        schema=self.schema.encode();shuffle=self.shuffle.encode();sampler=self.sampler.encode()
        b=bytearray(b'TMTRAIN1');b.extend(struct.pack('<6IQ8d2Q2I',1,self.nx,self.na,self.hidden,len(schema),0,self.step,*self.config,self.epochs,self.minibatch,len(shuffle),len(sampler)));b.extend(schema)
        for v in (self.parameters,self.first,self.second):b.extend(np.asarray(v,dtype='<f8').tobytes())
        b.extend(shuffle);b.extend(sampler);b.extend(struct.pack('<Q',helper.checksum(bytes(b))))
        path=Path(path);tmp=Path(str(path)+'.tmp')
        if path.exists():raise FileExistsError(path)
        with tmp.open('xb') as f:f.write(b);f.flush()
        tmp.rename(path)
    def export_policy(self,path,helper):
        b=bytearray(b'TMPPO001');schema=self.schema.encode()
        b.extend(struct.pack('<6I',1,self.nx,self.na,self.hidden,len(schema),0));b.extend(schema)
        b.extend(np.asarray(self.parameters,dtype='<f8').tobytes());b.extend(struct.pack('<Q',helper.checksum(bytes(b))))
        with Path(path).open('xb') as f:f.write(b)


def read_rollout(path,nx,na,envs,gamma,lam):
    path=Path(path)
    with path.open('rb') as f:
        magic=f.read(8)
        if magic==b'TMROLL01':
            header=f.read(16)
            if len(header)!=16:raise ValueError('Truncated binary rollout header')
            actual_nx,actual_na,count=struct.unpack('<IIQ',header)
            columns=7+na+nx
            if (actual_nx,actual_na)!=(nx,na) or not 0<count<=131072:raise ValueError('Binary rollout dimensions rejected')
            if path.stat().st_size!=24+count*columns*8:raise ValueError('Binary rollout length differs')
            data=np.fromfile(f,dtype='<f8',count=count*columns).reshape(count,columns)
        else:data=None
    if data is None:data=np.loadtxt(path,delimiter=',',skiprows=1,ndmin=2)
    if data.shape[1]!=7+na+nx or len(data)%envs or not np.isfinite(data).all():raise ValueError('Rollout shape/nonfinite values')
    old_logp,old_value,reward,next_value,terminated,truncated,duration=data[:,:7].T
    if not ((duration>0)&(duration<=10000)).all():raise ValueError('Invalid transition duration')
    advantage=np.empty(len(data),dtype=np.float64);carry=np.zeros(envs,dtype=np.float64)
    for i in range(len(data)-1,-1,-1):
        discount=math.pow(gamma,float(duration[i]));decay=math.pow(lam,float(duration[i]));j=i%envs
        delta=reward[i]+discount*(0. if terminated[i] else next_value[i])-old_value[i]
        carry[j]=delta+(0. if terminated[i] or truncated[i] else discount*decay*carry[j]);advantage[i]=carry[j]
    target=advantage+old_value
    mean=0.
    for x in advantage:mean+=float(x)
    mean/=len(data);variance=0.
    for x in advantage:variance+=(float(x)-mean)**2
    variance/=len(data);advantage=(advantage-mean)/math.sqrt(variance+1e-8)
    return {'x':data[:,7+na:], 'z':data[:,7:7+na], 'old_logp':old_logp,
            'old_value':old_value,'advantage':advantage,'target':target}

class Optimizer:
    def __init__(self,device='cuda'):
        if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; no silent CPU fallback')
        self.device=torch.device(device);torch.set_num_threads(1)
        self.dtype=torch.float64
        if self.device.type=='cuda':torch.cuda.init()
    def synchronize(self):
        if self.device.type=='cuda':torch.cuda.synchronize()
    def update(self,cp,rollout,envs,helper):
        self.synchronize();start=time.perf_counter()
        lr,gamma,lam,clip,value_coefficient,entropy,maxnorm,target_kl=cp.config
        arrays=read_rollout(rollout,cp.nx,cp.na,envs,gamma,lam)
        tensors={k:torch.as_tensor(np.ascontiguousarray(v),dtype=self.dtype,device=self.device) for k,v in arrays.items()}
        p=torch.nn.Parameter(torch.as_tensor(cp.parameters.copy(),dtype=self.dtype,device=self.device));m=torch.as_tensor(cp.first.copy(),device=self.device);v=torch.as_tensor(cp.second.copy(),device=self.device)
        an,cn=cp.actor_count,cp.critic_count
        def network(x,params,outputs):
            bias=cp.nx*cp.hidden;head=bias+cp.hidden;tail=head+outputs*cp.hidden
            return F.linear(torch.tanh(F.linear(x,params[:bias].reshape(cp.hidden,cp.nx),params[bias:head])),params[head:tail].reshape(outputs,cp.hidden),params[tail:])
        def logp(x,z):
            mean=network(x,p[:an],cp.na);ls=p[an+cn:]
            a=-2*z;jac=2*(math.log(2.)-z-(a.clamp_min(0)+torch.log1p(torch.exp(-torch.abs(a)))))
            d=(z-mean)*torch.exp(-ls)
            return (-.5*(d*d+1.8378770664093454836)-ls-jac).sum(-1)
        with torch.no_grad():
            err=(logp(tensors['x'],tensors['z'])-tensors['old_logp']).abs().max().item()
            verr=(network(tensors['x'],p[an:an+cn],1).flatten()-tensors['old_value']).abs().max().item()
        if err>=1e-7 or verr>=1e-7:raise ValueError(f'GPU behavior identity failed: logp={err} value={verr}')
        metrics={'policy_loss':0.,'value_loss':0.,'clip_fraction':0.,'gradient_norm':0.,'minibatches':0,'epochs':0,'kl_stopped':False}
        statistics=torch.zeros(4,dtype=self.dtype,device=self.device)
        finite_gradients=torch.ones((),dtype=torch.bool,device=self.device)
        order=np.arange(len(arrays['x']),dtype=np.uint32)
        for epoch in range(cp.epochs):
            with torch.no_grad():
                difference=logp(tensors['x'],tensors['z'])-tensors['old_logp']
                kl=(torch.exp(difference.clamp(-60,60))-1-difference).mean().item()
            if kl>1.5*target_kl:metrics['kl_stopped']=True;break
            cp.shuffle,order=helper.shuffle(cp.shuffle,order)
            for at in range(0,len(order),cp.minibatch):
                idx=torch.as_tensor(order[at:at+cp.minibatch].astype(np.int64),device=self.device)
                x=tensors['x'][idx];z=tensors['z'][idx];adv=tensors['advantage'][idx]
                ratio=torch.exp((logp(x,z)-tensors['old_logp'][idx]).clamp(-60,60));clipped=ratio.clamp(1-clip,1+clip)
                stop=((adv>=0)&(ratio>1+clip))|((adv<0)&(ratio<1-clip))
                ploss=-torch.where(stop,clipped*adv,ratio*adv).mean()
                error=network(x,p[an:an+cn],1).flatten()-tensors['target'][idx]
                vloss=.5*(error*error).mean()
                loss=ploss+value_coefficient*vloss-entropy*p[an+cn:].sum()
                gradient=torch.autograd.grad(loss,p)[0]
                norm=gradient.norm();scale=(maxnorm/norm).clamp(max=1.)
                g=gradient*scale
                with torch.no_grad():
                    finite_gradients.logical_and_(torch.isfinite(g).all())
                    cp.step+=1;m.mul_(.9).add_(g,alpha=.1);v.mul_(.999).addcmul_(g,g,value=.001)
                    b1=1-math.pow(.9,cp.step);b2=1-math.pow(.999,cp.step)
                    p.sub_(lr*(m/b1)/(torch.sqrt(v/b2)+1e-8));p[an+cn:].clamp_(-5,2)
                with torch.no_grad():
                    statistics[0].add_(ploss.detach());statistics[1].add_(vloss.detach());statistics[2].add_(stop.to(self.dtype).mean());statistics[3].copy_(norm)
                metrics['minibatches']+=1
            metrics['epochs']+=1
        with torch.no_grad():
            difference=logp(tensors['x'],tensors['z'])-tensors['old_logp'];metrics['approx_kl']=(torch.exp(difference.clamp(-60,60))-1-difference).mean().item()
        if not finite_gradients.item():raise ValueError('Nonfinite GPU gradient')
        values=statistics.cpu().tolist()
        for k,value in zip(['policy_loss','value_loss','clip_fraction','gradient_norm'],values):metrics[k]=value
        for k in ['policy_loss','value_loss','clip_fraction']:
            if metrics['minibatches']:metrics[k]/=metrics['minibatches']
        cp.parameters=p.detach().cpu().numpy().copy();cp.first=m.cpu().numpy().copy();cp.second=v.cpu().numpy().copy()
        self.synchronize();metrics.update({'optimizerSeconds':time.perf_counter()-start,'device':str(self.device),'dtype':'float64',
                                          'behaviorLogpMaxError':err,'behaviorValueMaxError':verr})
        return metrics
