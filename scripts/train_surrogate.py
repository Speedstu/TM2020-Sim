#!/usr/bin/env python3
"""Train/evaluate a learned 50 ms *surrogate*, never present it as Trackmania physics.

Standalone PyTorch 2.0 CPU script, loads existing system torch/numpy, no pip installs.
Strict map-UID group holdout. No game memory, no game automation. All artifacts on H:.
Outputs candidate weights even on fail, plus explicit generalization failure flags.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import torch
from torch import nn

from physics_baseline import ROOT,FEATURE_NAMES,TARGET_NAMES,load_all,metric

class PhysicsMLP(nn.Module):
    def __init__(self, n:int,hidden:int=96):
        super().__init__()
        self.seq=nn.Sequential(nn.Linear(n,hidden),nn.SiLU(),
                               nn.Linear(hidden,hidden),nn.SiLU(),
                               nn.Linear(hidden,hidden),nn.SiLU(),
                               nn.Linear(hidden,2))
    def forward(self,x):
        return self.seq(x)

def fold(uid,k=5):
    return int(hashlib.sha256(uid.encode("utf-8")).hexdigest()[:8],16)%k

def train(data,epochs,lr,seed,device="cpu"):
    xtrain,ytrain=data
    xmean=xtrain.mean(0)
    xstd=xtrain.std(0)
    xmean[0]=0;xstd[0]=1
    xstd[xstd<1e-8]=1
    ymean=ytrain.mean(0)
    ystd=ytrain.std(0)
    ystd[ystd<1e-8]=1
    xn=np.clip((xtrain-xmean)/xstd,-15,15).astype(np.float32)
    yn=np.clip((ytrain-ymean)/ystd,-20,20).astype(np.float32)
    torch.manual_seed(seed)
    model=PhysicsMLP(xn.shape[1])
    opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=0.0007)
    lossfn=nn.SmoothL1Loss(beta=0.7)
    X=torch.from_numpy(xn)
    Y=torch.from_numpy(yn)
    batch=512
    model.train()
    for epoch in range(epochs):
        generator=torch.Generator().manual_seed(seed*1000+epoch)
        permutation=torch.randperm(len(X),generator=generator)
        for ids in permutation.split(batch):
            yh=model(X[ids])
            loss=lossfn(yh,Y[ids])
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),2)
            opt.step()
    model.eval()
    return model,dict(xmean=xmean,xstd=xstd,ymean=ymean,ystd=ystd)

@torch.inference_mode()
def predict(model,transform,x):
    z=np.clip((x-transform["xmean"])/transform["xstd"],-15,15).astype(np.float32)
    y=model(torch.from_numpy(z)).numpy().astype(np.float64)
    return y*transform["ystd"]+transform["ymean"]

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--epochs",type=int,default=40)
    cli.add_argument("--folds",type=int,default=5)
    cli.add_argument("--threads",type=int,default=4)
    cli.add_argument("--lr",type=float,default=0.0008)
    cli.add_argument("--out",default=str(ROOT/"local"/"surrogate_v1"))
    opt=cli.parse_args()
    if not 1<=opt.epochs<=500:raise ValueError("Invalid epoch count")
    if not 2<=opt.folds<=8:raise ValueError("Invalid fold count")
    if not 1<=opt.threads<=16:raise ValueError("Invalid thread count")
    torch.set_num_threads(opt.threads)
    data=load_all()
    folds={k:[uid for uid in data if fold(uid,opt.folds)==k] for k in range(opt.folds)}
    if min(map(len,folds.values()))<1:
        raise RuntimeError("Empty map fold, choose another --folds value")
    output=[]
    start=time.perf_counter()
    for foldnum,test_uids in folds.items():
        train_records=[d for uid,d in data.items() if uid not in test_uids]
        test=[data[u] for u in test_uids]
        X=np.concatenate([d["x"] for d in train_records]);Y=np.concatenate([d["y"] for d in train_records])
        model,tr=train((X,Y),opt.epochs,opt.lr,seed=2026+foldnum)
        p=np.concatenate([predict(model,tr,t["x"]) for t in test])
        y=np.concatenate([t["y"] for t in test])
        row=metric(y,p)
        row["fold"]=foldnum
        row["heldOutMapUids"]=test_uids
        row["heldOutReplayIds"]=[d["replayId"] for d in test]
        row["trainMaps"]=len(train_records)
        output.append(row)
        print("FOLD",foldnum,"maps",len(test),"rows",len(y),"speedMAE",round(row["speedDeltaMAE_kmh"],4),
              "naive",round(row["naiveConstantSpeedMAE_kmh"],4),
              "yawMAEDeg",round(row["headingDeltaMAE_deg"],4),
              "naive",round(row["naiveConstantHeadingMAE_deg"],4),flush=True)

    def weighted(key):return sum(x[key]*x["n"] for x in output)/sum(x["n"] for x in output)
    target=Path(opt.out)
    target.mkdir(parents=True,exist_ok=True)
    metrics={
        "schema":"tm2020_surrogate_50ms_v1",
        "type":"NONAUTHORITATIVE offline learned one-step dynamics; not Trackmania engine",
        "holdout":"grouped by map UID, 5 folds, all feature normalization train-only",
        "sourceMaps":len(data),
        "sourceTransitions":sum(d["rows"] for d in data.values()),
        "epochs":opt.epochs,"folds":opt.folds,"torchVersion":torch.__version__,
        "speedMAE_kmh":weighted("speedDeltaMAE_kmh"),
        "speedNaiveMAE_kmh":weighted("naiveConstantSpeedMAE_kmh"),
        "yawMAE_deg":weighted("headingDeltaMAE_deg"),
        "yawNaiveMAE_deg":weighted("naiveConstantHeadingMAE_deg"),
        "foldMetrics":output,
        "runtimeSeconds":round(time.perf_counter()-start,2)
    }
    metrics["beatsNaiveBoth"]=metrics["speedMAE_kmh"]<metrics["speedNaiveMAE_kmh"] and metrics["yawMAE_deg"]<metrics["yawNaiveMAE_deg"]
    # Train a deployment candidate on ALL available maps, separate from CV analysis.
    allx=np.concatenate([d["x"] for d in data.values()])
    ally=np.concatenate([d["y"] for d in data.values()])
    final,trans=train((allx,ally),opt.epochs,opt.lr,seed=2026)
    torch.save({
        "state_dict":final.state_dict(),"architecture":"PhysicsMLP_96x3",
        "features":FEATURE_NAMES,"targets":TARGET_NAMES,
        "normalizer":{k:v.astype(np.float32) for k,v in trans.items()},
        "warning":"Approximate 50ms surrogate, never a deterministic Trackmania engine",
        "validation":metrics["beatsNaiveBoth"],
    },target/"surrogate.pt")
    (target/"cross_map_validation.json").write_text(json.dumps(metrics,indent=2)+"\n",encoding="utf-8")
    print("RESULT maps",metrics["sourceMaps"],"samples",metrics["sourceTransitions"],
          "speed",round(metrics["speedMAE_kmh"],4),"vs",round(metrics["speedNaiveMAE_kmh"],4),
          "yaw",round(metrics["yawMAE_deg"],4),"vs",round(metrics["yawNaiveMAE_deg"],4),
          "BEATS_BOTH",metrics["beatsNaiveBoth"],
          "seconds",metrics["runtimeSeconds"],flush=True)
    return 0

if __name__=="__main__":sys.exit(main())
