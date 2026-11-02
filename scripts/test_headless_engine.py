"""Exercise cold asset loading, controls, rewind, reset and race completion."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from force_worker_fixture import require
from headless_engine import HeadlessEngine,EngineCommandError


def digest(state):
    return hashlib.sha256(json.dumps({k:v for k,v in state.items() if k!="advancedTicks"},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()


def main(args):
    require(not args.output.exists(),"Headless validation never overwrites retained evidence")
    args.output.mkdir(parents=True);results=[];started=time.perf_counter()
    for index,map_path in enumerate(args.maps):
        began=time.perf_counter()
        with HeadlessEngine(args.host,map_path,args.packs,args.output/f"host-{index}.log",seed=2026,extension_sha256=args.extension_sha256) as engine:
            initial=digest(engine.state);initial_position=engine.state["position"]
            engine.step([1,0,0],20);checkpoint=engine.save();saved=digest(engine.state)
            engine.step([1,0,.15],20);branch=digest(engine.state)
            engine.restore(checkpoint);require(digest(engine.state)==saved,"Checkpoint state differs")
            engine.step([1,0,.15],20);require(digest(engine.state)==branch,"Checkpoint future differs")
            engine.release(checkpoint);engine.reset();require(digest(engine.state)==initial,"Cold initial reset differs")
            rejected=0
            for command in (dict(op="step",controls=[2,0,0],ticks=5),dict(op="step",controls=[1,0,0],ticks=1001),
                dict(op="restore",id=999999),dict(op="state",unknown=True)):
                try:engine.request(command)
                except EngineCommandError:rejected+=1
                else:raise AssertionError("Invalid host command was accepted: "+str(command))
                require(digest(engine.request(dict(op="state")))==initial,"Rejected command changed state")
            route=[]
            for _ in range(100):
                state=engine.step([1,0,0],50);route.append(dict(tick=state["tick"],position=state["position"],
                    checkpoints=state["checkpointsPassed"],finished=state["finished"]))
                if state["finished"]:break
            require(engine.state["position"]!=initial_position,"Gas did not move the cold-loaded car")
            final=digest(engine.state);ticks=engine.state["tick"]
            engine.reset()
            while engine.state["tick"]<ticks:engine.step([1,0,0],min(50,ticks-engine.state["tick"]))
            require(digest(engine.state)==final,"Repeated full rollout differs after reset")
            results.append(dict(map=str(engine.map),mapSha256=engine.map_sha256,hostSha256=engine.host_sha256,
                coldLoaded=True,checkpointBranchBitExact=True,resetBitExact=True,repeatRolloutBitExact=True,
                invalidCommandsRejected=rejected,rolloutTicks=ticks,finished=engine.state["finished"],
                finishTimeMs=engine.state["finishTimeMs"],checkpointsPassed=engine.state["checkpointsPassed"],
                initialPosition=initial_position,finalPosition=engine.state["position"],
                observationCount=len(engine.state["observation"]),assetBodyMass=engine.state["assetBodyMass"],
                gravity=engine.state["gravity"],elapsedSeconds=time.perf_counter()-began,route=route))
        print("HEADLESS_COLD_MAP",map_path.name,"ticks",ticks,"finish",results[-1]["finished"],flush=True)
    report=dict(schema="tm2020_headless_engine_validation_v1",maps=results,
        elapsedSeconds=time.perf_counter()-started,sourceGameProcessAccessed=False,openplanetUsed=False,
        sourceSnapshotsRequired=False,originalGameDifferentialPerformed=False,
        completeExactSimulatorQualified=False,generalPolicyQualified=False)
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("host","packs","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--maps",type=Path,nargs="+",required=True)
    p.add_argument("--extension-sha256");main(p.parse_args())
