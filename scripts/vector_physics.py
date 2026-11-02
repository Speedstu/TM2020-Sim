"""One batched FFI call per physics step, with persistent native workers."""
import ctypes as C
from pathlib import Path
import numpy as np
from fast_engine import State48
from run_fast_ppo import ROOT,steam_packs

class VectorPhysics:
    def __init__(self,n=16,*,decision_ticks=5,api_path=None,library=None,map_path=None,replay=None,horizon=None,internal_controls=False,normal_inputs=False):
        if normal_inputs and (internal_controls or decision_ticks!=1):raise ValueError('Normal recorded inputs require 100Hz, without the legacy frozen-history mode')
        self.normal_inputs=normal_inputs
        if decision_ticks not in (1,5):raise ValueError('Decision interval must be 1 or 5 ticks')
        self.n=n;self.decision_ticks=decision_ticks;self.api=C.CDLL(str(api_path or ROOT/'native/build-linux/libtm2020_vector_physics.so'))
        self.api.tmvec_open.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_uint32];self.api.tmvec_open.restype=C.c_void_p
        self.api.tmvec_states.argtypes=[C.c_void_p];self.api.tmvec_states.restype=C.POINTER(State48)
        self.api.tmvec_reset.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32]
        self.api.tmvec_step.argtypes=[C.c_void_p,C.POINTER(C.c_float)]
        self.api.tmvec_close.argtypes=[C.c_void_p];self.api.tmvec_error.restype=C.c_char_p
        self.library=Path(library or ROOT/'cache/reward-study-target/release/libtm2020_speed.so')
        self.map=Path(map_path or ROOT/'local/campaign-2026-autumn/Autumn-2026-01.Map.Gbx')
        if horizon is not None:
            if not hasattr(self.api,'tmvec_open_period_horizon'):raise RuntimeError('Native batch lacks horizon ABI')
            self.api.tmvec_open_period_horizon.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_char_p,C.c_uint32,C.c_uint32,C.c_uint32]
            self.api.tmvec_open_period_horizon.restype=C.c_void_p
            self.handle=self.api.tmvec_open_period_horizon(str(self.library).encode(),str(self.map).encode(),str(steam_packs()).encode(),str(replay or '/dev/null').encode(),n,decision_ticks,horizon)
        elif decision_ticks!=5 or replay is not None:
            if not hasattr(self.api,'tmvec_open_period'):raise RuntimeError('Native batch lacks explicit cadence/bank ABI')
            self.api.tmvec_open_period.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_char_p,C.c_uint32,C.c_uint32];self.api.tmvec_open_period.restype=C.c_void_p
            self.handle=self.api.tmvec_open_period(str(self.library).encode(),str(self.map).encode(),str(steam_packs()).encode(),str(replay or '/dev/null').encode(),n,decision_ticks)
        else:self.handle=self.api.tmvec_open(str(self.library).encode(),str(self.map).encode(),str(steam_packs()).encode(),n)
        if not self.handle:raise RuntimeError(self.api.tmvec_error().decode())
        if internal_controls or normal_inputs:
            if not hasattr(self.api,'tmvec_set_control_mode'):raise RuntimeError('Native batch lacks internal control ABI')
            self.api.tmvec_set_control_mode.argtypes=[C.c_void_p,C.c_uint32]
            self.check(self.api.tmvec_set_control_mode(self.handle,int(internal_controls)))
        self.states=self.api.tmvec_states(self.handle)
        self.buffer=(State48*n).from_address(C.addressof(self.states.contents))
        self.observations=np.ndarray((n,48),dtype=np.float64,buffer=self.buffer,strides=(C.sizeof(State48),8))
        self.banks=1
        if hasattr(self.api,'tmvec_bank_count'):
            self.api.tmvec_bank_count.argtypes=[C.c_void_p];self.api.tmvec_bank_count.restype=C.c_uint32
            self.banks=self.api.tmvec_bank_count(self.handle)
            self.api.tmvec_reset_bank.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32]
            self.api.tmvec_step_one.argtypes=[C.c_void_p,C.c_uint32,C.POINTER(C.c_float)]
    def check(self,result):
        if result:raise RuntimeError(self.api.tmvec_error().decode())
    def reset(self,i,seed):self.check(self.api.tmvec_reset(self.handle,i,seed))
    def reset_bank(self,i,seed,bank):
        if not hasattr(self.api,'tmvec_reset_bank'):raise RuntimeError('Native batch lacks bank ABI')
        self.check(self.api.tmvec_reset_bank(self.handle,i,seed,bank))
    def step_one(self,i,action):
        action=np.ascontiguousarray(action,dtype=np.float32)
        if action.shape!=(3,) or not np.isfinite(action).all():raise ValueError('Invalid warmup action')
        if self.normal_inputs:self.validate_recorded_actions(action[None,:])
        self.check(self.api.tmvec_step_one(self.handle,i,action.ctypes.data_as(C.POINTER(C.c_float))))
    def preview(self):
        self.api.tmvec_preview.argtypes=[C.c_void_p,C.POINTER(C.c_double)]
        out=np.empty((self.n,72),dtype=np.float64)
        self.check(self.api.tmvec_preview(self.handle,out.ctypes.data_as(C.POINTER(C.c_double))))
        out[:,13:15]=0.
        return out
    def save_checkpoint(self,i,slot):
        self.api.tmvec_save_checkpoint.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32]
        self.check(self.api.tmvec_save_checkpoint(self.handle,i,slot))
    def preview_one(self,i):
        self.api.tmvec_preview_one.argtypes=[C.c_void_p,C.c_uint32,C.POINTER(C.c_double)]
        out=np.empty(72,dtype=np.float64)
        self.check(self.api.tmvec_preview_one(self.handle,i,out.ctypes.data_as(C.POINTER(C.c_double))))
        out[13:15]=0.
        return out
    def restore_checkpoint(self,i,slot,seed):
        self.api.tmvec_restore_checkpoint.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_uint32]
        self.check(self.api.tmvec_restore_checkpoint(self.handle,i,slot,seed))
    def step(self,actions):
        actions=np.ascontiguousarray(actions,dtype=np.float32)
        if actions.shape!=(self.n,3) or not np.isfinite(actions).all():raise ValueError('Invalid action batch')
        if self.normal_inputs:self.validate_recorded_actions(actions)
        self.check(self.api.tmvec_step(self.handle,actions.ctypes.data_as(C.POINTER(C.c_float))))
    @staticmethod
    def validate_recorded_actions(actions):
        if not np.isin(actions[:,:2],[0.,1.]).all() or (np.abs(actions[:,2])>1).any() or not np.allclose(actions[:,2]*127,np.rint(actions[:,2]*127),atol=1e-5,rtol=0):
            raise ValueError('Recorded interface requires binary pedals and signed i8/127 steering; no hidden post-processing')
    def close(self):
        if self.handle:self.api.tmvec_close(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
