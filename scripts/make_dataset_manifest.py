#!/usr/bin/env python3
"""Link GBX-extracted replay state/input datasets with verified TMX map metadata."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
pairs = json.loads((ROOT / "config" / "dataset-pairs.json").read_text(encoding="utf-8-sig"))["pairs"]
linked = []
for pair in pairs:
    map_id, replay_id = pair["tmxId"], pair["replayId"]
    map_path = ROOT / "local" / "test-maps" / f"tmx-{map_id}.json"
    replay_path = ROOT / "local" / "replays" / f"dataset-{replay_id}.json"
    validation_path = ROOT / "local" / "replays" / f"validation-{replay_id}.json"
    m = json.loads(map_path.read_text(encoding="utf-8-sig"))
    r = json.loads(replay_path.read_text(encoding="utf-8-sig"))
    if m["uid"] != pair["mapUid"]:
        raise RuntimeError(f"Wrong map: TMX {map_id}, expected UID {pair['mapUid']}, got {m['uid']}")
    if m["kind"] != "map":
        raise RuntimeError(f"Not a map {map_id}")
    if len(r["ghosts"]) != 1:
        raise RuntimeError(f"Unexpected ghost count in replay {replay_id}")
    result = r["ghosts"][0]["result"]
    if not result.get("stateInputRows"):
        raise RuntimeError(f"No vehicle telemetry in replay {replay_id}")
    linked.append({
        "replayId": replay_id, "tmxId": map_id, "trackId": pair["trackId"],
        "mapUid": m["uid"], "mapName": m["mapName"],
        "mapBlockCount": m["blocksCount"], "mapItemCount": m["itemsCount"],
        "vehicleSamples": result["stateSamples"], "inputEvents": result["inputChanges"],
        "mapGbx": f"local/test-maps/tmx-{map_id}.Map.Gbx",
        "mapJson": str(map_path.relative_to(ROOT)).replace("\\","/"),
        "replayGbx": f"local/replays/tmtas-{replay_id}.Replay.Gbx",
        "datasetJson": str(replay_path.relative_to(ROOT)).replace("\\","/"),
        "validationJson": str(validation_path.relative_to(ROOT)).replace("\\","/"),
    })
out = {
    "schema": "tm2020_linked_replay_maps_v1",
    "note": "UID verified against public track metadata; map structure is not yet collision geometry.",
    "count": len(linked),
    "totalVehicleSamples": sum(x["vehicleSamples"] for x in linked),
    "totalInputEvents": sum(x["inputEvents"] for x in linked),
    "linked": linked
}
dest = ROOT / "local" / "dataset-manifest.json"
dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print("PASS: linked", len(linked), "replays to matching TMX maps; output:", dest)
