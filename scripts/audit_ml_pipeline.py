#!/usr/bin/env python3
"""Read-only diagnostics of the current PPO policy; no training/game control."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import numpy as np
import torch
from compare_hybrid_ppo import Policy,frame,quantized,save_json
from gpu_ppo import Checkpoint,Helpers
from robust_ppo import load_weights
from run_fast_ppo import ROOT
from top10_core import API
from vector_physics import VectorPhysics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,default=ROOT/'local/training/top10-20261030/ppo20')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    # best.pt is atomically published; retain the exact inode contents audited.
    shutil.copy2(args.run/'best.pt',args.output/'audited.pt')
    status=json.loads((args.run/'status.json').read_text())
    events=[json.loads(line) for line in (args.run/'evaluations.jsonl').read_text().splitlines()]
    protocol=json.loads((args.run/'protocol.json').read_text())
    period=protocol['decisionTicks']
    torch.set_num_threads(1)
    prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',Helpers())
    model=Policy(prior,'continuous');load_weights(model,args.output/'audited.pt')
    seeds=[99611001,99611002,99611003,99611004]
    counters={'states':0,'sameSteerProbabilitySum':0.,'gasFlipProbabilitySum':0.,
              'brakeFlipProbabilitySum':0.,'steerSaturatedStates':0,
              'tanhSaturatedUnits':0,'tanhUnits':0,'emptyHorizontalRays':0,'horizontalRays':0}
    rewards=[[] for _ in seeds];predictions=[[] for _ in seeds]
    with VectorPhysics(len(seeds),decision_ticks=period,api_path=API) as env,torch.no_grad():
        for i,seed in enumerate(seeds):env.reset(i,seed)
        history=np.tile(frame(env.observations),(1,5));active=np.ones(len(seeds),dtype=bool)
        for _ in range(4000//period):
            if not active.any():break
            x=torch.as_tensor(history,device='cuda');out=model.actor(x)
            hidden=model.actor[1](model.actor[0](x));values=model.critic(x).flatten()
            action=torch.cat(((out[:,:2]>=0).double(),out[:,2:3].tanh()),1).cpu().numpy()
            controls=quantized(action)
            # Exact probability that latent Gaussian steering exploration
            # survives the actual tanh+i8 action mapping as a different bin.
            q=torch.as_tensor(controls[:,2],device='cuda',dtype=torch.float64)
            lo=torch.atanh((q-.5/127).clamp(-1,1))
            hi=torch.atanh((q+.5/127).clamp(-1,1))
            sigma=model.logstd.exp()
            same=.5*(torch.erf((hi-out[:,2])/(sigma*math.sqrt(2)))
                     -torch.erf((lo-out[:,2])/(sigma*math.sqrt(2))))
            flip=torch.sigmoid(-out[:,:2].abs())
            idx=np.flatnonzero(active);ids=torch.as_tensor(idx,device='cuda')
            counters['states']+=len(idx)
            counters['sameSteerProbabilitySum']+=same[ids].sum().item()
            counters['gasFlipProbabilitySum']+=flip[ids,0].sum().item()
            counters['brakeFlipProbabilitySum']+=flip[ids,1].sum().item()
            counters['steerSaturatedStates']+=int((np.abs(action[idx,2])>.99).sum())
            counters['tanhSaturatedUnits']+=int((hidden[ids].abs()>.99).sum().item())
            counters['tanhUnits']+=len(idx)*hidden.shape[1]
            counters['emptyHorizontalRays']+=int((history[idx,-48+15:-48+37]>=.999999).sum())
            counters['horizontalRays']+=len(idx)*22
            for i in idx:predictions[i].append(values[i].item())
            env.step(controls)
            for i in idx:rewards[i].append(env.states[i].reward*.01)
            history[:,:-48]=history[:,48:];history[:,-48:]=frame(env.observations)
            active=np.array([not(s.terminated or s.truncated) for s in env.states[:env.n]])
        trials=[{'seed':seed,'finishMs':int(env.states[i].finish_ms),'steps':len(rewards[i])}
                for i,seed in enumerate(seeds)]
    errors=[]
    for r,v in zip(rewards,predictions):
        target=np.cumsum(np.asarray(r)[::-1])[::-1]
        errors.extend((np.asarray(v)-target).tolist())
    n=counters['states']
    report={'run':str(args.run),'auditedWeightsSha256':hashlib.sha256((args.output/'audited.pt').read_bytes()).hexdigest(),
            'updateAtAudit':status['update'],'bestUpdateAtAudit':status['bestUpdate'],
            'evaluationsSinceBest':sum(e['update']>status['bestUpdate'] for e in events),
            'plateauPhases':status['phase'],'curriculumMinimumBank':status['bankMinimum'],
            'sectionSuccessRate':status['sectionSuccessRate'],'currentBankFraction':status['bankFraction'],
            'decisionMs':period*10,'trials':trials,'states':n,'steerLatentSigma':model.logstd.exp().item(),
            'steerQuantizationUnchangedProbabilityMean':counters['sameSteerProbabilitySum']/n,
            'steerAboveAbs099Fraction':counters['steerSaturatedStates']/n,
            'expectedPedalFlipsAlongFourDeterministicRaces':{
                'gas':counters['gasFlipProbabilitySum'],'brake':counters['brakeFlipProbabilitySum']},
            'hiddenTanhAbsAbove099Fraction':counters['tanhSaturatedUnits']/counters['tanhUnits'],
            'horizontalRayMaxRangeFraction':counters['emptyHorizontalRays']/counters['horizontalRays'],
            'criticRmseVsDeterministicMonteCarlo':float(np.sqrt(np.mean(np.square(errors)))),
            'gaeTerminalCoefficientAfter20s':.995**(2000/period),
            'rewardTradeoffAt24s':{'returnFinish':76,'returnFailure':-140,
                'oneSecondSaved':1,'extraFailureProbabilityCancellingOneSecondGain':1/217},
            'limits':['Four new nominal seeds only; no robust performance claim.',
                'Exploration probabilities evaluated on deterministic states, not stochastic occupancy.',
                'Critic predicts stochastic-policy value; deterministic MC discrepancy alone is not a bug.',
                'Diagnostics do not identify causal performance bottlenecks without matched ablations.'],
            'trainingChanged':False,'gameAccessed':False}
    save_json(args.output/'report.json',report);print(json.dumps(report))


if __name__=='__main__':main()
