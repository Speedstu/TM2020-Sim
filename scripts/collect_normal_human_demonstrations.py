#!/usr/bin/env python3
"""Adapt original raw human-reference inputs by full forward normal simulation.

No state substitutions. Runs that fail are retained as failure evidence and
excluded from successful BC demonstrations.
"""
import json
from pathlib import Path
import numpy as np
from generalist_engine import GeneralistEngine
from prepare_fall_campaign import ROOT,save_json
from run_fast_ppo import steam_packs

BASE=ROOT/'local/training/human-rework-0.70'
LIB=ROOT/'local/training/hybrid-speed-0.58/native/libtm2020_speed.so'


def main():
    inventory=json.loads((BASE/'corpus/inventory.json').read_text());reports=[]
    for i in (1,3,6):
        meta=json.loads((ROOT/f'local/training/fall-campaign-0.52/{i:02d}/map.json').read_text())
        with GeneralistEngine(LIB,map_path=meta['map'],packs=steam_packs(),horizon=5000) as env:
            for entry in inventory['sources']:
                if entry['mapIndex']!=i or not entry['kind'].startswith('leaderboard'):continue
                g=json.loads((Path(entry['directory'])/'decoded-original.json').read_text())['ghosts'][0]
                timeline={}
                for group in g['groups']:
                    for k,c in enumerate(group['ticks']):timeline[group['start_offset_ms']//10+k]=[int(c['gas']),int(c['brake']),max(-1,c['steer']/127)]
                env.reset(g['validationSeed']);states=[];controls=[];splits=[];previous_cp=0
                for t in range((g['declaredMs']+1999)//10):
                    s=env.state
                    if s.reserved or s.terminated or s.truncated:break
                    if t not in timeline and t==0:raise ValueError('Missing race zero input')
                    command=timeline.get(t,controls[-1] if controls else [0,0,0]);states.append(np.array(s.rigid_words,dtype=np.uint32).view(np.float32).copy());controls.append(command)
                    env.step_controls(command,1)
                    if env.state.checkpoints>previous_cp:splits.append([int(env.state.checkpoints),int(env.state.tick)*10]);previous_cp=env.state.checkpoints
                finish=int(env.state.finish_ms) if env.state.finish_ms>=0 else None
                report={'mapIndex':i,'sourceSha256':entry['sha256'],'kind':entry['kind'],'sourceDeclaredMs':g['declaredMs'],
                    'finishMs':finish,'normalInterfaceForwardSimulation':True,'stateSubstitutions':0,'seed':g['validationSeed'],
                    'acceptedForBC':finish is not None and abs(finish-g['declaredMs'])<=100,'checkpointSplits':splits,
                    'sourceHumanOriginIndependentlyVerified':False}
                out=BASE/f'normal-demonstrations/{i:02d}';out.mkdir(parents=True,exist_ok=True)
                temp=out/(entry['kind']+'.tmp.npz');np.savez_compressed(temp,rigid=np.asarray(states),controls=np.asarray(controls,dtype=np.float32));temp.replace(out/(entry['kind']+'.npz'))
                save_json(out/(entry['kind']+'.json'),report);reports.append(report);save_json(BASE/'normal-demonstrations/report.json',{'runs':reports})
                print(json.dumps(report),flush=True)


if __name__=='__main__':main()
