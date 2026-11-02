"""Offline imitation teacher; reference controls are never policy observations."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from fast_engine import FastEngine
from run_fast_ppo import LIBRARY, ROOT, steam_packs


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    data=np.genfromtxt(a.reference,delimiter=',',skip_header=1)
    progress=np.maximum.accumulate(data[:,29])
    reports=[]
    with FastEngine(LIBRARY,ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx',steam_packs(),
                    ROOT/'local/replays/tmtas-4634.Replay.Gbx',horizon=4000) as env:
        env.configure(10,3,1.5)
        with (a.output/'teacher.csv').open('x') as stream:
            writer=csv.writer(stream);writer.writerow([f'observation_{i}' for i in range(48)]+['steer','baseline','race_ms'])
            for trial in range(a.trials):
                state=env.reset(2026+trial)
                while not(state.terminated or state.truncated):
                    x=np.array(state.observation)
                    index=int(np.searchsorted(progress,x[29]))
                    index=max(0,min(index,len(data)-1))
                    if index>0 and abs(progress[index-1]-x[29])<abs(progress[index]-x[29]):index-=1
                    ref=data[index]
                    # The target local lookahead includes the expert's drift
                    # attitude, unlike pursuit of the path tangent alone.
                    steering=ref[48]-a.gain*(x[9]-ref[9])*50-a.damping*(x[4]-ref[4])*10
                    steering=max(-1.,min(1.,steering))
                    writer.writerow([*x,steering,x[31],state.tick*10])
                    if trial and 10<=state.tick//5<13:
                        steering=max(-1.,min(1.,steering+(.1 if trial%2 else -.1)))
                    state=env.step_controls([1,0,round(steering*127)/127],5)
                row=dict(trial=trial,gain=a.gain,damping=a.damping,finished=bool(state.terminated),finishMs=state.finish_ms,progress=state.progress)
                reports.append(row);print(row,flush=True)
        (a.output/'report.json').write_text(json.dumps(reports,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path,default=ROOT/'local/recon/fast-0.37/demonstrations-v3/fit.csv')
    p.add_argument('--gain',type=float,default=.15)
    p.add_argument('--damping',type=float,default=0.)
    p.add_argument('--trials',type=int,default=3)
    main(p.parse_args())
