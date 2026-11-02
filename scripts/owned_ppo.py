"""Thin ctypes adapter to our SDK's C++ PPO trainer; no Python ML dependency."""
import ctypes as C
from pathlib import Path
import weakref


class Metrics(C.Structure):
    _fields_=[("size_bytes",C.c_uint32),("api_version",C.c_uint32)]+[
        (name,C.c_uint64) for name in ("transitions","optimizer_steps","minibatches","epochs")]+[
        (name,C.c_double) for name in ("policy_loss","value_loss","approx_kl","clip_fraction","gradient_norm")]+[
        ("kl_stopped",C.c_uint32),("reserved_zero",C.c_uint32)]


class OwnedPolicy:
    """Read-only native inference for independent evaluation/audits."""
    def __init__(self,dll,model,schema,observations=13,actions=3):
        self.dll=C.CDLL(str(Path(dll).resolve(strict=True)))
        self.nx,self.na=observations,actions
        self.dll.tm2020_policy_open.argtypes=[C.c_char_p,C.POINTER(C.c_void_p)]
        self.dll.tm2020_policy_schema.argtypes=[C.c_void_p]
        self.dll.tm2020_policy_schema.restype=C.c_char_p
        self.dll.tm2020_policy_predict.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_uint32,
            C.POINTER(C.c_double),C.c_uint32,C.POINTER(C.c_double)]
        self.dll.tm2020_policy_close.argtypes=[C.c_void_p]
        self.dll.tm2020_policy_close.restype=None
        self.handle=C.c_void_p()
        if self.dll.tm2020_policy_open(str(Path(model).resolve()).encode(),C.byref(self.handle)):
            raise ValueError("Cannot open evaluation policy")
        self._finalizer=weakref.finalize(self,self.dll.tm2020_policy_close,self.handle)
        if self.dll.tm2020_policy_schema(self.handle).decode()!=schema:
            self.close();raise ValueError("Evaluation observation schema differs")

    def predict(self,x):
        if len(x)!=self.nx:raise ValueError("Evaluation observation shape differs")
        a=(C.c_double*self.na)();v=C.c_double()
        if self.dll.tm2020_policy_predict(self.handle,(C.c_double*self.nx)(*x),self.nx,a,self.na,C.byref(v)):
            raise ValueError("Native evaluation prediction failed")
        return list(a),v.value

    def close(self):self._finalizer()


class OwnedPpo:
    def __init__(self,dll,observations,actions,schema,seed,hidden=32):
        self.dll=C.CDLL(str(Path(dll).resolve(strict=True)))
        self.nx,self.na=observations,actions
        double_ptr=C.POINTER(C.c_double)
        types={
            "create":[C.c_uint32,C.c_uint32,C.c_uint32,C.c_uint64,C.c_char_p,C.POINTER(C.c_void_p)],
            "sample":[C.c_void_p,double_ptr,C.c_uint32,double_ptr,C.c_uint32,double_ptr],
            "observe":[C.c_void_p,C.c_double,double_ptr,C.c_uint32,C.c_uint32,C.c_uint32,C.c_double],
            "cancel":[C.c_void_p],"update":[C.c_void_p,C.POINTER(Metrics)],
            "checkpoint":[C.c_void_p,C.c_char_p],"resume":[C.c_void_p,C.c_char_p],
            "export":[C.c_void_p,C.c_char_p],"rollout_csv":[C.c_void_p,C.c_char_p],
        }
        for name,args in types.items():
            fn=getattr(self.dll,"tm2020_trainer_"+name);fn.argtypes=args;fn.restype=C.c_int32
        self.dll.tm2020_trainer_last_error.restype=C.c_char_p
        self.dll.tm2020_trainer_close.argtypes=[C.c_void_p]
        self.dll.tm2020_trainer_close.restype=None
        self.handle=C.c_void_p()
        self.check(self.dll.tm2020_trainer_create(observations,actions,hidden,seed,schema.encode(),C.byref(self.handle)))
        self._finalizer=weakref.finalize(self,self.dll.tm2020_trainer_close,self.handle)

    def check(self,code):
        if code:raise RuntimeError(self.dll.tm2020_trainer_last_error().decode())

    def array(self,x):
        if len(x)!=self.nx:raise ValueError("Observation shape mismatch")
        return (C.c_double*self.nx)(*x)

    def sample(self,x):
        action=(C.c_double*self.na)();value=C.c_double()
        self.check(self.dll.tm2020_trainer_sample(self.handle,self.array(x),self.nx,action,self.na,C.byref(value)))
        return list(action)

    def observe(self,reward,x,truncated=False,duration=1.0,terminated=False):
        self.check(self.dll.tm2020_trainer_observe(self.handle,reward,self.array(x),self.nx,int(terminated),int(truncated),duration))

    def cancel(self):self.check(self.dll.tm2020_trainer_cancel(self.handle))

    def update(self):
        metrics=Metrics();metrics.size_bytes=C.sizeof(metrics);metrics.api_version=1
        self.check(self.dll.tm2020_trainer_update(self.handle,C.byref(metrics)))
        return {name:getattr(metrics,name) for name,_ in metrics._fields_ if name not in ("size_bytes","api_version","reserved_zero")}

    def file(self,operation,path):
        self.check(getattr(self.dll,"tm2020_trainer_"+operation)(self.handle,str(Path(path).resolve()).encode("utf-8")))

    def close(self):self._finalizer()
