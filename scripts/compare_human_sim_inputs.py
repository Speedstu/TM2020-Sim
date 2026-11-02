#!/usr/bin/env python3
"""Compare certified human ghost commands with Top-10 simulator rollouts."""
import argparse
import json
from pathlib import Path

import numpy as np
from hybrid_tracking import load_asset

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "local/training/hardcode-inputs-0.71/human-sim-comparison.json"
DEFAULT_TRAINING = ROOT / "local/training/hardcode-inputs-0.71"
EXPECTED_MAPS = list(range(1, 26))
MIN_ROBUST_TOP10_RUNS = 32
METRICS = {
    "steeringChangesPerSecond": ("steeringChangesPerSecond",),
    "steeringVariationPerSecond": ("steeringVariationPerSecond",),
    "reversalsWithin100msPerLap": ("reversalsWithin100ms",),
    "smallReversalsWithin100msPerLap": ("smallReversalsWithin100ms",),
    "rawSteeringStepP50P95P99": ("rawSteeringStepP50P95P99",),
    "steeringHoldMsP10P50P90": ("steeringHoldMsP10P50P90",),
    "gasDuty": ("gasDuty",),
    "brakeDuty": ("brakeDuty",),
    "gasTransitionsPerSecond": ("gasChangesPerSecond",),
    "brakeTransitionsPerSecond": ("brakeChangesPerSecond",),
    "gasPressMsP10P50P90": ("gasPressMsP10P50P90",),
    "gasReleaseMsP10P50P90": ("gasReleaseMsP10P50P90",),
    "brakePressMsP10P50P90": ("brakePressMsP10P50P90",),
    "brakeReleaseMsP10P50P90": ("brakeReleaseMsP10P50P90",),
}


