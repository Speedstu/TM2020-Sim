"""Exercise each explicitly selected installed car; fidelity remains separate."""
import argparse
import hashlib
import json
from pathlib import Path

from force_worker_fixture import require
from headless_engine import HeadlessEngine
from test_headless_engine import digest


def main(args):
    require(not args.output.exists(),"Never overwrite car matrix evidence");args.output.mkdir(parents=True)
    rows=[]
    # Current installed assets select legacy force model 1 for all three classic
    # cars; their vehicle names are not the force-dispatch numeric enum.
    for car,kind in (("CarSport",5),("CarSnow",1),("CarRally",1),("CarDesert",1)):
        with HeadlessEngine(args.host,args.map,args.packs,args.output/(car+".log"),car=car,
                extension_sha256=args.extension_sha256,seed=2026) as engine:
            require(engine.state["assetForceModelKind"]==kind,"Wrong selected force model")
            initial=digest(engine.state)
            plan=[([1,0,0],30),([1,0,.2],20),([1,0,-.2],20),([0,1,0],20),([0,0,0],10)]
            histories=[]
            for trial in range(2):
                engine.reset();trace=[]
                for controls,ticks in plan:
                    trace.append(digest(engine.step(controls,ticks)))
                histories.append(trace)
            require(histories[0]==histories[1],"Car control history changed after reset")
            engine.reset();require(digest(engine.state)==initial,"Car initial state changed")
            checkpoint=engine.save();engine.step([1,0,.1],20);future=digest(engine.state)
            engine.restore(checkpoint);engine.step([1,0,.1],20)
            require(digest(engine.state)==future,"Car checkpoint future differs");engine.release(checkpoint)
            engine.reset()
            for _ in range(100):
                engine.step([1,0,0],50)
                if engine.state["finished"]:break
            final=engine.state
            require(final["tick"]>0 and len(final["observation"])==233,"Car simulation did not advance")
            rows.append(dict(car=car,assetForceModelKind=kind,controlledTicks=100,
                mixedControlsExactAcrossReset=True,checkpointFutureExact=True,
                fullGasTicks=final["tick"],finished=final["finished"],finishTimeMs=final["finishTimeMs"],
                position=final["position"],observationCount=233,bodyMass=final["assetBodyMass"],
                originalGameOraclePerformedForThisCar=False))
            print("CAR_MATRIX",car,"kind",kind,"finish",final["finished"],"time_ms",final["finishTimeMs"],flush=True)
    report=dict(schema="tm2020_four_car_cold_engine_matrix_v1",cars=rows,
        physicsExtensionSha256=args.extension_sha256,hostSha256=hashlib.sha256(args.host.read_bytes()).hexdigest(),
        mapSha256=hashlib.sha256(args.map.read_bytes()).hexdigest(),
        originalGameDifferentialPerformed=False,completeExactSimulatorQualified=False)
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("host","map","packs","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--extension-sha256",required=True);main(p.parse_args())
