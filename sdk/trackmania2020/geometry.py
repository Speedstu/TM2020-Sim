"""Zero-copy batch BVH ray queries against EXPORTED PARTIAL collision geometry.

The game itself, Stadium's standard blocks and their colliders are not reproduced.
Tested only on meshes present in the map's EmbeddedZipData Item.Gbx physical_shape.
"""
from __future__ import annotations
import ctypes
from pathlib import Path
import numpy as np

REPO=Path(__file__).resolve().parents[2]
class PartialCollisionWorld:
    """In-process C++ BVH with deterministic read-only ray casts, not physical simulation."""
    def __init__(self, mesh_obj: str|Path, native_library: str|Path|None = None):
        dll=Path(native_library) if native_library is not None else REPO/"bin"/"TrackrayNative.dll"
        if not dll.is_file():raise FileNotFoundError(f"Native library not built: {dll}")
        self._lib=ctypes.CDLL(str(dll))
        self._lib.tm_world_open.argtypes=[ctypes.c_char_p]
        self._lib.tm_world_open.restype=ctypes.c_void_p
        self._lib.tm_world_close.argtypes=[ctypes.c_void_p]
        self._lib.tm_world_close.restype=None
        self._lib.tm_last_error.restype=ctypes.c_char_p
        self._lib.tm_world_triangle_count.argtypes=[ctypes.c_void_p]
        self._lib.tm_world_triangle_count.restype=ctypes.c_longlong
        arrayptr=ctypes.POINTER(ctypes.c_double)
        self._lib.tm_world_cast_batch.argtypes=[ctypes.c_void_p,arrayptr,ctypes.c_longlong,arrayptr]
        self._lib.tm_world_cast_batch.restype=ctypes.c_int
        self._handle=self._lib.tm_world_open(str(Path(mesh_obj).resolve()).encode("utf-8"))
        if not self._handle:
            raise RuntimeError("BVH loading failed: "+self._lib.tm_last_error().decode("utf-8",errors="replace"))
        self.triangle_count=int(self._lib.tm_world_triangle_count(self._handle))
        self.mesh=str(Path(mesh_obj).resolve())

    def close(self)->None:
        if getattr(self,"_handle",None):
            self._lib.tm_world_close(self._handle)
            self._handle=None

    def __enter__(self):return self
    def __exit__(self,exc_type,exc,tb):self.close()
    def __del__(self):self.close()

    def raycast(self,rays:np.ndarray)->np.ndarray:
        """Input float64 array shape (N,7): origin XYZ, direction XYZ, max distance.
        Output float64 shape (N,9): hit, distance, XYZ hit, XYZ normal, triangle ID.
        On misses, hit=0 and hit values are NaN (triangle ID=-1).
        """
        if not self._handle:raise RuntimeError("Collision world was closed")
        rays=np.asarray(rays,dtype=np.float64)
        if rays.ndim!=2 or rays.shape[1]!=7:raise ValueError("Expected float64 rays Nx7")
        if not rays.flags["C_CONTIGUOUS"]:rays=np.ascontiguousarray(rays)
        if np.any(~np.isfinite(rays)) or np.any(np.linalg.norm(rays[:,3:6],axis=1)<1e-12) or np.any(rays[:,6]<=0):
            raise ValueError("Invalid rays: non-finite values, zero directions or nonpositive max distance")
        out=np.empty((len(rays),9),dtype=np.float64)
        rc=self._lib.tm_world_cast_batch(
            ctypes.c_void_p(self._handle),
            rays.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            len(rays),
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        if rc!=0:raise RuntimeError(self._lib.tm_last_error().decode("utf-8",errors="replace"))
        return out

    def downcast(self,positions:np.ndarray,height:float=2.0,length:float=8.0)->np.ndarray:
        pos=np.asarray(positions,dtype=np.float64)
        if pos.ndim!=2 or pos.shape[1]!=3:raise ValueError("Positions must be Nx3")
        n=len(pos)
        rays=np.empty((n,7),dtype=np.float64)
        rays[:,:3]=pos
        rays[:,1]+=height
        rays[:,3:6]=(0,-1,0)
        rays[:,6]=length
        return self.raycast(rays)
