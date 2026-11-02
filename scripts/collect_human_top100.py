#!/usr/bin/env python3
"""Collect and decode public Fall campaign Top-100 ghosts for human-style work.

Read-only: downloads leaderboard snapshots and public ghost files, preserves
the existing Top-3 corpus, then analyzes raw 100 Hz inputs with the project
metadata decoder. No game/client or account writes are performed.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.request

from analyze_human_replays import analyze
from prepare_fall_campaign import ROOT, fetch, save_json, save

BASE = ROOT / "local/training/human-rework-0.70"
API = "https://trackmania.io/api/leaderboard/map/{uid}?length=100&offset=0"
UA = "TM2020LocalResearch/0.73 (read-only Top-100 human input analysis)"


def collect_one(index, entry, destination):
    rank = int(entry["position"])
    output = destination / f"{index:02d}" / f"leaderboard-rank{rank:03d}"
    analysis_path = output / "analysis.json"
    timeline_path = output / "timeline.npz"
    if analysis_path.is_file() and timeline_path.is_file():
        doc = json.loads(analysis_path.read_text())
        return {"map": index, "rank": rank, "timeMs": int(entry["time"]),
                "sha256": doc["sha256"], "ticks": int(doc["inputCoverageMs"][1]//10+1),
                "cached": True, "decoded": True}

    old = BASE / "corpus" / f"{index:02d}" / f"leaderboard-rank{rank}"
    if rank <= 3 and (old / "analysis.json").is_file():
        old_analysis = json.loads((old / "analysis.json").read_text())
        source = Path(old_analysis["source"])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != old_analysis["sha256"]:
            raise RuntimeError(f"Preserved Top-{rank} source hash mismatch on Fall {index:02d}")
    else:
        source = destination / f"{index:02d}" / "downloads" / f"rank{rank:03d}.Ghost.Gbx"
        if not source.is_file():
            url = "https://trackmania.io" + entry["url"]
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            payload = fetch(request.full_url, limit=8*1024*1024)
            source.parent.mkdir(parents=True, exist_ok=True)
            save(source, payload)

    doc = analyze(source, f"leaderboard-rank{rank:03d}", index, output)
    return {"map": index, "rank": rank, "timeMs": int(entry["time"]),
            "sha256": doc["sha256"], "ticks": int(doc["inputCoverageMs"][1]//10+1),
            "cached": False, "decoded": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps", type=int, nargs="+", default=[1, 3])
    parser.add_argument("--output", type=Path, default=BASE / "top100-cohort")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 4:
        parser.error("--workers must be between 1 and 4")
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    summary = {"schema": "tm2020_human_top100_input_cohort_v1",
               "source": "public trackmania.io leaderboard ghost downloads",
               "fetchedUtc": datetime.now(timezone.utc).isoformat(),
               "readOnly": True, "clientOrGameUsed": False, "maps": {}, "failures": []}

    for index in args.maps:
        if not 1 <= index <= 25:
            parser.error(f"invalid campaign map index {index}")
        map_meta = json.loads((ROOT / f"local/training/fall-campaign-0.52/{index:02d}/map.json").read_text())
        url = API.format(uid=map_meta["mapUid"])
        leaderboard = json.loads(fetch(url))
        entries = leaderboard.get("tops", [])
        ranks = [int(x["position"]) for x in entries]
        if len(entries) < 100 or ranks[:100] != list(range(1, 101)):
            raise RuntimeError(f"Fall {index:02d}: Top-100 response is incomplete or not rank ordered")
        snapshot = {"sourceUrl": url, "fetchedUtc": datetime.now(timezone.utc).isoformat(),
                    "playerCount": leaderboard.get("playercount"),
                    "tops": [{k: row[k] for k in ("position", "time", "url", "timestamp") if k in row}
                             for row in entries[:100] if all(k in row for k in ("position", "time", "url"))]}
        save_json(destination / f"{index:02d}" / "leaderboard-top100.json", snapshot)
        tasks = [(index, row, destination) for row in entries[:100]]
        results = []
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending = {pool.submit(collect_one, *task): task[1]["position"] for task in tasks}
            for future in as_completed(pending):
                rank = int(pending[future])
                try:
                    result = future.result(); results.append(result)
                    summary["maps"].setdefault(f"{index:02d}", []).append(result)
                except Exception as exc:
                    failure = {"map": index, "rank": rank, "error": str(exc)}
                    summary["failures"].append(failure)
                save_json(destination / "collection-progress.json", summary)
                done = len(results) + sum(x.get("map") == index for x in summary["failures"])
                if done % 10 == 0 or done == 100:
                    print(json.dumps({"map": index, "completed": done,
                                      "decoded": len(results), "failed": sum(
                                          x.get("map") == index for x in summary["failures"])}), flush=True)
        summary["maps"][f"{index:02d}"] = sorted(results, key=lambda x: x["rank"])
        save_json(destination / "collection-progress.json", summary)

    save_json(destination / "collection-report.json", summary)
    print(f"report: {destination / 'collection-report.json'}")
    if summary["failures"]:
        raise SystemExit(f"{len(summary['failures'])} Top-100 ghost(s) failed; see report")


if __name__ == "__main__":
    main()
