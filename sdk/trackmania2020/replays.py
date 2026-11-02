"""Read-only map/telemetry SDK for Trackmania 2020 public GBX exports.

The observed vehicle frames are replay snapshots at 50ms intervals.
This module deliberately provides NO counterfactual step(action) implementation.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterator

REPO=Path(__file__).resolve().parents[2]

def parse_clock(s:str)->int:
    negative=s.startswith("-")
    if negative:s=s[1:]
    m,sec=s.split(":")
    seconds,millis=(sec.split(".")+["0"])[:2]
    value=int(m)*60000 +int(seconds)*1000+int(millis.ljust(3,"0")[:3])
    return -value if negative else value

@dataclass(frozen=True)
class ReplayTrajectory:
    path:Path
    map_uid:str
    replay_id:int
    data:tuple[dict,...]
    race_ms:int
    input_timeline:tuple[dict,...]
    @classmethod
    def from_file(cls,path:Path|str,map_uid:str="",replay_id:int=0)->"ReplayTrajectory":
        source=Path(path)
        json_data=json.loads(source.read_text(encoding="utf-8-sig"))
        if json_data.get("schema")!="tm2020_replay_dataset_v1":
            raise ValueError(f"Unrecognized replay dataset: {source}")
        records=[g["result"] for g in json_data["ghosts"] if g["result"].get("stateInputRows")]
        if len(records)!=1:raise ValueError("Expected one ghost with vehicle states")
        g=records[0]
        frames=tuple(g["stateInputRows"])
        times=[int(r["tMs"]) for r in frames]
        if any(a>=b for a,b in zip(times,times[1:])):
            raise ValueError("Vehicle frames not strictly increasing")
        return cls(source,map_uid,replay_id,frames,parse_clock(g["raceTime"]),
                   tuple(g.get("inputEventTimeline",[])))
    @property
    def sample_count(self)->int:return len(self.data)
    @property
    def nominal_sample_time_ms(self)->int:return 50
    @property
    def counterfactual_simulation_supported(self)->bool:return False
    def frame_at(self,t_ms:int)->dict:
        """Closest recorded sample at or before t_ms. Never physics interpolation."""
        if not self.data: raise IndexError("No recorded vehicle samples")
        if t_ms<self.data[0]["tMs"] or t_ms>self.data[-1]["tMs"]:
            raise IndexError("Timestamp outside recorded trajectory")
        import bisect
        ix=bisect.bisect_right([r["tMs"] for r in self.data],t_ms)-1
        return self.data[ix]
    def valid_transitions(self)->Iterator[tuple[dict,dict]]:
        """Consecutive 50ms states before crossing finish, excluding telemetry tails.
        May include respawns; filter those separately for a dynamics model.
        """
        for a,b in zip(self.data,self.data[1:]):
            if b["tMs"]>self.race_ms:break
            if b["tMs"]-a["tMs"]==50:
                yield a,b

@dataclass(frozen=True)
class MapLayout:
    path:Path
    map_uid:str
    title:str
    blocks:tuple[dict,...]
    anchored_items:tuple[dict,...]
    @classmethod
    def from_file(cls,path:Path|str)->"MapLayout":
        source=Path(path)
        d=json.loads(source.read_text(encoding="utf-8-sig"))
        if d.get("kind")!="map":raise ValueError("Not Trackmania Map JSON")
        return cls(source,d["uid"],d.get("mapName",""),
                   tuple(d["blocks"]),tuple(d["items"]))
    @property
    def has_exact_collision_mesh(self)->bool:return False

@dataclass(frozen=True)
class ReplayMapPair:
    replay_id:int
    tmx_id:int
    map_uid:str
    trajectory:ReplayTrajectory
    layout:MapLayout
    source:str

class ReplayCorpus:
    """24-map public dataset including historical tests + newly ingested public TAS runs."""
    def __init__(self,repo:Path|str=REPO):
        self.repo=Path(repo)
        records=[]
        original=self.repo/"local"/"dataset-manifest.json"
        if original.is_file():
            d=json.loads(original.read_text(encoding="utf-8-sig"))
            records.extend((r,"initial") for r in d["linked"])
        external=self.repo/"local"/"corpus"/"manifest.json"
        if external.is_file():
            d=json.loads(external.read_text(encoding="utf-8-sig"))
            records.extend((r,"public_tas") for r in d["pairs"])
        seen=set()
        self._items=[]
        for r,source in records:
            uid=r["mapUid"]
            if uid in seen:raise ValueError(f"Duplicate map UID: {uid}")
            seen.add(uid)
            self._items.append((r,source))
    def __len__(self):return len(self._items)
    def entries(self)->list[dict]:
        return [dict(r) for r,_ in self._items]
    def by_index(self,index:int)->ReplayMapPair:
        r,source=self._items[index]
        m=MapLayout.from_file(self.repo/r["mapJson"])
        if m.map_uid!=r["mapUid"]:raise ValueError(f"MapUID mismatch: {m.map_uid} != {r['mapUid']}")
        rp=ReplayTrajectory.from_file(self.repo/r["datasetJson"],m.map_uid,int(r["replayId"]))
        return ReplayMapPair(int(r["replayId"]),int(r["tmxId"]),m.map_uid,rp,m,source)
    def group_split(self,heldout_fraction:float=0.2)->tuple[list[int],list[int]]:
        """Stable train/test by map UID, independent of file and ingestion ordering."""
        if not 0<heldout_fraction<1:raise ValueError("Fraction must be between 0 and 1")
        training=[];test=[]
        for i,(item,_) in enumerate(self._items):
            digest=hashlib.sha256(item["mapUid"].encode("utf-8")).digest()
            value=int.from_bytes(digest[:8],"big")/(2**64)
            (test if value<heldout_fraction else training).append(i)
        if not training or not test:raise ValueError("Split has an empty partition")
        return training,test
