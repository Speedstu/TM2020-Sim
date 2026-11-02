#!/usr/bin/env python3
"""Train/export the compact state-conditioned v8 policy from human state/action data."""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from hybrid_tracking import load_asset, save_asset
from prepare_fall_campaign import save_json
from train_hardcode_recorded_inputs import human_action_constraints


class Actor(nn.Module):
    def __init__(self):
        super().__init__()
        self.shared = nn.Linear(12, 32)
        self.head = nn.Linear(32, 3)

    def forward(self, x):
        return self.head(torch.tanh(self.shared(x)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--batch-size", type=int, default=8192)
    ap.add_argument("--steer-mode", choices=("delta", "absolute"), default="delta")
    args = ap.parse_args()
    index = args.map
    folder = ROOT / f"local/training/hardcode-human-0.73/{index:02d}"
    dataset = folder / "behavior-dataset-top100.npz"
    data_report = json.loads(dataset.with_suffix(".json").read_text())
    with np.load(dataset) as d:
        x = np.asarray(d["features"], dtype=np.float32)
        y = np.asarray(d["controls"], dtype=np.float32)
        rank = np.asarray(d["rank"], dtype=np.int64)
    dagger_path = folder / "dagger-human-nearest.npz"
    dagger_samples = 0
    if dagger_path.is_file():
        with np.load(dagger_path) as d:
            dx = np.asarray(d["features"], dtype=np.float32)
            dy = np.asarray(d["controls"], dtype=np.float32)
        if dx.ndim != 2 or dx.shape[1] != 12 or dy.shape != (len(dx), 3):
            raise ValueError("Invalid DAgger state/action set")
        dagger_samples = len(dx)
        x = np.concatenate((x, dx))
        y = np.concatenate((y, dy))
        rank = np.concatenate((rank, np.zeros(dagger_samples, dtype=np.int64)))
    if x.ndim != 2 or x.shape[1] != 12 or y.shape != (len(x), 3) or rank.shape != (len(x),):
        raise ValueError("State dataset requires 12 features, three action labels, and rank IDs")
    # Delta mode is smoother on the human manifold; absolute mode removes the
    # recurrent command input entirely and tests a state-only action map.
    if args.steer_mode == "delta":
        y[:, 2] = np.clip(y[:, 2] - x[:, 8], -2., 2.)
    else:
        x[:, 8] = 0.
    accepted_ranks = set(data_report["acceptedRanks"])
    accepted = (rank == 0) | np.asarray([int(r) in accepted_ranks for r in rank], dtype=bool)
    train = accepted & ((rank == 0) | (rank <= 80))
    valid = accepted & (rank > 80) & (rank <= 100)
    if not train.any() or not valid.any():
        raise ValueError("Group split by ghost rank is empty")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = Actor().to(device)
    tx = torch.from_numpy(x[train]).to(device)
    ty = torch.from_numpy(y[train]).to(device)
    vx = torch.from_numpy(x[valid]).to(device)
    vy = torch.from_numpy(y[valid]).to(device)
    # Give every ghost equal total weight so long replays do not dominate.
    counts = np.bincount(rank[train], minlength=101)[rank[train]].astype(np.float32)
    tw = torch.from_numpy((1. / np.maximum(counts, 1.)).astype(np.float32)).to(device)
    tw[torch.as_tensor(rank[train] == 0, device=device)] *= 20.
    tw /= tw.mean()
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-5)
    best = float("inf")
    best_state = None
    stale = 0
    history = []
    generator = torch.Generator(device=device).manual_seed(0x73031)
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(tx), generator=generator, device=device)
        for ids in order.split(args.batch_size):
            logits = model(tx[ids])
            steer_loss = (torch.tanh(logits[:, 0]) - ty[ids, 2]).square()
            pedal_loss = nn.functional.binary_cross_entropy_with_logits(logits[:, 1:], ty[ids, :2], reduction="none").mean(dim=1)
            loss = ((steer_loss + pedal_loss) * tw[ids]).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            opt.step()
        model.eval()
        with torch.no_grad():
            pred = model(vx)
            val_steer = (torch.tanh(pred[:, 0]) - vy[:, 2]).abs().mean().item()
            val_pedal = ((pred[:, 1:] >= 0) == (vy[:, :2] >= .5)).float().mean().item()
            val_loss = val_steer + (1. - val_pedal)
        history.append({"epoch": epoch + 1, "validationSteerMae": val_steer,
                        "validationPedalAccuracy": val_pedal, "selectionLoss": val_loss})
        if val_loss < best - 1e-5:
            best = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= 12:
                break
    if best_state is None:
        raise RuntimeError("No finite policy checkpoint")
    model.load_state_dict(best_state)
    net = np.zeros(515, dtype=np.float64)
    state = model.state_dict()
    net[:384] = state["shared.weight"].cpu().numpy().reshape(-1)
    net[384:416] = state["shared.bias"].cpu().numpy()
    net[416:512] = state["head.weight"].cpu().numpy().reshape(-1)
    net[512:515] = state["head.bias"].cpu().numpy()
    map_path = ROOT / f"local/campaign-2026-autumn/Autumn-2026-{index:02d}.Map.Gbx"
    meta = json.loads((ROOT / f"local/training/fall-campaign-0.52/{index:02d}/map.json").read_text())
    route_asset = folder / "historical-champion.tmhyb"
    reference, gains, _ = load_asset(route_asset, map_path=map_path, uid=meta["mapUid"])
    # The route is a spatial target only. No human steering/pedal tape survives in v8.
    reference[:, 22:25] = 0.
    constraints = human_action_constraints(index)
    path = folder / ("state-policy-v8.tmhyb" if args.steer_mode == "delta" else "state-policy-v8-absolute.tmhyb")
    gains[5] = 0. if args.steer_mode == "delta" else -1.
    save_asset(path, reference, gains, net, map_path=map_path, uid=meta["mapUid"], version=8,
               feedback_filter=np.array([0., 0., 10.]), human_constraints=constraints)
    report = {"map": index, "policy": str(path), "device": str(device), "trainingRanks": [1, 80],
              "validationRanks": [81, 100], "acceptedGhosts": len(data_report["acceptedRanks"]),
              "trainSamples": int(train.sum()),
              "validationSamples": int(valid.sum()), "daggerSamples": dagger_samples,
              "bestValidation": best,
              "history": history, "steeringMode": args.steer_mode,
              "actionTapeColumnsInAsset": "zeroed",
              "runtimeHumanGovernor": "v8 contextual envelope from observed 100 Hz humans"}
    save_json(folder / "state-policy-training.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
