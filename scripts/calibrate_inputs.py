#!/usr/bin/env python3
"""Calibrate how the recorded 10ms Trackmania input events align with 50ms vehicle state.

Do NOT call the result a perfect 100Hz physics input reader: states are sampled
at ~20Hz and only observations at those instants are directly checked.
Uses held-out map UIDs to validate offset and signed steering mapping.
"""
from __future__ import annotations
import bisect
import json
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"sdk"))
from trackmania2020 import ReplayCorpus

def infer(pair,shift:int):
    rows=pair.trajectory.data
    input_events=pair.trajectory.input_timeline
    if not input_events:return None
    clock=np.array([int(e["tMs"]) for e in input_events],dtype=np.int64)
    steer=np.zeros(len(clock),dtype=np.float64)
    gas=np.zeros(len(clock),dtype=bool)
    brake=np.zeros(len(clock),dtype=bool)
    s=0.0;g=False;b=False
    for i,e in enumerate(input_events):
        if e["steerRaw"] is not None:s=float(e["steerRaw"])
        if e["gas"] is not None:g=bool(e["gas"])
        if e["brake"] is not None:b=bool(e["brake"])
        steer[i]=s;gas[i]=g;brake[i]=b
    race=pair.trajectory.race_ms
    valid=[r for r in rows if int(r["tMs"])<=race]
    if len(valid)<5:return None
    original=np.array([float(r["recordedControls"]["steer"]) for r in valid],dtype=np.float64)
    actual_gas=np.array([float(r["recordedControls"]["gas"])>=0.5 for r in valid],dtype=bool)
    actual_brake=np.array([float(r["recordedControls"]["brake"])>=0.5 for r in valid],dtype=bool)
    rt=np.array([int(r["tMs"])+shift for r in valid],dtype=np.int64)
    indices=np.searchsorted(clock,rt,side="right")-1
    inferred_s=np.where(indices>=0,steer[np.maximum(0,indices)],0)
    inferred_gas=np.where(indices>=0,gas[np.maximum(0,indices)],False)
    inferred_brake=np.where(indices>=0,brake[np.maximum(0,indices)],False)
    return dict(raw=inferred_s,steer=original,
                gasMismatch=np.count_nonzero(inferred_gas!=actual_gas),
                brakeMismatch=np.count_nonzero(inferred_brake!=actual_brake),
                count=len(valid))

def fit_params(samples):
    x=np.concatenate([s["raw"] for s in samples])
    y=np.concatenate([s["steer"] for s in samples])
    A=np.stack([x,np.ones_like(x)],axis=1)
    a,b=np.linalg.lstsq(A,y,rcond=None)[0]
    return float(a),float(b)

def eval_samples(samples,a,b):
    count=sum(s["count"] for s in samples)
    absolute=sum(np.abs(s["steer"]-(s["raw"]*a+b)).sum() for s in samples)
    ng=sum(s["gasMismatch"] for s in samples)
    nb=sum(s["brakeMismatch"] for s in samples)
    return {
        "count":count,
        "steerMAE":float(absolute/count),
        "steerWithinOne255":float(
            sum(np.count_nonzero(np.abs(s["steer"]-(s["raw"]*a+b)) <= 1/255+1e-6)
                for s in samples)/count),
        "gasMismatchSamples":int(ng),"brakeMismatchSamples":int(nb),
        "pedalMismatchFraction":float((ng+nb)/(2*count)),
        "combinedScore":float(absolute/count + (ng+nb)/count*.25)
    }

def main():
    corpus=ReplayCorpus(ROOT)
    train,test=corpus.group_split(0.2)
    train_pairs=[corpus.by_index(i) for i in train]
    test_pairs=[corpus.by_index(i) for i in test]
    candidates=[]
    for shift in range(-60,61,10):
        samples=[infer(pair,shift) for pair in train_pairs]
        samples=[s for s in samples if s is not None]
        ls_a,ls_b=fit_params(samples)
        models=[
            ("fitted_least_squares",ls_a,ls_b),
            ("signed_8bit_2x_minus_1_over_255",2/255,-1/255),
            ("signed_8bit_x_over_127",1/127,0),
        ]
        choice=[]
        for name,model_a,model_b in models:
            metrics=eval_samples(samples,model_a,model_b)
            choice.append(dict(formula=name,shiftMs=shift,steerRawScale=model_a,steerRawBias=model_b,**metrics))
        candidates.extend(choice)
    best=min(candidates,key=lambda s:s["combinedScore"])
    a,b=best["steerRawScale"],best["steerRawBias"]
    heldout=[s for pair in test_pairs if (s:=infer(pair,best["shiftMs"])) is not None]
    heldout_metrics=eval_samples(heldout,a,b)
    exact_formula=eval_samples(heldout,2/255,-1/255)
    naive_formula=eval_samples(heldout,1/127,0)
    all_canonical=[s for pair in [*train_pairs,*test_pairs] if (s:=infer(pair,best["shiftMs"])) is not None]
    out={
        "schema":"tm2020_recorded_controls_input_timing_v1",
        "scope":"replay 10ms input events aligned to *50ms sampled* CSceneVehicleVis controls",
        "trainMapCount":len(train),"heldoutMapCount":len(test),
        "chosenEventOffsetShiftMs":best["shiftMs"],
        "trainChosenSteerFormula":best["formula"],
        "trainFitRawSteerScale":a,"trainFitRawSteerBias":b,
        "preferredTrainingMetrics":{k:v for k,v in best.items() if k not in ("steerRawScale","steerRawBias")},
        "heldoutFitMetrics":heldout_metrics,
        "heldoutReferenceFormula2xMinus1Over255":exact_formula,
        "heldoutReferenceFormulaRawOver127":naive_formula,
        "canonicalAllMapsMetrics":eval_samples(all_canonical,2/255,-1/255),
        "candidateTimingShifts":[{k:v for k,v in x.items() if k in ("formula","shiftMs","steerMAE","gasMismatchSamples","brakeMismatchSamples","combinedScore")} for x in candidates],
        "warning":"Inferred 50ms synchronization is not proof of 100Hz tick-perfect replay/control timing."
    }
    p=ROOT/"local"/"input_calibration.json"
    p.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print("INPUTS maps train",len(train),"test",len(test),"best offset",best["shiftMs"],"ms","formula",best["formula"])
    print("  learned steer =",round(a,9),"* raw +",round(b,9))
    print("  heldout steerMAE",round(heldout_metrics["steerMAE"],7),
          "within 1/255",round(heldout_metrics["steerWithinOne255"],4),
          "gas mismatch",heldout_metrics["gasMismatchSamples"],
          "brake mismatch",heldout_metrics["brakeMismatchSamples"])
    print("  ref [2x-1]/255 heldoutMAE",round(exact_formula["steerMAE"],7),
          "naive raw/127 heldoutMAE",round(naive_formula["steerMAE"],7))
    print("OUTPUT",p)
if __name__=="__main__":main()
