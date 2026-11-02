#!/usr/bin/env python3
"""Explicitly run a campaign candidate in the user's offline current map.

Defaults to printing the exact command. --run is required to touch the game.
Simulation reports are not evidence of an in-game arrival or world rank.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import numpy as np
from hybrid_tracking import load_asset
from prepare_fall_campaign import OUT
from run_fast_ppo import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('map',type=int,choices=range(1,26))
    p.add_argument('--campaign',type=Path,default=OUT);p.add_argument('--output',type=Path)
    p.add_argument('--run',action='store_true');a=p.parse_args()
    d=a.campaign/f'{a.map:02d}';m=json.loads((d/'map.json').read_text())
    r=json.loads((d/'result.json').read_text());model=Path(r['model'])
    if hashlib.sha256(model.read_bytes()).hexdigest()!=r['modelSha256']:raise ValueError('Model changed after qualification')
    ref,_,_=load_asset(model,map_path=m['map'],uid=m['mapUid'])
    ref0=np.fromfile(d/'reference.f32',dtype='<f4').reshape(-1,25)[0]
    output=a.output or ROOT/f'local/recon/campaign-user-tests/{a.map:02d}'
    command=[sys.executable,str(ROOT/'scripts/run_internal_trial.py'),'--map',m['map'],'--map-uid',m['mapUid'],
        '--spawn',*map(str,ref0[9:12]),'--model',str(model),'--deployment',str(ROOT/'local/recon/deployment-0.52'),
        '--seconds',str(min(115,len(ref)*.01+8)),'--output',str(output),'--capture']
    print('Simulation qualification:',json.dumps({k:r[k] for k in ('nominal64','perturbed64','simGoalPassed')}))
    print(shlex.join(command),flush=True)
    if a.run:subprocess.run(command,check=True)


if __name__=='__main__':main()