def mean_value(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return float(np.mean(values)) if values else None


def fmt(value, digits=2):
    return "n/a" if value is None else f"{value:.{digits}f}"


def summarize_rows(rows, target_ms, label="top10"):
    top = [r for r in rows if r.get("finishMs") is not None and r["finishMs"] <= target_ms]
    out = {f"{label}Runs": len(top), f"finishMsMeanAmong{label.title()}": mean_value([r["finishMs"] for r in top])}
    for label, (key,) in METRICS.items():
        vals = [r.get("inputs", {}).get(key) for r in top]
        vals = [v for v in vals if isinstance(v, (int, float)) or
                (isinstance(v, list) and len(v) == 3)]
        if vals and isinstance(vals[0], list):
            out[label] = np.median(np.asarray(vals, dtype=float), axis=0).round(3).tolist()
        else:
            out[label] = float(np.median(vals)) if vals else None
    return out


def human_style_proxy(inputs, human):
    common_failures = []
    observed_failures = []
    censored = []
    if inputs.get("top10Runs", inputs.get("top100Runs", 0)) <= 0:
        common_failures.append("no qualifying command samples")
        observed_failures.append("no qualifying command samples")
    bands = human.get("empiricalP10P90", {})
    extrema = human.get("empiricalMinMax", {})
    checks = [
        ("steeringChangesPerSecond", inputs.get("steeringChangesPerSecond"), 0, "steering changes/s outside human cohort P10–P90"),
        ("steeringVariationPerSecond", inputs.get("steeringVariationPerSecond"), 0, "steering variation/s outside human cohort P10–P90"),
        ("reversalsWithin100msPerLap", inputs.get("reversalsWithin100msPerLap"), 0, "fast reversals outside human cohort P10–P90"),
        ("smallReversalsWithin100msPerLap", inputs.get("smallReversalsWithin100msPerLap"), 0, "small reversals outside human cohort P10–P90"),
        ("gasDuty", inputs.get("gasDuty"), 0, "gas duty outside human cohort P10–P90"),
        ("brakeDuty", inputs.get("brakeDuty"), 0, "brake duty outside human cohort P10–P90"),
        ("gasTransitionsPerSecond", inputs.get("gasTransitionsPerSecond"), 0, "gas transition rate outside human cohort P10–P90"),
        ("brakeTransitionsPerSecond", inputs.get("brakeTransitionsPerSecond"), 0, "brake transition rate outside human cohort P10–P90"),
    ]
    for name, actual, q, label in checks:
        if actual is None:
            continue
        b=bands.get(name,[]);x=extrema.get(name,[])
        if len(b)==2 and not (b[0]<=actual<=b[1]):common_failures.append(label)
        if len(x)==2 and not (x[0]<=actual<=x[1]):observed_failures.append(label.replace("P10–P90","observed human range"))
    for name, actual_key, positions, labels in (
        ("rawSteeringStepP50P95P99", "rawSteeringStepP50P95P99", (1, 2), ("i8 P95", "i8 P99")),
        ("steeringHoldMsP10P50P90", "steeringHoldMsP10P50P90", (1, 2), ("steering hold P50", "steering hold P90")),
        ("gasPressMsP10P50P90", "gasPressMsP10P50P90", (0, 1, 2), ("gas press P10", "gas press P50", "gas press P90")),
        ("gasReleaseMsP10P50P90", "gasReleaseMsP10P50P90", (0, 1, 2), ("gas release P10", "gas release P50", "gas release P90")),
        ("brakePressMsP10P50P90", "brakePressMsP10P50P90", (0, 1, 2), ("brake press P10", "brake press P50", "brake press P90")),
        ("brakeReleaseMsP10P50P90", "brakeReleaseMsP10P50P90", (0, 1, 2), ("brake release P10", "brake release P50", "brake release P90")),
    ):
        channel = 'gas' if name.startswith('gas') else 'brake' if name.startswith('brake') else None
        if channel:
            duty=inputs.get(channel+'Duty'); hduty=human.get(channel+'Duty')
            transitions=inputs.get(channel+'TransitionsPerSecond'); ht=human.get(channel+'TransitionsPerSecond')
            # A channel held for the entire lap has no observed hold end. Its
            # duration measures lap time, so do not penalize a faster finisher.
            if duty in (0.,1.) and hduty==duty and transitions==0. and ht==0.:
                censored.append(name)
                continue
        actual = inputs.get(actual_key, [])
        b = bands.get(name, [])
        x = extrema.get(name, [])
        for pos, label in zip(positions, labels):
            if not isinstance(actual,list) or len(actual)<=pos:continue
            if len(b)==2 and isinstance(b[0],list) and len(b[0])>pos and not (b[0][pos]<=actual[pos]<=b[1][pos]):
                common_failures.append(f"{label} outside human cohort P10–P90")
            if len(x)==2 and isinstance(x[0],list) and len(x[0])>pos and not (x[0][pos]<=actual[pos]<=x[1][pos]):
                observed_failures.append(f"{label} outside observed human range")
    return {"passes": not observed_failures, "failedCriteria": observed_failures,
            "rightCensoredDurationMetricsExcluded": censored,
            "commonStylePasses": not common_failures, "commonStyleFailures": common_failures,
            "criteria": "bot median across qualifying runs must lie inside the observed per-ghost human min–max range; P10–P90 is reported separately as commonness",
            "proxyOnly": True, "cohortRange": "empirical across decoded Top-100 ghosts"}


def summarize_human_ghost(path):
    doc = json.loads(path.read_text())
    seg = doc["segments"]["all"]
    # Neutral input channels are not evidence for how a human steers the car.
    if seg.get("gasDuty", 0.) < .5 or seg.get("steeringChangesPerSecond", 0.) < 1.:
        return None
    result = {key: seg.get(key) for key in METRICS}
    result["steeringHoldMsP10P50P90"] = seg.get("holdMsP10P50P90")
    result["reversalsWithin100msPerLap"] = seg.get("reversalsWithin100ms")
    result["smallReversalsWithin100msPerLap"] = seg.get("smallReversalsWithin100ms")
    result["source"] = doc.get("source")
    result["sha256"] = doc.get("sha256")
    return result


def summarize_human_cohort(index):
    samples = []
    excluded = []
    for rank in range(1, 101):
        path = ROOT / f"local/training/human-rework-0.70/top100-cohort/{index:02d}/leaderboard-rank{rank:03d}/analysis.json"
        if not path.exists() and rank <= 3:
            path = ROOT / f"local/training/human-rework-0.70/corpus/{index:02d}/leaderboard-rank{rank}/analysis.json"
        if not path.exists():
            continue
        doc = summarize_human_ghost(path)
        if doc is None:
            excluded.append({"rank": rank, "reason": "neutral or non-driving recorded inputs"})
        else:
            samples.append({"rank": rank, "metrics": doc})
    if not samples:
        raise RuntimeError(f"No usable human input ghosts for map {index}")
    names = list(METRICS) + ["reversalsWithin100msPerLap", "smallReversalsWithin100msPerLap"]
    cohort = {}
    for name in names:
        values = [s["metrics"].get(name) for s in samples]
        values = [v for v in values if v is not None]
        if not values:
            cohort[name] = None
        elif isinstance(values[0], list):
            values = [v for v in values if v]
            cohort[name] = np.median(np.asarray(values, dtype=float), axis=0).round(3).tolist() if values else []
        else:
            cohort[name] = float(np.median(np.asarray(values, dtype=float)))
    bands = {}
    for name in names:
        values = [s["metrics"].get(name) for s in samples]
        values = [v for v in values if v is not None and (not isinstance(v, list) or len(v) == 3)]
        if values:
            a = np.asarray(values, dtype=float)
            bands[name] = np.percentile(a, [10, 90], axis=0).round(3).tolist()
    cohort["empiricalP10P90"] = bands
    extrema = {}
    for name in names:
        values = [s["metrics"].get(name) for s in samples]
        values = [v for v in values if v is not None and (not isinstance(v, list) or len(v) == 3)]
        if values:
            a=np.asarray(values,dtype=float)
            extrema[name]=np.stack((np.min(a,axis=0),np.max(a,axis=0))).round(3).tolist()
    cohort["empiricalMinMax"] = extrema
    cohort["sourceRanks"] = [s["rank"] for s in samples]
    cohort["excludedRanks"] = excluded
    cohort["certification"] = "public leaderboard ghosts; user asserts leaderboard human verification; not independently verified"
    return cohort, samples


def action_tape_similarity(index, training_dir, candidate_sha):
    """Flag a candidate asset whose stored 100 Hz action tape mirrors Top-1."""
    meta=json.loads((ROOT/f"local/training/fall-campaign-0.52/{index:02d}/map.json").read_text())
    asset=None
    for path in (training_dir/f"{index:02d}").rglob("*.tmhyb"):
        import hashlib
        if hashlib.sha256(path.read_bytes()).hexdigest()==candidate_sha:
            asset=path;break
    if asset is None:return {"checked":False,"reason":"candidate asset file not found"}
    ghost=ROOT/f"local/training/human-rework-0.70/top100-cohort/{index:02d}/leaderboard-rank001/timeline.npz"
    if not ghost.is_file():ghost=ROOT/f"local/training/human-rework-0.70/corpus/{index:02d}/leaderboard-rank1/timeline.npz"
    if not ghost.is_file():return {"checked":False,"reason":"Top-1 raw input timeline missing"}
    reference,_,_=load_asset(asset,map_path=meta["map"],uid=meta["mapUid"])
    with np.load(ghost) as doc:human=np.asarray(doc["controls"],dtype=float)
    n=min(len(reference),len(human));bot=reference[:n,22:25].copy();human=human[:n].copy()
    bot[:,:2]=np.rint(bot[:,:2]);bot[:,2]=np.rint(bot[:,2]*127.)
    human[:,:2]=np.rint(human[:,:2]);human[:,2]=np.rint(human[:,2]*127.)
    exact_channels={name:float(np.mean(bot[:,col]==human[:,col])) for col,name in enumerate(("gas","brake","steer"))}
    corr=float(np.corrcoef(bot[:,2],human[:,2])[0,1]) if np.std(bot[:,2]) and np.std(human[:,2]) else None
    detected=exact_channels["gas"]>=.99 and exact_channels["brake"]>=.99 and corr is not None and corr>=.98
    return {"checked":True,"ticksCompared":n,"sourceGhostRank":1,"exactTickFractionByChannel":exact_channels,
        "steerCorrelation":corr,"replayActionTapeDetected":detected,
        "sourceHumanSha256":json.loads((ROOT/f"local/training/human-rework-0.70/top100-cohort/{index:02d}/leaderboard-rank001/analysis.json").read_text())["sha256"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--training-dir", type=Path, default=DEFAULT_TRAINING,
                    help="hardcode training directory containing per-map latest-qualification.json")
    ap.add_argument("--maps", type=int, nargs="+", default=None,
                    help="Maps to report; default all 25 campaign maps (unqualified maps remain pending)")
    args = ap.parse_args()
    requested = args.maps or EXPECTED_MAPS
    pending = []
    pending_reasons = {}
    report = {"method": "only completed simulator finishes at or below cached leaderboard Top-10 time; means across qualifying runs",
              "expectedCampaignMaps": EXPECTED_MAPS, "requestedMaps": requested,
              "minimumRobustTop10RunsPerSeedSet": MIN_ROBUST_TOP10_RUNS,
              "pendingMaps": pending, "pendingReasons": pending_reasons, "maps": {}}
    for index in requested:
        m = f"{index:02d}"
        qual_path = args.training_dir / m / "latest-qualification.json"
        if not qual_path.is_file():
            pending.append(index);pending_reasons[str(index)]="no 64-seed qualification yet"
            continue
        qual = json.loads(qual_path.read_text())
        if qual.get("actionSpaceHardConstrained") is not True:
            pending.append(index);pending_reasons[str(index)]="legacy qualification predates hard human action-space constraints"
            continue
        human, human_ghosts = summarize_human_cohort(index)
        tape = action_tape_similarity(index,args.training_dir,qual["candidateSha256"])
        arms = {}
        for arm in ("beforeNormal", "afterNormal"):
            families = {}
            for family in ("normal64", "perturbed64"):
                result = qual["results"][arm][family]
                families[family] = {
                    "finishRate": result["finishes"],
                    "Top10Rate": result["top10Finishes"],
                    "Top100Rate": result.get("top100Finishes", result["finishes"]),
                    "inputsAmongTop10": summarize_rows(result["trials"], qual["top10TargetMs"], "top10"),
                    "inputsAmongTop100": summarize_rows(result["trials"], qual.get("top100TargetMs", qual["top10TargetMs"]), "top100"),
                }
            arms[arm] = families
        report["maps"][m] = {
            "top10TargetMs": qual["top10TargetMs"],
            "humanCohortMedian": human,
            "humanGhosts": human_ghosts,
            "qualification": str(qual_path.relative_to(ROOT)) if qual_path.is_relative_to(ROOT) else str(qual_path.resolve()),
            "baselineSha256": qual["baselineSha256"],
            "candidateSha256": qual["candidateSha256"],
            "storedActionTapeSimilarityToTop1":tape,
            "same64SeedsAndHorizon": qual["sameSeedsAndHorizon"],
            "actionSpaceHardConstrained": True,
            "humanActionConstraints": qual["humanActionConstraints"],
            "arms": arms,
            "clientReplayVerified": False,
            "promotion": qual["promotion"],
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for m, doc in report["maps"].items():
        human = doc["humanCohortMedian"]
        print(f"Fall {m} human cohort ranks {human['sourceRanks']}: "
              f"steer {fmt(human['steeringChangesPerSecond'])}/s; "
              f"reversals {fmt(human['reversalsWithin100msPerLap'], 1)}; "
              f"small reversals {fmt(human['smallReversalsWithin100msPerLap'], 1)}; "
              f"excluded {human['excludedRanks']}")
        for arm, families in doc["arms"].items():
            for name, r in families.items():
                x = r["inputsAmongTop10"]
                style100 = r["inputsAmongTop100"] if r["inputsAmongTop100"]["top100Runs"] else x
                r["humanLikeTop100CommandProxy"] = human_style_proxy(style100, human)
                r["humanLikeTop10CommandProxy"] = human_style_proxy(x, human)
                r["humanLikeCommandProxy"] = r["humanLikeTop10CommandProxy"]
                print(f"  {arm}/{name}: Top10 {r['Top10Rate']}/64, Top100 {r['Top100Rate']}/64, finishes {r['finishRate']}/64; "
                      f"Top10-style steer {fmt(x['steeringChangesPerSecond'])}/s; "
                      f"reversals {fmt(x['reversalsWithin100msPerLap'], 1)}; "
                      f"small {fmt(x['smallReversalsWithin100msPerLap'], 1)}; "
                      f"variation {fmt(x['steeringVariationPerSecond'], 3)}/s; "
                      f"human Top10-proxy {'PASS' if r['humanLikeTop10CommandProxy']['passes'] else 'FAIL'}; "
                      f"common-style {'PASS' if r['humanLikeTop10CommandProxy']['commonStylePasses'] else 'OUTSIDE P10–P90'}")
        cand = doc["arms"]["afterNormal"]
        baseline = doc["arms"]["beforeNormal"]
        doc["simReadyForClientTrial"] = all(
            cand[f]["Top10Rate"] >= max(baseline[f]["Top10Rate"], MIN_ROBUST_TOP10_RUNS) and
            cand[f]["finishRate"] >= baseline[f]["finishRate"] and
            cand[f]["inputsAmongTop10"]["finishMsMeanAmongTop10"] is not None and
            cand[f]["inputsAmongTop10"]["finishMsMeanAmongTop10"] <= doc["top10TargetMs"] and
            cand[f]["humanLikeTop10CommandProxy"]["passes"] and
            not doc["storedActionTapeSimilarityToTop1"].get("replayActionTapeDetected",False)
            for f in ("normal64", "perturbed64"))
        print(f"  simulator gate before trying game: {'PASS' if doc['simReadyForClientTrial'] else 'FAIL'}")
    report["simReadyForRequestedMaps"] = (not pending and bool(report["maps"]) and
                                          all(d["simReadyForClientTrial"] for d in report["maps"].values()))
    report["simReadyForClientTrialAllMaps"] = (requested == EXPECTED_MAPS and report["simReadyForRequestedMaps"])
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"report: {args.output}")


if __name__ == "__main__":
    main()
