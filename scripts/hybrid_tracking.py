"""Map-specific native feedforward/feedback. Explicit assisted-control evidence."""
import ctypes as C
import hashlib
import json
import os
import struct
from functools import lru_cache
from pathlib import Path
import numpy as np
from run_fast_ppo import ROOT
from vector_physics import VectorPhysics

DIR=ROOT/'local/training/hybrid-20261031'
UID='ypPmohQofd72MyTsIsijKfrJH98'
MAP=ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx'
API=ROOT/'local/training/adaptive-20261031/frozen/native/libtm2020_vector_physics.so'
PHYSICS=ROOT/'cache/reward-study-target/release/libtm2020_speed.so'
CORE=Path(os.environ.get('TM2020_HYBRID_CORE',Path(os.environ.get('TM2020_HARDCODE_NATIVE',ROOT/'native/build-hybrid'))/'libtm2020_trajectory.so'))


@lru_cache(maxsize=4)
def _native_checksum(path):
    try:
        lib=C.CDLL(path);fn=lib.tmhybrid_checksum
        fn.argtypes=[C.c_char_p,C.c_size_t];fn.restype=C.c_uint64
        return lib,fn
    except (OSError,AttributeError):return None


def asset_checksum(data):
    native=_native_checksum(str(CORE))
    if native is not None:return native[1](data,len(data))
    value=14695981039346656037
    for b in data:value=((value^b)*1099511628211)&((1<<64)-1)
    return value


def load_asset(path,*,map_path=MAP,uid=UID):
    data=Path(path).read_bytes()
    if len(data)<64 or data[:8]!=b'TMHYB001':raise ValueError('Invalid hybrid signature')
    value=asset_checksum(data[:-8])
    if value!=struct.unpack_from('<Q',data,len(data)-8)[0]:raise ValueError('Hybrid checksum differs')
    version,n,nx,nh,nu,ns=struct.unpack_from('<6I',data,8);offset=32
    if version not in (1,2,3,4,5,6,7,8) or nx!=12 or nh!=32 or not 100<=n<=10000 or ns!=64 or not 1<=nu<=64:raise ValueError('Invalid hybrid schema')
    extra_doubles=3 if version==3 else 12 if version==5 else 16 if version==6 else 32 if version in (7,8) else 0
    net_size=515 if version==8 else 449
    if len(data)!=32+nu+ns+(6+net_size+extra_doubles)*8+n*25*4+8:raise ValueError('Hybrid lengths differ')
    asset_uid=data[offset:offset+nu].decode();offset+=nu;map_sha=data[offset:offset+ns].decode();offset+=ns
    if asset_uid!=uid or map_sha!=hashlib.sha256(Path(map_path).read_bytes()).hexdigest():raise ValueError('Hybrid map differs')
    gains=np.frombuffer(data,dtype='<f8',count=6,offset=offset).copy();offset+=48
    network=np.frombuffer(data,dtype='<f8',count=net_size,offset=offset).copy();offset+=net_size*8
    if version in (3,5,6,7,8):
        validate_feedback_filter(np.frombuffer(data,dtype='<f8',count=3,offset=offset));offset+=24
    if version==5:
        validate_human_constraints(np.frombuffer(data,dtype='<f8',count=9,offset=offset));offset+=72
    if version==6:
        validate_human_action_envelope(np.frombuffer(data,dtype='<f8',count=13,offset=offset));offset+=104
    if version in (7,8):
        validate_human_context_envelope(np.frombuffer(data,dtype='<f8',count=29,offset=offset));offset+=232
    reference=np.frombuffer(data,dtype='<f4',count=n*25,offset=offset).reshape(n,25).copy()
    return reference,gains,network


def validate_feedback_filter(values):
    values=np.asarray(values,dtype='<f8')
    if (values.shape!=(3,) or not np.isfinite(values).all() or not 0<=values[0]<=8/127 or
        not 0<=values[1]<=1 or values[2] not in (10,20,30,40,50)):
        raise ValueError('Invalid feedback filter')
    return values


def validate_human_constraints(values):
    """v5 hard action envelope, measured from verified 100 Hz human inputs."""
    v=np.asarray(values,dtype='<f8')
    if v.shape!=(9,) or not np.isfinite(v).all():raise ValueError('Invalid human action constraints')
    step,changes,reversals,small,min_steer,pedals,min_gas,min_brake,max_abs=v
    if (not 1<=step<=254 or not 1<=changes<=100 or not 0<=reversals<=100 or
        not 0<=small<=100 or not 10<=min_steer<=1000 or not 1<=pedals<=100 or
        not 10<=min_gas<=5000 or not 10<=min_brake<=5000 or not 1<=max_abs<=127 or
        any(float(x).is_integer() is False for x in v)):
        raise ValueError('Human action constraints outside safe bounds')
    return v


def validate_human_action_envelope(values):
    """v6 includes both observed rolling-window and per-run human budgets."""
    v=np.asarray(values,dtype='<f8')
    if v.shape!=(13,) or not np.isfinite(v).all():raise ValueError('Invalid human action envelope')
    validate_human_constraints(v[:9])
    if any(not float(x).is_integer() for x in v[9:]):raise ValueError('Human run budgets must be integers')
    if any(x<1 or x>10000 for x in v[9:]):raise ValueError('Human run budget outside safe bounds')
    return v


