"""Causal route-state demonstrations, replayed by native physics from race zero.

Recorded controls supply offline supervised targets only. They are excluded
from policy observations except the declared previous actually applied action.
Separate replay files are retained for fit, validation and final test.
"""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess

from fast_engine import FastEngine


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    reports=[]
    with FastEngine(a.library,a.map,a.packs,a.route,horizon=4500) as root:
        root.configure(a.lookahead,a.gain,a.residual)
        for replay in a.replays:
            metadata=json.loads(subprocess.check_output([str(a.tape_tool.resolve()),'info',str(replay.resolve())]))
            text=subprocess.check_output([str(a.tape_tool.resolve()),'dump',str(replay.resolve())],text=True)
            controls={int(r['race_ms']):[float(r['gas']),float(r['brake']),int(r['steer_i8'])/127]
                      for r in csv.DictReader(io.StringIO(text))}
            require(all(t in controls for t in range(0,metadata['declaredMs']//10*10,10)), 'Partial input history')
            with FastEngine(a.library,clone=root) as env:
                state=env.reset(a.seed)
                name=replay.name+'.route32.csv';count=0;outside=0
                with (a.output/name).open('x',newline='') as stream:
                    writer=csv.writer(stream)
                    writer.writerow([f'observation_{i}' for i in range(32)]+['steer','baseline','race_ms'])
                    while not(state.terminated or state.truncated):
                        t=state.tick*10
                        require(t in controls,'Demonstration ended before a real finish')
                        c=controls[t]
                        if state.tick%a.repeat==0:
                            writer.writerow(list(state.observation)+[c[2],state.observation[31],t]);count+=1
                            outside+=abs((c[2]-state.observation[31])/a.residual)>1
                        state=env.step_controls(c,1)
                require(state.terminated and state.finish_ms==metadata['declaredMs'],
                        f'Demonstration diverged: {state.finish_ms} vs {metadata["declaredMs"]}')
                row=dict(replay=str(replay.resolve()),file=name,rows=count,finishMs=state.finish_ms,
                         referenceControlsOutsideResidual=outside,controlsUsedAsSupervisedTargetsOnly=True)
                reports.append(row);print('DEMONSTRATION',replay.name,count,state.finish_ms,'outside',outside,flush=True)
    (a.output/'report.json').write_text(json.dumps(dict(replays=reports,lookahead=a.lookahead,gain=a.gain,
        residual=a.residual,repeat=a.repeat,seed=a.seed),indent=2)+'\n')


def require(ok,message):
    if not ok:raise AssertionError(message)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('library','map','packs','route','tape-tool','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--replays',type=Path,nargs='+',required=True)
    p.add_argument('--lookahead',type=float,default=10)
    p.add_argument('--gain',type=float,default=3)
    p.add_argument('--residual',type=float,default=.35)
    p.add_argument('--repeat',type=int,default=5)
    p.add_argument('--seed',type=int,default=29120025)
    main(p.parse_args())
