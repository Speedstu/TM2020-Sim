"""Meaningful ABI, isolation, causality and reset tests on installed maps."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import hashlib
import json
from pathlib import Path

from fast_engine import FastEngine,State


def require(ok,message):
    if not ok:raise AssertionError(message)


def main(a):
    a.output.mkdir(parents=True,exist_ok=False)
    with FastEngine(a.library,a.map,a.packs,a.route,horizon=4000) as root:
        require(root.version==4,'Unexpected physics task/ABI version')
        require(C.sizeof(root.state_type)==544,'Unexpected native ABI size')
        require(root.bank_size()>10,'Missing complete replay reset states')
        root.configure(10,3,1.5)
        def trial(_):
            with FastEngine(a.library,clone=root) as env:
                state=env.reset(29120025);initial=bytes(state)
                # Rejected commands must neither advance physics nor latch failure.
                for action,repeat in [([1,-1,float('nan')],5),([1,-1,2],5),([1,-1,0],0)]:
                    try:env.step(action,repeat)
                    except RuntimeError:pass
                    else:raise AssertionError('Invalid native command accepted')
                    require(bytes(env.state)==initial,'Invalid action changed output state')
                def drive():
                    digest=hashlib.sha256()
                    for t in range(200):
                        state=env.step([1,-1,0.02 if t%17<8 else -0.02],5)
                        digest.update(bytes(state))
                    return digest.hexdigest()
                first=drive();require(bytes(env.reset(29120025))==initial,'Reset state differs')
                second=drive();require(first==second,'Reset did not replay exact physics and features')
                saved=bytes(env.reset_bank(29120025,5))
                require(env.state.tick>=400,'Snapshot did not restore race time')
                bank_trace=drive()
                require(bytes(env.reset_bank(29120025,5))==saved,'Snapshot reset differs')
                require(drive()==bank_trace,'Snapshot physical continuation differs')
                return first
        sequential=trial(0)
        with ThreadPoolExecutor(max_workers=4) as workers:
            parallel=list(workers.map(trial,range(4)))
        require(all(x==sequential for x in parallel),'Parallel worlds share mutable state')
        with FastEngine(a.library,clone=root) as ordinary,FastEngine(a.library,clone=root) as planned:
            planned.planner()
            left=ordinary.reset(29120025);right=planned.reset(29120025)
            def physical_equal():
                a=root.state_type.from_buffer_copy(bytes(left));b=root.state_type.from_buffer_copy(bytes(right))
                a.observation[31]=b.observation[31]=0.
                require(bytes(a)==bytes(b),'Planning mutated real vehicle state or causal features')
            physical_equal()
            for i in range(8):
                controls=[1,0,(i%3-1)/127]
                left=ordinary.step_controls(controls,5);right=planned.step_controls(controls,5)
                physical_equal()
    with FastEngine(a.library,a.map,a.packs,a.route,horizon=7) as env:
        env.configure(10,3,1.5);env.reset()
        initial=bytes(env.state)
        try:env.reset_bank(2026,1)
        except RuntimeError:pass
        else:raise AssertionError('Accepted a reset snapshot beyond the episode horizon')
        require(bytes(env.state)==initial,'Rejected snapshot reset changed the world')
        state=env.step([1,-1,0],5);require(state.tick==5 and state.advanced_ticks==5,'Initial action duration differs')
        state=env.step([1,-1,0],5);require(state.tick==7 and state.advanced_ticks==2 and state.truncated,'Partial final action differs')
        try:env.step([1,-1,0],5)
        except RuntimeError:pass
        else:raise AssertionError('Stepped a completed episode')
        env.reset();require(env.step([1,-1,0],1).tick==1,'Reset did not clear completed state')
    report=dict(schema='tm2020_fast_environment_checks_v1',rejectedCommandsDoNotAdvance=True,
                repeatedResetBitsEqual=True,parallelCloneIsolation=True,completeReplaySnapshotResetExact=True,parallelWorlds=4,
                finalPartialRepeatCorrect=True,continuedAfterDoneRejected=True,
                forecastsDoNotChangeActualPhysics=True,deterministicTraceSha256=sequential)
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS FAST_ENVIRONMENT_ISOLATION_RESET_AND_BOUNDARIES')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('library','map','packs','route','output'):p.add_argument('--'+name,type=Path,required=True)
    main(p.parse_args())