def validate_human_context_envelope(values):
    """v7: rolling-window limits plus 5 route-local human action budgets."""
    v=np.asarray(values,dtype='<f8')
    if v.shape!=(29,) or not np.isfinite(v).all():raise ValueError('Invalid contextual human action envelope')
    validate_human_constraints(v[:9])
    if any(not float(x).is_integer() or x<1 or x>10000 for x in v[9:]):
        raise ValueError('Context budgets must be bounded positive integers')
    return v


def save_asset(path,reference,gains,network=None,*,map_path=MAP,uid=UID,version=1,feedback_filter=None,human_constraints=None):
    if version not in (1,2,3,4,5,6,7,8):raise ValueError('Invalid hybrid asset version')
    if (version==3)!=(feedback_filter is not None) and not (version in (5,6,7,8) and feedback_filter is not None):raise ValueError('Feedback filter is required only for v3/v5/v6/v7/v8')
    if (version in (5,6,7,8))!=(human_constraints is not None):raise ValueError('v5/v6/v7/v8 requires explicit human action constraints')
    extra=validate_feedback_filter(feedback_filter).tobytes() if version in (3,5,6,7,8) else b''
    if version==5:extra+=validate_human_constraints(human_constraints).tobytes()
    if version==6:extra+=validate_human_action_envelope(human_constraints).tobytes()
    if version==7:extra+=validate_human_context_envelope(human_constraints).tobytes()
    if version==8:extra+=validate_human_context_envelope(human_constraints).tobytes()
    reference=np.ascontiguousarray(reference,dtype='<f4');gains=np.asarray(gains,dtype='<f8')
    if reference.ndim!=2 or reference.shape[1]!=25 or gains.shape!=(6,):raise ValueError('Invalid hybrid asset')
    network_size=515 if version==8 else 449
    if network is None:network=np.zeros(network_size,dtype='<f8')
    network=np.asarray(network,dtype='<f8')
    if network.shape!=(network_size,) or not all(np.isfinite(v).all() for v in [reference,gains,network]):raise ValueError('Nonfinite or invalid network')
    uid=uid.encode();sha=hashlib.sha256(Path(map_path).read_bytes()).hexdigest().encode()
    data=b'TMHYB001'+struct.pack('<6I',version,len(reference),12,32,len(uid),len(sha))+uid+sha+gains.tobytes()+network.tobytes()+extra+reference.tobytes()
    checksum=asset_checksum(data)
    path=Path(path);temp=path.with_suffix('.tmp');temp.write_bytes(data+struct.pack('<Q',checksum));temp.replace(path)


def reference_asset():
    source=ROOT/'local/training/top10-20261030'
    rigid=np.load(source/'wr-100hz-rigid.npy').view(np.float32)
    controls=np.load(source/'wr-100hz-demonstration.npy')[:,48:51].astype(np.float32)
    reference=np.concatenate((rigid,controls),axis=1)
    return reference


def retime_pedals(reference,brake_ticks,gas_ticks,start=20,end=None,brake_width=0):
    result=reference.copy();end=len(reference) if end is None else min(end,len(reference))
    start=max(20,int(start));ticks=np.arange(start,end)
    for column,offset in ((23,brake_ticks),(22,gas_ticks)):
        result[start:end,column]=reference[np.clip(ticks-int(offset),0,len(reference)-1),column]
    if brake_width:
        flags=result[:,23]>.5;edges=np.diff(np.r_[False,flags,False].astype(np.int8))
        for lo,hi in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
            changed=max(lo,hi+int(brake_width))
            if changed>hi:result[max(start,hi):min(end,changed),23]=1.
            elif changed<hi:result[max(start,changed):min(end,hi),23]=0.
    return result


