"""Local process adapter for the separately licensed, pinned Gearbox host.

No game process, Openplanet, sparse snapshot or live-memory fallback is used.
The external engine's fidelity is an explicit validation question.
"""
import hashlib
import json
import math
from pathlib import Path
import queue
import subprocess
import threading

from force_worker_fixture import require

UPSTREAM="e0583ee55168e950a65a645778e591bd26b6a0f2"
PROTOCOL="tm2020_gearbox_host_v1"
SCHEMA="tm2020_gearbox_geometry233_v1"
OBSERVATIONS=233


class EngineCommandError(RuntimeError):
    def __init__(self,response):
        self.response=response
        super().__init__(response.get("error","Engine command failed"))


class HeadlessEngine:
    def __init__(self,host,map_path,packs,log,max_ticks=100_000,seed=2026,timeout=180,extension_sha256=None,car=None):
        self.host=Path(host).resolve(strict=True);self.map=Path(map_path).resolve(strict=True)
        self.packs=Path(packs).resolve(strict=True)
        require(type(max_ticks) is int and 1<=max_ticks<=100_000,"Invalid engine lifetime budget")
        require(type(seed) is int and 0<=seed<2**32,"Invalid engine replay seed")
        require(car is None or car in ("CarSport","CarSnow","CarRally","CarDesert"),"Unsupported explicit car")
        self.seed=seed;self.map_sha256=hashlib.sha256(self.map.read_bytes()).hexdigest()
        self.host_sha256=hashlib.sha256(self.host.read_bytes()).hexdigest()
        self.log_path=Path(log);self.log_path.parent.mkdir(parents=True,exist_ok=True)
        self._log=self.log_path.open("x",encoding="utf-8")
        self._responses=queue.Queue();self.closed=False
        try:
            command=[str(self.host),"--map",str(self.map),"--packs",str(self.packs),
                "--max-ticks",str(max_ticks),"--seed",str(seed)]
            if car is not None:command += ["--car",car]
            self.process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=self._log,text=True,encoding="utf-8",bufsize=1,
                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            def read():
                try:
                    for line in self.process.stdout:
                        if len(line)>1024*1024:raise ValueError("Oversized engine response")
                        self._responses.put(json.loads(line))
                except Exception as error:self._responses.put(error)
                finally:self._responses.put(None)
            self._reader=threading.Thread(target=read,daemon=True);self._reader.start()
            self.ready=self._receive(timeout)
            require(self.ready.get("protocol")==PROTOCOL and self.ready.get("upstreamRevision")==UPSTREAM
                and self.ready.get("observationSchema")==SCHEMA and self.ready.get("observationCount")==OBSERVATIONS
                and self.ready.get("coldMapLoadedFromInstalledAssets") is True
                and self.ready.get("openplanetUsed") is False and self.ready.get("sourceGameProcessAccessed") is False
                and self.ready.get("physicsExtensionSha256")==extension_sha256
                and self.ready.get("initialCarOverride")==car,
                "Unexpected external engine identity/protocol")
            self.state=self._validate(self.ready["state"])
        except Exception:
            self.close();raise

    def _receive(self,timeout=30):
        try:value=self._responses.get(timeout=timeout)
        except queue.Empty as error:raise TimeoutError("Engine response deadline expired; see "+str(self.log_path)) from error
        if isinstance(value,Exception):raise value
        if value is None:raise RuntimeError("Engine exited; see "+str(self.log_path))
        require(isinstance(value,dict) and type(value.get("ok")) is bool,"Malformed engine response")
        if not value["ok"]:raise EngineCommandError(value)
        return value

    def request(self,command):
        require(not self.closed,"Engine is closed")
        raw=json.dumps(command,separators=(",",":"),allow_nan=False)
        require(len(raw)<=65536,"Engine command size bound")
        self.process.stdin.write(raw+"\n");self.process.stdin.flush()
        return self._receive()["result"]

    @staticmethod
    def _validate(state):
        require(state.get("observationSchema")==SCHEMA and len(state.get("observation",[]))==OBSERVATIONS
            and all(type(x) in (int,float) and math.isfinite(x) for x in state["observation"]),
            "Invalid external physics observation")
        require(len(state.get("rigidWords",[]))==22 and all(type(x) is int and 0<=x<2**32 for x in state["rigidWords"]),
            "Invalid external rigid-state words")
        require(type(state.get("tick")) is int and state["tick"]>=0 and type(state.get("finished")) is bool,
            "Invalid external clock/finish state")
        return state

    def step(self,controls,ticks=5):
        require(isinstance(controls,(list,tuple)) and len(controls)==3
            and all(type(x) in (int,float) and math.isfinite(x) for x in controls)
            and 0<=controls[0]<=1 and 0<=controls[1]<=1 and abs(controls[2])<=1,
            "Controls require [gas,brake,steering] in [0,1],[0,1],[-1,1]")
        require(type(ticks) is int and 1<=ticks<=1000,"Invalid engine action repeat")
        self.state=self._validate(self.request(dict(op="step",controls=controls,ticks=ticks)))
        return self.state

    def reset(self):
        self.state=self._validate(self.request(dict(op="reset")));return self.state

    def save(self):return self.request(dict(op="save"))["id"]

    def restore(self,checkpoint):
        self.state=self._validate(self.request(dict(op="restore",id=checkpoint)));return self.state

    def release(self,checkpoint):self.request(dict(op="release",id=checkpoint))

    def close(self):
        if getattr(self,"closed",False):return
        if hasattr(self,"process"):
            if self.process.poll() is None:
                if hasattr(self,"ready"):
                    try:self.request(dict(op="quit"))
                    except Exception:pass
                else:self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)
            for stream in (self.process.stdin,self.process.stdout):
                if stream:stream.close()
            if hasattr(self,"_reader"):self._reader.join(timeout=1)
        self._log.close();self.closed=True

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def race_reward(before,after):
    """Explicit shaping; checkpoint and finish decisions come from the engine."""
    passed=after["checkpointsPassed"]-before["checkpointsPassed"]
    require(passed>=0,"Checkpoint progress went backwards without an episode reset")
    progress=0.01*(before["goalDistanceMetres"]-after["goalDistanceMetres"]) if passed==0 else 0.0
    finish=100.0 if after["finished"] and not before["finished"] else 0.0
    elapsed=after["tick"]-before["tick"]
    require(elapsed>0,"No original engine tick was advanced")
    return progress+10.0*passed+finish-0.0002*elapsed
