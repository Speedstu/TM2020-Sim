"""Gymnasium interface to the asset-loaded external engine; no game runtime."""
from pathlib import Path
import sys
import numpy as np
try:
    import gymnasium as gym
except ModuleNotFoundError:
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"tools/rl-python"))
    import gymnasium as gym

from force_worker_fixture import require
from headless_engine import HeadlessEngine,OBSERVATIONS,SCHEMA,race_reward

ACTION_SCHEMA=SCHEMA+"|actions=unit_pedals_steering3_v1"


def encode(state):
    return np.asarray(state["observation"],dtype=np.float32)


class TrackmaniaHeadlessEnv(gym.Env):
    metadata={"render_modes":[]}

    def __init__(self,host,map_path,packs,log_folder,horizon=2500,repeat=5,seed=2026,extension_sha256=None,car=None):
        require(type(horizon) is int and 1<=horizon<=100_000 and type(repeat) is int and 1<=repeat<=1000,
            "Invalid headless episode horizon/repeat")
        self.host,self.map,self.packs=host,map_path,packs
        self.log_folder=Path(log_folder);self.log_folder.mkdir(parents=True,exist_ok=True)
        self.horizon,self.repeat=horizon,repeat;self.engine=None;self.episode_done=True;self.launch_count=0
        self.extension_sha256,self.car=extension_sha256,car
        self.observation_space=gym.spaces.Box(-np.inf,np.inf,shape=(OBSERVATIONS,),dtype=np.float32)
        self.action_space=gym.spaces.Box(-1.0,1.0,shape=(3,),dtype=np.float32)
        self._open(seed)

    def _open(self,seed):
        if self.engine:self.engine.close()
        log=self.log_folder/f"engine-{self.launch_count:04d}.log";self.launch_count+=1
        self.engine=HeadlessEngine(self.host,self.map,self.packs,log,seed=seed,max_ticks=self.horizon,
            extension_sha256=self.extension_sha256,car=self.car)

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        require(not options,"No headless reset options are defined")
        if seed is not None:
            require(type(seed) is int and 0<=seed<2**32,"Replay seed must be an unsigned 32-bit integer")
            if seed!=self.engine.seed:self._open(seed)
        state=self.engine.reset();self.episode_done=False
        return encode(state),dict(physics=state,mapSha256=self.engine.map_sha256,
            completeExactPhysicsQualified=False)

    def step(self,action):
        require(not self.episode_done,"Reset the headless episode before stepping")
        action=np.asarray(action,dtype=np.float32)
        require(action.shape==(3,) and np.isfinite(action).all() and (np.abs(action)<=1).all(),
            "Action must be a finite [-1,1] triple")
        values=action.astype(np.float64).tolist()
        controls=[(values[0]+1)/2,(values[1]+1)/2,values[2]]
        before=self.engine.state
        try:state=self.engine.step(controls,min(self.repeat,self.horizon-before["tick"]))
        except Exception:self.episode_done=True;raise
        terminated=state["finished"];truncated=not terminated and state["tick"]>=self.horizon
        self.episode_done=terminated or truncated
        return encode(state),race_reward(before,state),terminated,truncated,dict(
            physics=state,controls=controls,advancedTicks=state["tick"]-before["tick"],
            completeExactPhysicsQualified=False)

    def close(self):
        if self.engine:self.engine.close();self.engine=None
