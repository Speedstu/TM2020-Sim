"""Compiled ephemeral discovery recorder; separate from the offline guard API."""
import ctypes as C
from pathlib import Path
import weakref
from owned_native_guard import _Api,_Fault
from unicorn.unicorn_py3.unicorn import uclib


def release(dll,engine_ref,handle):
    if engine_ref() is None:dll.tmcapture_abandon(handle)
    else:dll.tmcapture_destroy(handle)


class NativeCapture:
    def __init__(self,mu,path):
        self.mu=mu;self.path=Path(path).resolve(strict=True);self.dll=C.CDLL(str(self.path))
        signatures={
            "create":([C.c_void_p,C.POINTER(_Api)],C.c_void_p),
            "code":([C.c_void_p,C.c_uint64,C.c_void_p],C.c_int),
            "exclude":([C.c_void_p,C.c_uint64,C.c_uint64],C.c_int),
            "platform":([C.c_void_p,C.c_uint64],C.c_int),
            "start":([C.c_void_p],C.c_int),
            "pages":([C.c_void_p,C.POINTER(C.c_uint64),C.c_uint64],C.c_uint64),
            "mask":([C.c_void_p,C.c_uint64,C.c_void_p,C.c_int],C.c_int),
            "fault":([C.c_void_p,C.POINTER(_Fault)],C.c_int),
            "counts":([C.c_void_p,C.POINTER(C.c_uint64)],None),
            "destroy":([C.c_void_p],None),"abandon":([C.c_void_p],None)}
        for name,(args,result) in signatures.items():
            fn=getattr(self.dll,"tmcapture_"+name);fn.argtypes,fn.restype=args,result;setattr(self,name,fn)
        api=_Api(*(C.cast(getattr(uclib,"uc_"+name),C.c_void_p).value for name,_ in _Api._fields_))
        self.handle=self.create(mu._uch,C.byref(api))
        if not self.handle:raise RuntimeError("Cannot create ephemeral capture recorder")
        self._finalizer=weakref.finalize(self,release,self.dll,weakref.ref(mu),self.handle)

    def add_code(self,page,expected):
        if len(expected)!=4096 or not self.code(self.handle,page,C.c_char_p(bytes(expected))):
            raise ValueError("Invalid pinned instruction page")

    def snapshot(self):
        n=self.pages(self.handle,None,0);pages=(C.c_uint64*n)()
        if self.pages(self.handle,pages,n)!=n:raise RuntimeError("Capture changed outside synchronous execution")
        result={}
        for page in pages:
            masks=[]
            for plane in range(3):
                buf=(C.c_ubyte*4096)()
                if not self.mask(self.handle,page,buf,plane):raise RuntimeError("Missing capture mask")
                masks.append(bytes(buf))
            result[page]=masks
        return result

    def fault_info(self):
        result=_Fault()
        if self.fault(self.handle,C.byref(result)):return {name:getattr(result,name) for name,_ in result._fields_}

    def counters(self):
        out=(C.c_uint64*2)();self.counts(self.handle,out)
        return dict(instructions=out[0],memoryAccesses=out[1])

    def close(self):
        if getattr(self,"handle",None):self._finalizer();self.handle=None
