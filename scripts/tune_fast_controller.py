"""Measure geometric controller parameters on a declared development map."""
import argparse
import json
from pathlib import Path
import time
from fast_engine import FastEngine

def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    results=[];started=time.monotonic()
    with FastEngine(a.library,a.map,a.packs,a.route,horizon=a.horizon) as env:
        for look in (10,20,30,40,50,65):
            for gain in (1.5,3,5,7.5,10):
                env.configure(look,gain,0.35)
                state=env.reset();score=0.;max_cross=0.;start=time.monotonic()
                while not(state.terminated or state.truncated):
                    state=env.step([1,-1,0]);score+=state.reward;max_cross=max(max_cross,state.cross_track)
                row=dict(lookahead=look,gain=gain,finished=bool(state.terminated),finishMs=state.finish_ms,
                    progress=state.progress,maxCrossTrack=max_cross,reward=score,ticks=state.tick,
                    wallSeconds=time.monotonic()-start)
                results.append(row)
                print('CONTROLLER',look,gain,row['finished'],state.finish_ms,round(state.progress,2),flush=True)
                (a.output/'report.json').write_text(json.dumps(dict(cases=results,wallSeconds=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('library','map','packs','route','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--horizon',type=int,default=4500)
    main(p.parse_args())
