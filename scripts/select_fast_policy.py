"""Select imitation candidates by complete development races, not row MSE."""
import argparse
import json
from pathlib import Path
import shutil
from fast_engine import FastEngine
from owned_ppo import OwnedPolicy
from run_fast_ppo import LIBRARY, ROOT, steam_packs

SCHEMA='tm2020_fast_route48_v3|controls=binary_pedals_i8_steer|controller=geometric_residual_v2|policy_actions=steering_residual1'


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    results=[];best=None
    with FastEngine(LIBRARY,ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx',steam_packs(),
                    ROOT/'local/replays/tmtas-4634.Replay.Gbx',horizon=4000) as env:
        env.configure(10,3,1.5)
        for model in sorted(a.candidates.glob('*.tmppo')):
            policy=OwnedPolicy(ROOT/'native/build-linux/libtm2020_policy.so',model,SCHEMA,48,1)
            finishes=[]
            for trial in range(a.trials):
                state=env.reset(52026+trial)
                if trial:
                    for _ in range(10):state=env.step([1,-1,0],5)
                    for _ in range(3):state=env.step([1,-1,.15 if trial%2 else -.15],5)
                while not(state.terminated or state.truncated):
                    action,_=policy.predict(list(state.observation))
                    state=env.step([1,-1,action[0]],5)
                finishes.append(state.finish_ms)
            policy.close()
            count=sum(t>=0 for t in finishes);mean=sum(t for t in finishes if t>=0)/count if count else 1e9
            key=(count,-mean)
            row=dict(model=str(model),finishes=finishes,meanMs=mean);results.append(row)
            if best is None or key>best:
                best=key;shutil.copyfile(model,a.output/'best.tmppo')
                (a.output/'best.json').write_text(json.dumps(row,indent=2)+'\n')
            print(row,flush=True)
            (a.output/'report.json').write_text(json.dumps(dict(cases=results,developmentSelection=True,testUsed=False),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--candidates',type=Path,required=True)
    p.add_argument('--trials',type=int,default=3)
    main(p.parse_args())
