"""Route-free headless physics and the exact same external perception encoder."""
import ctypes as C
from pathlib import Path
from fast_engine import FastEngine

SCHEMA = ('tm2020_generalist48_v1|controls=binary_pedals_i8_steer|'
          'perception=static_rays33_goal_aabb_v1')

class GeneralistEngine(FastEngine):
    def __init__(self, library, map_path=None, packs=None, horizon=4500, clone=None,curriculum_replay=None):
        super().__init__(library, map_path, packs, curriculum_replay or Path('/dev/null'), horizon, clone)
        if not hasattr(self.lib, 'tmgen_observe'):
            self.close()
            raise RuntimeError('This library has no route-free perception ABI')
        self.lib.tmgen_observe.argtypes = [C.c_void_p, C.POINTER(C.c_float), C.c_uint32, C.POINTER(C.c_double)]
        self.lib.tmgen_raw.argtypes = [C.c_void_p, C.POINTER(C.c_float)]
        self.configure(10., 3., 1.)

    def raw(self):
        values = (C.c_float * 21)()
        self.check(self.lib.tmgen_raw(self.handle, values))
        return tuple(values)

    def observe(self, raw, reset=False):
        if len(raw) != 21:
            raise ValueError('Expected 21 current telemetry floats')
        values = (C.c_double * 48)()
        self.check(self.lib.tmgen_observe(self.handle, (C.c_float * 21)(*raw), reset, values))
        return tuple(values)
    def observe_preview(self,raw,reset=False):
        if len(raw)!=24:raise ValueError('Expected 24 current telemetry floats')
        self.lib.tmgen_observe72.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.c_uint32,C.POINTER(C.c_double)]
        values=(C.c_double*72)()
        self.check(self.lib.tmgen_observe72(self.handle,(C.c_float*24)(*raw),reset,values))
        return tuple(values)
