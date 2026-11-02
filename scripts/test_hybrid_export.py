#!/usr/bin/env python3
"""CUDA training -> TMPPO export -> native in-process action decoder parity."""
import json
from pathlib import Path
import subprocess
import time
import numpy as np
import torch
from compare_hybrid_ppo import Policy,ARMS,MASK,quantized
from gpu_ppo import Checkpoint,Helpers
from run_fast_ppo import ROOT

def main():
    output=ROOT/'local/recon/internal-0.46/export-parity';output.mkdir(exist_ok=True)
    helpers=Helpers();prior=Checkpoint.load(ROOT/'local/recon/strength-0.45/ppo-history5-value/run/best.checkpoint',helpers)
    x=np.random.default_rng(46601).normal(0,.3,(256,240));x[:,MASK]=0
    x.astype('<f8').tofile(output/'observations.f64');report={}
    for arm in ARMS:
        model=Policy(prior,arm);weights=ROOT/f'local/recon/internal-0.46/ppo-comparison/46601-{arm}/best.pt'
        if weights.exists():model.load_state_dict(torch.load(weights,weights_only=True))
        temporary=output/(arm+'-'+str(time.time_ns())+'.tmppo')
        model.export(prior,temporary,helpers);temporary.replace(output/(arm+'.tmppo'))
        subprocess.run([str(ROOT/'native/build-linux/tm2020_internal_policy_probe'),str(output/(arm+'.tmppo')),
                        str(output/'observations.f64'),str(output/(arm+'.f32'))],check=True)
        with torch.no_grad():expected=quantized(model.action(torch.tensor(x,device='cuda'),True)[0].cpu().numpy())
        actual=np.fromfile(output/(arm+'.f32'),dtype='<f4').reshape(-1,3)
        if not np.array_equal(actual,expected):raise RuntimeError(f'{arm}: native actions differ from CUDA model')
        report[arm]={'rows':len(x),'bitExactFloatControls':True,'outputs':model.outputs,'trainedWeights':weights.exists()}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
