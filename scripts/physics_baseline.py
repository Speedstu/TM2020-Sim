#!/usr/bin/env python3
"""Auditable 50ms Trackmania 2020 replay dynamics baseline (NOT an exact game simulator).

Uses existing numpy, no environment or GPU. Data is grouped by full map UID.
Only states DURING the completed race are used. We never evaluate on the same map
as training, and never train on post-finish telemetry. Model predicts one-step
delta speed and delta yaw. Holdout accuracy is compared against zero-delta.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MATERIALS = (
    "Asphalt", "Concrete", "Dirt", "Grass", "Ice", "Metal", "Plastic", "Rubber",
    "Sand", "Wood", "Water", "Turbo", "Other"
)
FEATURE_NAMES = [
    "bias", "speed_x100", "speed2_x1e4", "steer",
    "gas", "brake", "speed*gas", "speed*brake", "speed*steer",
    "abs(steer)*speed", "sideSpeed_x50", "sideSpeed*steer",
    "pitch", "roll", "pitch*speed", "gear_x5", "rpm_x255", "ground",
    "turbo", "wetness", "reac_air_steer_x100", "reactor",
    *[f"surface_{m}" for m in MATERIALS],
]
TARGET_NAMES = ["delta_speed_kmh", "delta_heading_rad"]

def parse_millis(s: str) -> int:
    s = s.lstrip("-")
    minutes, secs = s.split(":")
    whole, frac = (secs.split(".") + ["0"])[:2]
    return int(minutes)*60000 + int(whole)*1000 + int(frac.ljust(3,"0")[:3])

def diff_angle(a: float, b: float) -> float:
    return (b-a+np.pi)%(2*np.pi)-np.pi

def prepare_features(row: dict) -> list[float]:
    v = float(row["speedKmh"])/100
    steer = float(row["recordedControls"]["steer"])
    gas = float(row["recordedControls"]["gas"])
    brake = float(row["recordedControls"]["brake"])
    ss = float(row["sideSpeed"])/50
    pitch, _, roll = map(float, row["euler"])
    mats = row["tire"]["groundMaterials"]
    counts = Counter(m if m in MATERIALS[:-1] else "Other" for m in mats)
    reactor = row["reactor"]
    vec = [
        1, v, v*v, steer,
        gas, brake, gas*v, brake*v, steer*v,
        abs(steer)*v, ss, ss*steer,
        pitch, roll, pitch*v, float(row["gear"])/5,
        float(row["rpmRaw"])/255, float(row["ground"]),
        float(row["turbo"]["active"]), float(row["wetness"]),
        float(reactor["steer"])/100,
        float(reactor["boostLevel"] != "None"),
        *[counts.get(m,0)/4 for m in MATERIALS]
    ]
    assert len(vec) == len(FEATURE_NAMES)
    return vec

def load_all() -> dict:
    manifest = json.loads((ROOT/"local/dataset-manifest.json").read_text(encoding="utf-8-sig"))
    extra_path = ROOT/"local/corpus/manifest.json"
    additions = json.loads(extra_path.read_text(encoding="utf-8-sig"))["pairs"] if extra_path.exists() else []
    datasets={}
    for item in [*manifest["linked"], *additions]:
        data=json.loads((ROOT/item["datasetJson"]).read_text(encoding="utf-8-sig"))
        usable=[g["result"] for g in data["ghosts"] if g["result"].get("stateInputRows")]
        if len(usable)!=1: raise RuntimeError(f"Expected exactly one replay ghost: {item['replayId']}")
        states=usable[0]["stateInputRows"]
        race_end=parse_millis(usable[0]["raceTime"])
        x,y=[],[]
        delta_t=[]
        for prev,nxt in zip(states,states[1:]):
            if nxt["tMs"] > race_end: continue
            dt=nxt["tMs"]-prev["tMs"]
            if dt != 50: continue
            x.append(prepare_features(prev))
            y.append([
                float(nxt["speedKmh"])-float(prev["speedKmh"]),
                diff_angle(float(prev["euler"][1]),float(nxt["euler"][1])),
            ])
            delta_t.append(dt)
        if len(x)<5: raise RuntimeError("Too few data after filtering")
        if item["mapUid"] in datasets: raise RuntimeError(f"Duplicate map UID: {item['mapUid']}")
        datasets[item["mapUid"]]={"x":np.asarray(x,dtype=np.float64),"y":np.asarray(y,dtype=np.float64),
                                  "raceMs":race_end,"replayId":item["replayId"],"tmxId":item["tmxId"],
                                  "rows":len(x),"postFinishFiltered":max(0,len(states)-1-len(x))}
    if len(datasets)<3:raise RuntimeError("Need at least 3 distinct maps to evaluate generalization")
    return datasets

def fit_model(x,y,alpha=1.):
    # Features are normalized using training set only: no holdout information.
    mean=x.mean(axis=0);std=x.std(axis=0)
    mean[0]=0;std[0]=1
    std[std<1e-8]=1
    xm=(x-mean)/std
    a=xm.T@xm + alpha*np.diag([0]+[1]*(xm.shape[1]-1))
    b=xm.T@y
    weights=np.linalg.solve(a,b)
    return {"mean":mean,"std":std,"weights":weights}

def predict(model,x):
    return ((x-model["mean"])/model["std"])@model["weights"]

def metric(y,pred):
    err=pred-y
    baseline=-y
    return {
        "n": len(y),
        "speedDeltaMAE_kmh":float(np.mean(np.abs(err[:,0]))),
        "speedDeltaRMSE_kmh":float(np.sqrt(np.mean(err[:,0]**2))),
        "headingDeltaMAE_deg":float(np.rad2deg(np.mean(np.abs(err[:,1])))),
        "headingDeltaRMSE_deg":float(np.rad2deg(np.sqrt(np.mean(err[:,1]**2)))),
        "naiveConstantSpeedMAE_kmh":float(np.mean(np.abs(baseline[:,0]))),
        "naiveConstantHeadingMAE_deg":float(np.rad2deg(np.mean(np.abs(baseline[:,1])))),
        "speedBeatsNaive":bool(np.mean(np.abs(err[:,0])) < np.mean(np.abs(baseline[:,0]))),
        "headingBeatsNaive":bool(np.mean(np.abs(err[:,1])) < np.mean(np.abs(baseline[:,1]))),
    }

def main() -> int:
    args=argparse.ArgumentParser()
    args.add_argument("--alpha",type=float,default=10.0)
    args.add_argument("--out",default=str(ROOT/"local/physics_baseline"))
    ns=args.parse_args()
    data=load_all()
    uid=list(data)
    reports=[]
    for k in uid:
        other=[data[u] for u in uid if u!=k]
        train_x=np.concatenate([d["x"] for d in other])
        train_y=np.concatenate([d["y"] for d in other])
        model=fit_model(train_x,train_y,ns.alpha)
        test=data[k]
        report=metric(test["y"],predict(model,test["x"]))
        report.update({"heldOutMapUid":k,"replayId":test["replayId"],
                       "trainMaps":len(other),"trainSamples":len(train_x),
                       "raceMs":test["raceMs"],"postFinishFiltered":test["postFinishFiltered"]})
        reports.append(report)
    x=np.concatenate([d["x"] for d in data.values()])
    y=np.concatenate([d["y"] for d in data.values()])
    all_model=fit_model(x,y,ns.alpha)
    folder=Path(ns.out);folder.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(folder/"regression_50ms.npz",**all_model,
                        features=np.asarray(FEATURE_NAMES),
                        targets=np.asarray(TARGET_NAMES))
    report={
        "schema":"tm2020_50ms_dynamics_baseline_v1",
        "createdUtc": datetime.now(timezone.utc).isoformat(),
        "scope": "offline one-step speed+heading delta prediction from REPLAY telemetry; NOT a real physics simulator",
        "split":"leave-one-map-out, heldout map never used to fit normalizers or weights",
        "alpha":ns.alpha,
        "features":FEATURE_NAMES,
        "sourceMaps":len(uid),"sourceTransitions":len(x),
        "holdout":reports,
        "totalHoldoutEvaluated":sum(r["n"] for r in reports),
        "weightedMeanSpeedMAE":sum(r["speedDeltaMAE_kmh"]*r["n"] for r in reports)/sum(r["n"] for r in reports),
        "weightedNaiveSpeedMAE":sum(r["naiveConstantSpeedMAE_kmh"]*r["n"] for r in reports)/sum(r["n"] for r in reports),
        "weightedMeanYawMAEDeg":sum(r["headingDeltaMAE_deg"]*r["n"] for r in reports)/sum(r["n"] for r in reports),
        "weightedNaiveYawMAEDeg":sum(r["naiveConstantHeadingMAE_deg"]*r["n"] for r in reports)/sum(r["n"] for r in reports),
    }
    (folder/"validation.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("PASS maps=",len(uid),"total transitions=",len(x),
          "speed MAE=",round(report["weightedMeanSpeedMAE"],4),
          "naive=",round(report["weightedNaiveSpeedMAE"],4),
          "yaw MAE deg=",round(report["weightedMeanYawMAEDeg"],4),
          "naive=",round(report["weightedNaiveYawMAEDeg"],4))
    for row in reports:
        print("replay",row["replayId"],"holdout",row["n"],"speedMAE",round(row["speedDeltaMAE_kmh"],4),
              "yawMAEdeg",round(row["headingDeltaMAE_deg"],4),
              "postfinish",row["postFinishFiltered"])
    print("OUTPUT",folder)
    return 0

if __name__=="__main__":sys.exit(main())