class Hybrid:
    def __init__(self,asset,n):
        self.n=n;self.lib=C.CDLL(str(CORE))
        self.lib.tmhybrid_open.argtypes=[C.c_char_p,C.c_uint32];self.lib.tmhybrid_open.restype=C.c_void_p
        self.lib.tmhybrid_close.argtypes=[C.c_void_p]
        self.lib.tmhybrid_reset.argtypes=[C.c_void_p,C.c_uint32]
        self.lib.tmhybrid_gains.argtypes=[C.c_void_p,C.POINTER(C.c_double)]
        self.lib.tmhybrid_actions.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.POINTER(C.c_uint32),C.POINTER(C.c_float),C.POINTER(C.c_double),C.POINTER(C.c_double)]
        self.handle=self.lib.tmhybrid_open(str(Path(asset).resolve()).encode(),n)
        if not self.handle:raise RuntimeError('Native hybrid asset rejected')
        self.features=np.zeros((n,12),dtype=np.float64);self.controls=np.zeros((n,3),dtype=np.float32)
    def reset(self,i):
        if self.lib.tmhybrid_reset(self.handle,i):raise RuntimeError('Invalid hybrid cursor')
    def gains(self,values):
        values=np.ascontiguousarray(values,dtype=np.float64)
        if values.shape!=(6,) or not np.isfinite(values).all():raise ValueError('Invalid gain vector')
        if self.lib.tmhybrid_gains(self.handle,values.ctypes.data_as(C.POINTER(C.c_double))):raise RuntimeError('Gains rejected')
    def commit(self,i,steer):
        self.lib.tmhybrid_commit.argtypes=[C.c_void_p,C.c_uint32,C.c_float]
        if self.lib.tmhybrid_commit(self.handle,i,float(steer)):raise RuntimeError('Invalid committed action')
    def govern_controls(self,commands,milliseconds):
        commands=np.ascontiguousarray(commands,dtype=np.float32)
        milliseconds=np.ascontiguousarray(milliseconds,dtype=np.uint32)
        if commands.ndim!=2 or commands.shape!=(self.n,3) or milliseconds.shape!=(self.n,):
            raise ValueError('Expected one timestamp and 3 controls per governor cursor')
        self.lib.tmhybrid_govern_controls.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.POINTER(C.c_uint32),C.POINTER(C.c_float)]
        out=np.empty_like(commands)
        result=self.lib.tmhybrid_govern_controls(self.handle,commands.ctypes.data_as(C.POINTER(C.c_float)),
            milliseconds.ctypes.data_as(C.POINTER(C.c_uint32)),out.ctypes.data_as(C.POINTER(C.c_float)))
        if result:raise RuntimeError('Hard action governor rejected recorded controls')
        return out
    def cursor_index(self,i):
        self.lib.tmhybrid_cursor.argtypes=[C.c_void_p,C.c_uint32];self.lib.tmhybrid_cursor.restype=C.c_uint32
        value=self.lib.tmhybrid_cursor(self.handle,i)
        if value==2**32-1:raise ValueError('Unknown controller cursor')
        return value
    def act(self,env,residuals=None):
        rigid=np.asarray([list(s.rigid_words) for s in env.states[:self.n]],dtype=np.uint32).view(np.float32)
        milliseconds=np.asarray([s.tick*10 for s in env.states[:self.n]],dtype=np.uint32)
        r=None if residuals is None else np.ascontiguousarray(residuals,dtype=np.float64)
        result=self.lib.tmhybrid_actions(self.handle,rigid.ctypes.data_as(C.POINTER(C.c_float)),milliseconds.ctypes.data_as(C.POINTER(C.c_uint32)),self.controls.ctypes.data_as(C.POINTER(C.c_float)),self.features.ctypes.data_as(C.POINTER(C.c_double)),None if r is None else r.ctypes.data_as(C.POINTER(C.c_double)))
        if result:raise RuntimeError('Hybrid batch failed')
        return self.controls.copy()
    def close(self):
        if self.handle:self.lib.tmhybrid_close(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def cases(seed,count=41,perturbed=True):
    rng=np.random.default_rng(seed);result=[]
    for i in range(count):
        result.append({'seed':36139877 if i==0 else int(rng.integers(1,4294967294)),
                       'warm':int(rng.integers(20,1700)),'duration':int(rng.integers(1,8)),
                       'kick':0. if not perturbed or i%5==0 else float(rng.choice([-1,1])*rng.uniform(.02,.1))})
    return result


def evaluate(asset,trial_cases,gains=None,retain=False):
    n=len(trial_cases)
    with VectorPhysics(n,decision_ticks=1,api_path=API,library=PHYSICS) as env,Hybrid(asset,n) as controller:
        if gains is not None:controller.gains(gains)
        for i,c in enumerate(trial_cases):env.reset(i,c['seed'])
        trace=[];active=np.ones(n,dtype=bool)
        for t in range(3500):
            if not active.any():break
            controls=controller.act(env)
            for i,c in enumerate(trial_cases):
                if c['warm']<=t<c['warm']+c['duration']:controls[i,2]=np.clip(controls[i,2]+c['kick'],-1,1)
            controls[:,2]=np.sign(controls[:,2])*np.floor(np.abs(controls[:,2])*127+.5)/127
            if retain:trace.append({'tick':t,'rigid':list(env.states[0].rigid_words),'controls':controls[0].tolist(),'features':controller.features[0].tolist()})
            env.step(controls)
            active=np.array([not(s.terminated or s.truncated) for s in env.states[:n]])
        trials=[dict(c,finishMs=int(s.finish_ms) if s.finish_ms>=0 else None,
                     checkpoints=int(s.checkpoints),tick=int(s.tick)) for c,s in zip(trial_cases,env.states[:n])]
    times=[c['finishMs'] for c in trials if c['finishMs'] is not None]
    result={'finishes':len(times),'count':n,'meanMs':float(np.mean(times)) if times else None,
            'medianMs':float(np.median(times)) if times else None,'bestMs':min(times) if times else None,
            'penalizedMeanMs':float(np.mean([c['finishMs'] or 40000 for c in trials])),
            'trials':trials,'referenceAssisted':True,'measuredInGame':False}
    return (result,trace) if retain else result
