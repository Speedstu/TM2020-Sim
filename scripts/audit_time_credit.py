#!/usr/bin/env python3
"""Audit complete returns and abrupt speed losses, without changing physics."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
from compare_hybrid_ppo import Policy, frame, quantized, save_json
from gpu_ppo import Checkpoint, Helpers
from robust_ppo import load_weights, trial_suite
from ppo_time_credit import potential
from vector_physics import VectorPhysics
from run_fast_ppo import ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stochastic-sigmas',type=float,nargs='*',default=[])
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1)
    helpers=Helpers();prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',helpers)
    model=Policy(prior,'continuous');load_weights(model,args.source)
    trials=[c for c in trial_suite(85200,256) if c['group']=='nominal']
    report={'source':str(args.source),'lossEventsAreKinematicCandidatesNotVerifiedContacts':True,'modes':{}}
    with VectorPhysics(len(trials)) as env:
        modes=['idle','straight','policy']+['noise-'+str(s) for s in args.stochastic_sigmas]
        for mode in modes:
            if mode.startswith('noise-'):
                sigma=float(mode[6:])
                if not 0.<sigma<=1.:raise ValueError('Invalid latent sigma')
                with torch.no_grad():model.logstd.fill_(float(np.log(sigma)))
                torch.manual_seed(85801)
            for i,c in enumerate(trials):env.reset(i,c['seed'])
            history=np.tile(frame(env.observations),(1,5));active=np.ones(env.n,dtype=bool)
            raw_return=np.zeros(env.n);shaped_return=np.zeros(env.n);events=[]
            phi=potential(env.observations)
            initial_phi=phi.copy();maxspeed=np.zeros(env.n)
            for step in range(800):
                if not active.any():break
                if mode=='policy' or mode.startswith('noise-'):
                    with torch.no_grad():actions=model.action(torch.as_tensor(history,device='cuda'),mode=='policy')[0].cpu().numpy()
                else:
                    actions=np.zeros((env.n,3));actions[:,0]=float(mode=='straight')
                controls=quantized(actions);speed=np.array([s.speed for s in env.states[:env.n]])
                positions=np.asarray([list(s.rigid_words)[9:12] for s in env.states[:env.n]],dtype=np.uint32).view(np.float32)
                near_front=np.minimum(env.observations[:,20],env.observations[:,31])*80.
                was_active=active.copy();env.step(controls)
                after=np.array([s.speed for s in env.states[:env.n]]);maxspeed=np.maximum(maxspeed,after)
                ended=np.array([bool(s.terminated or s.truncated) for s in env.states[:env.n]])
                new_phi=potential(env.observations)
                new_phi=np.where(ended,0.,new_phi)
                rewards=np.array([s.reward for s in env.states[:env.n]])
                raw_return+=np.where(was_active,rewards,0.)
                shaped_return+=np.where(was_active,rewards+new_phi-phi,0.)
                for i in np.flatnonzero(was_active & ~ended & (speed-after>4.) & (controls[:,1]==0)):
                    events.append({'trial':int(i),'seed':trials[i]['seed'],'timeMs':step*50,
                                   'lossMps':float(speed[i]-after[i]),'beforeMps':float(speed[i]),
                                   'afterMps':float(after[i]),'frontRayMeters':float(near_front[i]),
                                   'position':positions[i].tolist()})
                phi=new_phi;active=~ended
                history[:,:-48]=history[:,48:];history[:,-48:]=frame(env.observations)
            if active.any():raise AssertionError('Race exceeded finite horizon')
            finishes=np.array([s.finish_ms for s in env.states[:env.n]])
            expected=np.where(finishes>=0,100.-finishes/1000.,-140.)
            np.testing.assert_allclose(raw_return,expected,atol=1e-9,rtol=0)
            np.testing.assert_allclose(shaped_return+initial_phi,raw_return,atol=1e-9,rtol=0)
            item={'finishes':int(np.sum(finishes>=0)),'count':env.n,'returns':raw_return.tolist(),
                  'finishMs':[int(t) if t>=0 else None for t in finishes],
                  'potentialReturnIdentityMaxError':float(np.max(np.abs(shaped_return+initial_phi-raw_return))),
                  'maxSpeedMps':maxspeed.tolist(),'abruptSpeedLossCount':len(events),
                  'largestLosses':sorted(events,key=lambda e:-e['lossMps'])[:12]}
            report['modes'][mode]=item;save_json(args.output/'report.json',report)
            print(json.dumps({'mode':mode,'finishes':item['finishes'],'count':env.n,
                              'meanReturn':float(raw_return.mean()),'abruptLosses':len(events),
                              'potentialIdentityError':item['potentialReturnIdentityMaxError']}),flush=True)


if __name__=='__main__':main()
