#!/usr/bin/env python3
"""Keep a learned actor, reinitialize value head/Adam for the minimum-time objective."""
import argparse
import copy
import json
import math
import struct
from pathlib import Path
import numpy as np
from gpu_ppo import Checkpoint,Helpers


def prepare(source,output,actions,learning_rate=5e-5,gae_lambda=.97,steering_std=.08,actor_model=None,minibatch=None,target_kl=.01):
    helper=Helpers();cp=Checkpoint.load(source,helper)
    original_actions=cp.na;actor=cp.parameters[:cp.actor_count].copy()
    if actor_model is not None:
        data=Path(actor_model).read_bytes()
        if data[:8]!=b'TMPPO001' or len(data)<40:raise ValueError('Invalid actor model')
        version,nx,na,hidden,ns,reserved=struct.unpack_from('<6I',data,8)
        if (version,nx,na,hidden,reserved)!=(1,cp.nx,cp.na,cp.hidden,0):raise ValueError('Actor architecture differs')
        if data[32:32+ns].decode()!=cp.schema:raise ValueError('Actor schema differs')
        if len(data)!=32+ns+len(cp.parameters)*8+8 or helper.checksum(data[:-8])!=struct.unpack_from('<Q',data,len(data)-8)[0]:raise ValueError('Actor checksum/length rejected')
        actor=np.frombuffer(data,dtype='<f8',count=cp.actor_count,offset=32+ns).copy()
        if not np.isfinite(actor).all():raise ValueError('Nonfinite actor')
    critic=cp.parameters[cp.actor_count:cp.actor_count+cp.critic_count].copy();std=cp.parameters[-cp.na:].copy()
    if actions==1 and cp.na==3:
        shared=cp.hidden*(cp.nx+1)
        actor=np.concatenate([actor[:shared],actor[shared+2*cp.hidden:shared+3*cp.hidden],actor[-1:]])
        std=std[-1:];cp.na=1;cp.schema=cp.schema.replace('pedals_direct3','steering_direct1')
    elif actions!=cp.na:raise ValueError('Unsupported action conversion')
    # Retain critic features; only its output is reset, so its hidden layer can learn.
    head=cp.hidden*(cp.nx+1);critic[head:]=0.;critic[-1]=.7
    std[-1]=math.log(steering_std)
    cp.parameters=np.concatenate([actor,critic,std]);cp.first=np.zeros_like(cp.parameters);cp.second=np.zeros_like(cp.parameters);cp.step=0
    if minibatch is not None:
        if minibatch<1:raise ValueError('Invalid minibatch')
        cp.minibatch=minibatch
    cp.config=(learning_rate,1.,gae_lambda,.1,.5,0.,.5,target_kl)
    output=Path(output)
    if output.exists():raise FileExistsError(output)
    output.mkdir(parents=True)
    cp.save(output/'initial.checkpoint',helper);cp.export_policy(output/'initial.tmppo',helper)
    report={'source':str(Path(source).resolve()),'originalActions':original_actions,'actions':cp.na,'hidden':cp.hidden,
            'actorPreserved':True,'actorModel':str(actor_model) if actor_model else None,'onlySteeringHeadSelected':actions==1 and original_actions==3,
            'criticOutputReset':True,'adamResetForNewObjective':True,'learningRate':learning_rate,
            'gamma':1,'clip':.1,'targetKl':target_kl,'minibatch':cp.minibatch,'initialSteeringLatentStd':steering_std,'gaeLambda':gae_lambda}
    (output/'initialization.json').write_text(json.dumps(report,indent=2)+'\n')
    return cp


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--actions',type=int,choices=[1,3],required=True)
    p.add_argument('--learning-rate',type=float,default=5e-5);p.add_argument('--gae-lambda',type=float,default=.97);p.add_argument('--steering-std',type=float,default=.08)
    p.add_argument('--actor-model',type=Path);p.add_argument('--minibatch',type=int);p.add_argument('--target-kl',type=float,default=.01);a=p.parse_args()
    prepare(a.source,a.output,a.actions,a.learning_rate,a.gae_lambda,a.steering_std,a.actor_model,a.minibatch,a.target_kl)

if __name__=='__main__':main()
