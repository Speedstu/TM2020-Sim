"""Independent spectator simulation using actual trained PPO weights and native physics.

CRITICAL: these 16 cars are *spectator rollouts*. They are NOT the private
worlds inside the concurrent Codex training process. No training state mutated.
"""
from __future__ import annotations
import math, os, threading, time, sys
from pathlib import Path
import numpy as np
from common import ROOT,model_path
SCRIPTS=str(ROOT/'scripts')
if SCRIPTS not in sys.path:sys.path.insert(0,SCRIPTS)

def state_coords(s):
    words=np.asarray(list(s.rigid_words),dtype=np.uint32).view(np.float32)
    x,y,z=(float(v) for v in words[9:12])
    w,qx,qy,qz=(float(v) for v in words[12:16])
    fx=2*(qx*qz+w*qy)
    fz=1-2*(qx*qx+qy*qy)
    heading=math.atan2(fx,fz)
    if not all(math.isfinite(v) for v in (x,z,heading)) or s.reserved:
        return None
    return x,z,heading

class Spectator:
    def __init__(self,count=16):
        self.count=max(2,min(32,int(count)))
        self.lock=threading.Lock();self.stop=threading.Event()
        self.paused=threading.Event()
        self.reset=threading.Event()
        self.snapshot={'cars':[],'source':'PREPARING ENGINE','fps':0,'updates':0,'connected':False,
                       'error':None,'model':'—','finished':0}
        self.thread=threading.Thread(target=self.loop,daemon=False,name='trackvis-physics')
    def start(self):self.thread.start()
    def close(self):
        self.stop.set()
        if self.thread.is_alive():self.thread.join(timeout=7)
    def latest(self):
        with self.lock:return dict(self.snapshot)
    def store(self,**kwargs):
        with self.lock:self.snapshot={**self.snapshot,**kwargs}
    def loop(self):
        try:self.run()
        except Exception as e:
            self.store(error=str(e),source='SIMULATION ERROR',connected=False)
    def run(self):
        # Do not initialize CUDA here; spectator uses CPU NumPy inference to
        # avoid competing with the active PPO training on its NVIDIA GPU.
        os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
        os.environ.setdefault('OMP_NUM_THREADS','1')
        os.environ.setdefault('TM2020_PHYSICS_WORKERS','4')
        import torch
        from vector_physics import VectorPhysics
        from compare_hybrid_ppo import frame
        torch.set_num_threads(1)
        path=model_path()
        if path is None:raise RuntimeError('No trained PPO checkpoint found')
        data=torch.load(path,map_location='cpu',weights_only=True)
        if 'model' in data:data=data['model']
        a0w=data['actor.0.weight'].numpy().copy()
        a0b=data['actor.0.bias'].numpy().copy()
        a2w=data['actor.2.weight'].numpy().copy()
        a2b=data['actor.2.bias'].numpy().copy()
        discrete=a2w.shape[0]>3
        self.store(model=path.name,source='OFFLINE / INDEPENDENT SIMULATION',connected=True)
        rng=np.random.default_rng(9131)
        n=self.count;h=np.zeros((n,240),dtype=np.float64)
        trails=[[] for _ in range(n)]
        cooldown=np.zeros(n,dtype=np.int32)
        finished=0;total_steps=0
        with VectorPhysics(n) as env:
            for i in range(n):
                env.reset(i,91823+i*17)
            h[:]=np.tile(frame(env.observations),(1,5))
            last=time.monotonic()
            while not self.stop.is_set():
                if self.reset.is_set():
                    self.reset.clear()
                    for i in range(n):
                        env.reset(i,91823+i*17)
                        trails[i]=[]
                    h[:]=np.tile(frame(env.observations),(1,5))
                    finished=0;total_steps=0
                if self.paused.is_set():
                    self.stop.wait(.05);last=time.monotonic();continue
                # Sample learner's policy with small per-car perturbations.
                v=np.tanh(h@a0w.T+a0b)
                out=v@a2w.T+a2b
                gas=(out[:,0]>=0).astype(np.float32)
                brake=(out[:,1]>=0).astype(np.float32)
                if discrete:
                    idx=np.argmax(out[:,2:],axis=1)
                    steer=-1.+2.*idx.astype(float)/(len(out[0])-3)
                else:
                    steer=np.tanh(out[:,2])
                # Variance creates non-overlapping individual trajectories.
                noise=rng.normal(0,.006,size=n)
                controls=np.stack((gas,brake,np.clip(steer+noise,-1,1)),axis=1).astype(np.float32)
                env.step(controls)
                total_steps+=1
                cars=[]
                next_frames=frame(env.observations.copy())
                h[:,:-48]=h[:,48:].copy()
                h[:,-48:]=next_frames
                for i,s in enumerate(env.states[:n]):
                    coords=state_coords(s)
                    if coords and (not s.terminated and not s.truncated):
                        x,z,head=coords
                        trails[i].append((x,z))
                        if len(trails[i])>140:trails[i]=trails[i][-140:]
                    if s.terminated or s.truncated:
                        if s.finish_ms>0:finished+=1
                        cooldown[i]+=1
                        if cooldown[i]>=6:
                            env.reset(i,int(rng.integers(1,4000000000)))
                            h[i]=np.tile(frame(env.observations[i:i+1])[0],5)
                            trails[i]=[];cooldown[i]=0
                    else:cooldown[i]=0
                    if coords:
                        x,z,head=coords
                        cars.append({'id':i+1,'x':x,'z':z,'heading':head,
                            'speed':float(s.speed)*3.6,'checkpoint':int(s.checkpoints),
                            'tick':int(s.tick),'done':bool(s.terminated or s.truncated),
                            'trail':tuple(trails[i])})
                now=time.monotonic()
                dt=now-last
                last=now
                self.store(cars=cars,fps=round(1/dt,1) if dt>0 else 0,
                           updates=total_steps,finished=finished,connected=True)
                # Native physics advances 5*10ms. Respect real time but do not
                # accumulate a sleep backlog; low overhead on laptop Eco.
                self.stop.wait(max(0,.05-(time.monotonic()-now)))
