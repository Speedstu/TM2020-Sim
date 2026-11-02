#!/usr/bin/env python3
"""Validate real passive Trackmania vehicle telemetry captured by C++ native TCP.

This checks TIMESTAMP consistency and measurement plausibility only.
It cannot establish native 100Hz physics accuracy without a physics-tick marker
and independent game-vs-simulator differential experiments.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from statistics import median
import sys

REQUIRED_KEYS={
    "schema","wallMs","sequence","frameDt","position","velocity",
    "dir","frontSpeed","sideSpeed","steer","gas","brake",
    "flSlip","frSlip","rlSlip","rrSlip"
}

def validate(file: Path)->dict:
    if not file.is_file():raise FileNotFoundError(file)
    if file.stat().st_size>1_000_000_000:raise ValueError("Telemetry capture larger than 1GB")
    count=0
    seq_prev=None
    ms_prev=None
    dropped=0
    reversed_clock=0
    ticks=[]
    bad_vectors=0
    invalid_controls=0
    zero_or_negative_dt=0
    map_uids=set()
    map_switches=0
    previous_map=None
    race_start_values=set()
    invalid_optional=0
    with file.open(encoding="utf-8-sig") as stream:
        for number,line in enumerate(stream,1):
            if len(line)>8192:raise ValueError(f"Line {number} exceeds protocol size")
            try: entry=json.loads(line)
            except json.JSONDecodeError as e:raise ValueError(f"Bad JSON on line {number}") from e
            if not isinstance(entry,dict) or not REQUIRED_KEYS.issubset(entry):
                raise ValueError(f"Missing required telemetry keys on line {number}")
            if entry["schema"]!="tm2020_live_telemetry_v1":
                raise ValueError(f"Invalid schema on line {number}")
            uid=entry.get("mapUid")
            if uid is not None:
                if not isinstance(uid,str) or len(uid)>128:
                    invalid_optional+=1
                elif uid:
                    map_uids.add(uid)
                    if previous_map is not None and previous_map!=uid:
                        map_switches+=1
                    previous_map=uid
            race_start=entry.get("raceStartMs")
            if race_start is not None:
                if type(race_start) is not int or not 0<=race_start<=0xffffffff:
                    invalid_optional+=1
                else:race_start_values.add(race_start)
            time_coef=entry.get("simulationTimeCoef")
            if time_coef is not None and (
                not isinstance(time_coef,(int,float)) or not math.isfinite(time_coef)
                or time_coef<0 or time_coef>100
            ): invalid_optional+=1
            seq,ms=entry["sequence"],entry["wallMs"]
            if not isinstance(seq,int) or not isinstance(ms,int):
                raise ValueError(f"Invalid sequence/timestamp on line {number}")
            if seq_prev is not None:
                if seq<=seq_prev:raise ValueError(f"Non-increasing sequence on line {number}")
                dropped+=seq-seq_prev-1
            if ms_prev is not None:
                delta=ms-ms_prev
                if delta<0:reversed_clock+=1
                if delta>0 and delta<=1000:ticks.append(delta)
            if float(entry["frameDt"])<=0:zero_or_negative_dt+=1
            for key in ("position","velocity","dir"):
                value=entry[key]
                if not isinstance(value,list) or len(value)!=3 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in value):
                    bad_vectors+=1
            for key in ("steer","gas","brake"):
                v=entry[key]
                if not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>2:
                    invalid_controls+=1
            for key in ("frontSpeed","sideSpeed","flSlip","frSlip","rlSlip","rrSlip"):
                v=entry[key]
                if not isinstance(v,(int,float)) or not math.isfinite(v):raise ValueError(f"Bad {key} at line {number}")
            seq_prev,ms_prev=seq,ms
            count+=1
    if count<3:raise ValueError("At least 3 telemetry samples needed")
    if bad_vectors or invalid_controls or reversed_clock or invalid_optional:
        raise ValueError(f"Invalid sample vectors/controls/time: {bad_vectors}/{invalid_controls}/{reversed_clock}")
    median_ms=median(ticks) if ticks else None
    return {
        "format":"tm2020_live_capture_quality_v1",
        "samples":count,"droppedSequenceGaps":dropped,"nonpositiveFrameDt":zero_or_negative_dt,
        "positiveTickDifferences":len(ticks),"medianObservedFrameSpacingMs":median_ms,
        "approxObservedHz":round(1000/median_ms,3) if median_ms else None,
        "timeStampMeaning":"Openplanet Time::Now monotonic wall milliseconds; measured Update/render callbacks, not physics integrator ticks",
        "verifiedInternalPhysics100Hz":False,
        "strictPhysicsCalibrationReady":False,
        "mapUids":sorted(map_uids),
        "mapSwitches":map_switches,
        "distinctRaceStartClocks":len(race_start_values),
        "metadataPresent":bool(map_uids or race_start_values),
        "qualityVerdict":"valid-render-telemetry-only" if ticks and zero_or_negative_dt==0 else "insufficient-time-quality"
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("capture",type=Path)
    ap.add_argument("--output",type=Path)
    a=ap.parse_args()
    result=validate(a.capture)
    rendered=json.dumps(result,indent=2)
    print(rendered)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(rendered+"\n",encoding="utf-8")
    return 0
if __name__=="__main__":sys.exit(main())
