"""Development-only receding-horizon teacher using cloned physical worlds."""
import argparse
import csv
import json
from pathlib import Path
import time
import random

from fast_engine import FastEngine
from run_fast_ppo import LIBRARY, ROOT, steam_packs
from owned_ppo import OwnedPolicy
from select_fast_policy import SCHEMA


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    policy=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',a.model,SCHEMA,48,1) if a.model else None
    rng=random.Random(a.seed+a.trial)
    with FastEngine(LIBRARY,ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx',steam_packs(),
                    ROOT/'local/replays/tmtas-4634.Replay.Gbx',horizon=4000) as env:
        env.configure(10,3,1.5)
        state=env.reset(a.seed+a.trial)
        with (a.output/'teacher.csv').open('x') as stream:
            writer=csv.writer(stream)
            writer.writerow([f'observation_{i}' for i in range(48)]+['steer','baseline','race_ms'])
            while not(state.terminated or state.truncated):
                best=(float('inf'),0.)
                for i in range(17):
                    steer=(i-8)/8
                    with FastEngine(LIBRARY,clone=env) as future:
                        score=0.
                        for j in range(a.horizon//10):
                            predicted=future.step_controls([1,0,round(steer*127)/127],10)
                            x=predicted.observation
                            dx=x[9]*50-x[21]*10;dz=x[11]*50-x[23]*10
                            norm=max(.1,(dx*dx+dz*dz)**.5)
                            perpendicular=(x[0]*100*dz-x[2]*100*dx)/norm
                            score+=predicted.cross_track**2 + a.velocity*perpendicular**2
                            if predicted.terminated:score-=10000;break
                            if predicted.truncated:score+=10000;break
                        score-=a.progress*(predicted.progress-state.progress)
                        score+=.01*(steer-state.controls[2])**2
                    if score<best[0]:best=(score,steer)
                writer.writerow([*state.observation,best[1],state.observation[31],state.tick*10])
                applied=best[1]
                if policy and rng.random()<a.mixture:
                    action,_=policy.predict(list(state.observation))
                    applied=max(-1.,min(1.,state.observation[31]+1.5*action[0]))
                if a.trial and 10<=state.tick//5<13:
                    applied=max(-1.,min(1.,applied+(.15 if a.trial%2 else -.15)))
                state=env.step_controls([1,0,round(applied*127)/127],5)
                if state.tick%100==0:print('TEACHER',state.tick,round(state.progress,1),round(state.cross_track,2),best[1],flush=True)
        report=dict(finishMs=state.finish_ms,finished=bool(state.terminated),progress=state.progress,
                    ticks=state.tick,seconds=time.monotonic()-start,searchUsesPhysicalClones=True,
                    horizon=a.horizon,velocityCost=a.velocity,progressCost=a.progress,trial=a.trial,seed=a.seed+a.trial)
        (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(report)
    if policy:policy.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--horizon',type=int,default=40)
    p.add_argument('--velocity',type=float,default=.15)
    p.add_argument('--progress',type=float,default=1.)
    p.add_argument('--trial',type=int,default=0)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--model',type=Path)
    p.add_argument('--mixture',type=float,default=.5)
    main(p.parse_args())
