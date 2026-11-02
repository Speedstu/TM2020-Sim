#!/usr/bin/env python3
"""Bounded, resumable research importer for public Trackmania 2020 maps+replays.

No logins, no DRM interaction, no global installs. All data under H: project.
TMTAS public /tracks and /replays endpoints; Trackmania Exchange map GBX URLs.
Single-threaded with modest delays, size limits, unique MapUID verification.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
DATA=ROOT/"local"/"corpus"
GBX_DLL=ROOT/"src"/"GbxLab"/"bin"/"Release"/"net9.0"/"GbxLab.dll"
AGENT="Mozilla/5.0 (compatible; TrackmaniaResearchOffline/0.1)"
URL_BASE="https://tmtas.exchange/api"
MAX_MAP_SIZE=20*1024*1024
MAX_REPLAY_SIZE=25*1024*1024
MAX_TOTAL_BYTES=220*1024*1024
RETRIES=2

def urlopen(url:str,limit:int=4*1024*1024)->bytes:
    req=urllib.request.Request(url,headers={"User-Agent":AGENT,"Accept":"application/json,application/octet-stream,*/*"})
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req,timeout=22) as response:
                size=response.headers.get("Content-Length")
                if size and int(size)>limit:
                    raise ValueError(f"File too large ({size} > {limit}): {url}")
                data=response.read(limit+1)
                if len(data)>limit: raise ValueError(f"Response size exceeds limit: {url}")
            time.sleep(0.18)
            return data
        except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError) as e:
            if isinstance(e,urllib.error.HTTPError) and e.code in (400,401,403,404,422):
                raise
            if attempt==RETRIES-1:raise
            time.sleep(1+attempt)
    raise RuntimeError("No download")

def json_endpoint(path):
    return json.loads(urlopen(URL_BASE+path).decode("utf-8"))

def download_gbx(url: str,target:Path,maxsize:int):
    if target.exists() and target.stat().st_size>=16:
        with target.open("rb") as f:
            if f.read(3)==b"GBX":return False
    content=urlopen(url, maxsize)
    if len(content)<16 or content[:3]!=b"GBX":
        raise ValueError(f"Downloaded data is not GBX ({len(content)} bytes): {url}")
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name(target.name+".part")
    tmp.write_bytes(content)
    tmp.replace(target)
    return True

def run_gbx(mode:str, src:Path, dst:Path):
    env=os.environ.copy()
    temp=ROOT/"cache"/"temp"
    temp.mkdir(parents=True,exist_ok=True)
    env.update({
        "DOTNET_CLI_HOME":str(ROOT/"cache"/"dotnet-home"),
        "NUGET_PACKAGES":str(ROOT/"cache"/"nuget"),
        "NUGET_HTTP_CACHE_PATH":str(ROOT/"cache"/"nuget-http"),
        "TEMP":str(temp),"TMP":str(temp),
        "DOTNET_CLI_TELEMETRY_OPTOUT":"1",
        "DOTNET_GENERATE_ASPNET_CERTIFICATE":"false"
    })
    r=subprocess.run(["dotnet",str(GBX_DLL),mode,str(src),str(dst)],
                      env=env,text=True,capture_output=True,timeout=80)
    if r.returncode!=0:raise RuntimeError(f"Parser {mode} failed: {r.stdout[-300:]} {r.stderr[-800:]}")
    return json.loads(dst.read_text(encoding="utf-8-sig"))

def select_tracks(max_number:int):
    seen=set()
    cohorts=[]
    # Sample different chronological cohorts, not just newly uploaded stunts.
    for page in (1,51,101,151,201,251,301,351):
        try:
            response=json_endpoint("/tracks?exchange=tm2020&sortBy=latest_replay_date&sortOrder=desc&amount=50&fromResultIndex="+str(page))
        except Exception as e:
            print("Track catalog query failed at",page,":",str(e)[:100],flush=True)
            continue
        tracks=response.get("results",[])
        filtered=[t for t in tracks if t.get("tmx_id") and t.get("uid") and t.get("track_id") and t.get("tas_time")]
        rng=random.Random(page+9927)
        rng.shuffle(filtered)
        group=[]
        for tr in filtered:
            if tr["uid"] in seen:continue
            seen.add(tr["uid"])
            group.append(tr)
        cohorts.append(group)
    shuffled=[]
    for x in range(max(len(c) for c in cohorts) if cohorts else 0):
        for cohort in cohorts:
            if x<len(cohort):shuffled.append(cohort[x])
    return shuffled[:max_number*5]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--max-new",type=int,default=16)
    p.add_argument("--catalog-candidates",type=int,default=130)
    a=p.parse_args()
    if not (1<=a.max_new<=80):raise ValueError("--max-new must be 1..80")
    if not GBX_DLL.is_file():raise RuntimeError("Build GbxLab first")
    DATA.mkdir(parents=True,exist_ok=True)
    manifest_file=DATA/"manifest.json"
    existing=json.loads(manifest_file.read_text(encoding="utf-8-sig")) if manifest_file.exists() else {"schema":"tm2020_public_replay_corpus_v1","pairs":[]}
    pairs=existing["pairs"]
    known={p["mapUid"] for p in pairs}
    # Prior local research samples also have train/test value and must be excluded from new imports.
    prior=json.loads((ROOT/"local"/"dataset-manifest.json").read_text(encoding="utf-8-sig"))
    known.update(p["mapUid"] for p in prior["linked"])
    total=sum(x.stat().st_size for x in DATA.rglob("*.Gbx"))
    completed=0
    errors=[]
    for candidate in select_tracks(a.catalog_candidates):
        if completed>=a.max_new:break
        if total>MAX_TOTAL_BYTES:break
        uid=str(candidate["uid"])
        if uid in known:continue
        track_id=int(candidate["track_id"])
        tmx_id=int(candidate["tmx_id"])
        try:
            replays=json_endpoint(f"/replays?track_id={track_id}")
            if not isinstance(replays,list) or not replays:continue
            best=min(replays,key=lambda q:q.get("time",1e20))
            replay_id=int(best["id"])
            if not (3000<=int(best.get("time",0))<=120000):continue
            # Temporary files are in same destination and never overwrite an already valid GBX.
            map_file=DATA/f"tmx-{tmx_id}.Map.Gbx"
            rep_file=DATA/f"tmtas-{replay_id}.Replay.Gbx"
            got_map=download_gbx(f"https://trackmania.exchange/mapgbx/{tmx_id}",map_file,MAX_MAP_SIZE)
            map_json=DATA/f"tmx-{tmx_id}.json"
            map_data=run_gbx("map",map_file,map_json)
            if map_data["uid"]!=uid:
                raise ValueError(f"Map UID mismatch: expected {uid}, found {map_data['uid']}")
            got_replay=download_gbx(f"{URL_BASE}/replay?id={replay_id}",rep_file,MAX_REPLAY_SIZE)
            rep_json=DATA/f"dataset-{replay_id}.json"
            rep_data=run_gbx("dataset",rep_file,rep_json)
            valid=[g["result"] for g in rep_data.get("ghosts",[]) if g["result"].get("stateInputRows")]
            if not valid:raise ValueError("Replay has no vehicle telemetry")
            n=sum(len(g["stateInputRows"]) for g in valid)
            entry={
                "trackId":track_id,"tmxId":tmx_id,"replayId":replay_id,
                "mapUid":uid,"mapName":map_data["mapName"],
                "source":"TMTAS Exchange (public TAS replay) / Trackmania Exchange",
                "timeMs":int(best["time"]),
                "vehicleSamples":n,
                "blockCount":map_data["blocksCount"],"itemCount":map_data["itemsCount"],
                "mapGbx":str(map_file.relative_to(ROOT)).replace("\\","/"),
                "mapJson":str(map_json.relative_to(ROOT)).replace("\\","/"),
                "replayGbx":str(rep_file.relative_to(ROOT)).replace("\\","/"),
                "datasetJson":str(rep_json.relative_to(ROOT)).replace("\\","/"),
                "mapSha256":hashlib.sha256(map_file.read_bytes()).hexdigest(),
                "replaySha256":hashlib.sha256(rep_file.read_bytes()).hexdigest(),
            }
            pairs.append(entry)
            known.add(uid)
            completed+=1
            total+=map_file.stat().st_size+rep_file.stat().st_size
            existing["lastUpdatedUtc"]=datetime.now(timezone.utc).isoformat()
            manifest_file.with_suffix(".json.tmp").write_text(json.dumps(existing,indent=2)+"\n",encoding="utf-8")
            manifest_file.with_suffix(".json.tmp").replace(manifest_file)
            print(f"PASS {completed}/{a.max_new}: TMX {tmx_id} / replay {replay_id} / {n} states / {map_data['mapName'][:48]}",flush=True)
        except Exception as exc:
            errors.append({"tmxId":tmx_id,"trackId":track_id,"error":f"{type(exc).__name__}: {str(exc)[:350]}"})
            if len(errors)<=10:print("SKIP",tmx_id,str(exc)[:100],flush=True)
        time.sleep(.15)
    (DATA/"import-errors.json").write_text(json.dumps(errors,indent=2),encoding="utf-8")
    print(f"DONE new={completed} total={len(pairs)} failures={len(errors)} archiveBytes={total}",flush=True)
    return 0 if completed else 1

if __name__=="__main__":sys.exit(main())
