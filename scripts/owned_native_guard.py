"""Compiled byte/instruction guard for the SAME private Unicorn engine.

The DLL never opens a process or executes game instructions natively. Unicorn
still executes the pinned original instructions. This only removes per-access
Python/ctypes callbacks; unknown bytes and changed instructions still stop it.
"""
import ctypes as C
from pathlib import Path
import weakref
from unicorn.unicorn_py3.unicorn import uclib


class _Api(C.Structure):
    _fields_=[(name,C.c_void_p) for name in
              ("hook_add","hook_del","mem_read","reg_read","emu_stop")]


class _Fault(C.Structure):
    _fields_=[(name,C.c_uint64) for name in ("kind","address","start","size","pc")]


def _release(dll,engine_ref,handle):
    # Finalizers run in reverse creation order at interpreter shutdown: detach
    # hooks before Unicorn's earlier engine finalizer calls uc_close.
    if engine_ref() is None:dll.tmguard_abandon(handle)
    else:dll.tmguard_destroy(handle)


class NativeGuard:
    def __init__(self,mu,path):
        self.mu=mu  # Keep the engine alive until hooks are detached.
        self.path=Path(path).resolve(strict=True)
        self.dll=C.CDLL(str(self.path))
        signatures={
            "create":([C.c_void_p,C.POINTER(_Api)],C.c_void_p),
            "page":([C.c_void_p,C.c_uint64,C.c_void_p,C.c_int],C.c_int),
            "range":([C.c_void_p,C.c_uint64,C.c_uint64,C.c_int],C.c_int),
            "platform":([C.c_void_p,C.c_uint64],C.c_int),
            "start":([C.c_void_p],C.c_int),
            "fault":([C.c_void_p,C.POINTER(_Fault)],C.c_int),
            "touched":([C.c_void_p,C.POINTER(C.c_uint64),C.c_uint64],C.c_uint64),
            "clear":([C.c_void_p],None),
            "counts":([C.c_void_p,C.POINTER(C.c_uint64)],None),
            "destroy":([C.c_void_p],None),
            "abandon":([C.c_void_p],None),
            "write_initialization":([C.c_void_p,C.c_int],None),
            "access":([C.c_void_p,C.c_uint64,C.c_int,C.c_int],None),
            "initialized_pages":([C.c_void_p,C.POINTER(C.c_uint64),C.c_uint64],C.c_uint64),
            "initialized_mask":([C.c_void_p,C.c_uint64,C.c_void_p,C.c_int],C.c_int),
        }
        for name,(args,result) in signatures.items():
            fn=getattr(self.dll,"tmguard_"+name)
            fn.argtypes,fn.restype=args,result
            setattr(self,name,fn)
        api=_Api(*(C.cast(getattr(uclib,"uc_"+name),C.c_void_p).value
                   for name,_ in _Api._fields_))
        self.handle=self.create(mu._uch,C.byref(api))
        if not self.handle:raise RuntimeError("Cannot create native Unicorn guard")
        self._finalizer=weakref.finalize(self,_release,self.dll,weakref.ref(mu),self.handle)
        self._masks={}

    def add_page(self,page,raw,code=False):
        if len(raw)!=4096:raise ValueError("Guard page requires 4096 bytes")
        if not self.page(self.handle,page,C.c_char_p(bytes(raw)),int(code)):
            raise RuntimeError("Cannot register guard page")

    def sync_masks(self,data):
        if not self.handle:raise ValueError("Compiled guard has been closed")
        # The test/research API can replace a sparse page tuple deliberately.
        # Retain the old bytes object to prevent an id from being reused.
        for page,(mask,_,_) in data.items():
            if self._masks.get(page) is not mask:
                self.add_page(page,mask)
                self._masks[page]=mask
        if self._masks.keys()!=data.keys():
            raise ValueError("Removing mapped pages requires a new machine")

    def fault_info(self):
        result=_Fault()
        if self.fault(self.handle,C.byref(result)):
            return {name:getattr(result,name) for name,_ in result._fields_}

    def touched_pages(self):
        n=self.touched(self.handle,None,0)
        result=(C.c_uint64*n)()
        if self.touched(self.handle,result,n)!=n:
            raise RuntimeError("Guard changed outside synchronous execution")
        return set(result)

    def counters(self):
        result=(C.c_uint64*2)()
        self.counts(self.handle,result)
        return dict(instructions=result[0],memoryAccesses=result[1])

    def save_initialized(self):
        n=self.initialized_pages(self.handle,None,0)
        pages=(C.c_uint64*n)()
        if self.initialized_pages(self.handle,pages,n)!=n:raise RuntimeError("Initialized page count changed")
        result={}
        for page in pages:
            mask=(C.c_ubyte*4096)()
            if not self.initialized_mask(self.handle,page,mask,0):raise RuntimeError("Cannot snapshot initialized bytes")
            result[page]=bytes(mask)
        return result

    def restore_initialized(self,pages):
        for page,mask in pages.items():
            if len(mask)!=4096:raise ValueError("Initialized mask length differs")
            buf=(C.c_ubyte*4096).from_buffer_copy(mask)
            if not self.initialized_mask(self.handle,page,buf,1):raise ValueError("Invalid initialized-byte checkpoint")

    def close(self):
        if getattr(self,"handle",None):
            self._finalizer()
            self.handle=None
