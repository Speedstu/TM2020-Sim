"""DAgger states from learner/physical-planner mixtures; causal inference data."""
import argparse
import csv
import json
from pathlib import Path
import random
import time

from fast_engine import FastEngine
from owned_ppo import OwnedPolicy
from run_fast_ppo import LIBRARY, ROOT, steam_packs
from select_fast_policy import SCHEMA


def main(a):
    if not 0<=a.mixture<=1:raise ValueError('Mixture must be in [0,1]')
    a.output.mkdir(parents=True,exist_ok=False)
    policy=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',a.model,SCHEMA,48,1)
    reports=[];rng=random.Random(a.seed);started=time.monotonic()
    try:
        with FastEngine(LIBRARY,ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx',steam_packs(),
                        ROOT/'local/replays/tmtas-4634.Replay.Gbx',horizon=3500) as plain:
            plain.configure(10,3,1.5)
            with FastEngine(LIBRARY,clone=plain) as teacher:
                teacher.planner()
                with (a.output/'teacher.csv').open('x') as stream:
                    writer=csv.writer(stream);writer.writerow([f'observation_{i}' for i in range(48)]+['steer','baseline','race_ms'])
                    for trial in range(a.trials):
                        bank=0 if trial%2==0 else 1+rng.randrange(plain.bank_size()-1)
                        seed=a.seed+trial
                        state=plain.reset_bank(seed,bank);target=teacher.reset_bank(seed,bank)
                        rows=0
                        while not(state.terminated or state.truncated):
                            steering=target.observation[31]
                            writer.writerow([*state.observation,steering,state.observation[31],state.tick*10]);rows+=1
                            action,_=policy.predict(list(state.observation))
                            applied=max(-1.,min(1.,state.observation[31]+1.5*action[0])) if rng.random()<a.mixture else steering
                            if rng.random()<.015:applied=max(-1.,min(1.,applied+rng.uniform(-.15,.15)))
                            controls=[1.,0.,round(applied*127)/127]
                            state=plain.step_controls(controls,5);target=teacher.step_controls(controls,5)
                            if list(state.rigid_words)!=list(target.rigid_words):raise AssertionError('Teacher forecasts changed actual physics')
                        row=dict(trial=trial,bank=bank,seed=seed,rows=rows,finishMs=state.finish_ms,
                                 finished=bool(state.terminated),progress=state.progress,mixture=a.mixture)
                        reports.append(row);stream.flush();print(row,flush=True)
                        (a.output/'report.json').write_text(json.dumps(dict(cases=reports,seconds=time.monotonic()-started),indent=2)+'\n')
    finally:policy.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--mixture',type=float,default=.3)
    p.add_argument('--trials',type=int,default=8)
    p.add_argument('--seed',type=int,default=61026)
    main(p.parse_args())
