"""Audit-only ctypes adapter to the in-process native training environment."""
import ctypes as C
from pathlib import Path

def state_fields(nx):
    return [('observation',C.c_double*nx)]+[(n,C.c_double) for n in ('reward','progress','cross_track','speed')]+[
        ('rigid_words',C.c_uint32*22)]+[(n,C.c_uint32) for n in ('tick','checkpoints','terminated','truncated','advanced_ticks')]+[
        ('finish_ms',C.c_int32),('controls',C.c_float*3),('reserved',C.c_uint32)]

class State(C.Structure):
    _fields_=state_fields(32)

class State48(C.Structure):
    _fields_=state_fields(48)

class FastEngine:
    def __init__(self,library,map_path=None,packs=None,route=None,horizon=4500,clone=None):
        self.lib=C.CDLL(str(Path(library).resolve(strict=True)))
        self.version=self.lib.tmfast_version()
        if self.version not in (1,2,3,4):raise RuntimeError("Unknown fast physics ABI")
        self.state_type=State48 if self.version>=3 else State
        pointer=C.POINTER(self.state_type)
        self.lib.tmfast_open.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_uint32]
        self.lib.tmfast_open.restype=C.c_void_p
        self.lib.tmfast_clone.argtypes=[C.c_void_p];self.lib.tmfast_clone.restype=C.c_void_p
        self.lib.tmfast_reset.argtypes=[C.c_void_p,C.c_uint32,pointer]
        self.lib.tmfast_step.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_uint32,pointer]
        self.lib.tmfast_step_controls.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.c_uint32,pointer]
        self.lib.tmfast_configure.argtypes=[C.c_void_p,C.c_double,C.c_double,C.c_double]
        if self.version>=3:
            self.lib.tmfast_bank_size.argtypes=[C.c_void_p]
            self.lib.tmfast_bank_size.restype=C.c_uint32
            self.lib.tmfast_reset_bank.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,pointer]
        if self.version>=4:self.lib.tmfast_configure_planner.argtypes=[C.c_void_p,C.c_uint32]
        self.lib.tmfast_close.argtypes=[C.c_void_p]
        self.lib.tmfast_last_error.restype=C.c_char_p
        self.handle=(self.lib.tmfast_clone(clone.handle) if clone is not None else
            self.lib.tmfast_open(*(str(Path(p).resolve(strict=True)).encode() for p in (map_path,packs,route)),horizon))
        if not self.handle:raise RuntimeError(self.lib.tmfast_last_error().decode())
        self.state=self.state_type()
    def check(self,code):
        if code:raise RuntimeError(self.lib.tmfast_last_error().decode())
    def configure(self,lookahead,gain,residual=.35):self.check(self.lib.tmfast_configure(self.handle,lookahead,gain,residual))
    def planner(self,enabled=True):self.check(self.lib.tmfast_configure_planner(self.handle,int(enabled)))
    def reset(self,seed=2026):
        self.check(self.lib.tmfast_reset(self.handle,seed,C.byref(self.state)));return self.state
    def bank_size(self):return self.lib.tmfast_bank_size(self.handle) if self.version>=3 else 1
    def reset_bank(self,seed,bank):
        self.check(self.lib.tmfast_reset_bank(self.handle,seed,bank,C.byref(self.state)));return self.state
    def step(self,action,repeat=5):
        self.check(self.lib.tmfast_step(self.handle,(C.c_double*3)(*action),repeat,C.byref(self.state)));return self.state
    def step_controls(self,controls,repeat=5):
        self.check(self.lib.tmfast_step_controls(self.handle,(C.c_float*3)(*controls),repeat,C.byref(self.state)));return self.state
    def close(self):
        if self.handle:self.lib.tmfast_close(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
