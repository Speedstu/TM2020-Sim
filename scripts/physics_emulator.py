"""Bounded original-instruction oracle support, entirely in synthetic memory."""
import hashlib
from pathlib import Path
import struct
import sys
import pefile
from reverse_physics import ROOT,SHA
sys.path.insert(0,str(ROOT/'tools/physics-python'))
import unicorn
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_PROT_READ,UC_PROT_EXEC
from unicorn.x86_const import UC_X86_REG_RSP,UC_X86_REG_RIP,UC_X86_REG_MXCSR


class PhysicsEmulator:
    def __init__(self,executable,ranges):
        raw=Path(executable).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Unknown game build')
        if unicorn.__version__!='2.1.4':raise ValueError('Unqualified emulator version')
        pe=pefile.PE(data=raw,fast_load=True);self.base=pe.OPTIONAL_HEADER.ImageBase
        self.mu=Uc(UC_ARCH_X86,UC_MODE_64);size=(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095
        self.mu.mem_map(self.base,size)
        for s in pe.sections:self.mu.mem_write(self.base+s.VirtualAddress,s.get_data())
        self.mu.mem_protect(self.base,size,UC_PROT_READ)
        for start,end in ranges:
            page=start&~4095;self.mu.mem_protect(self.base+page,((end+4095)&~4095)-page,UC_PROT_READ|UC_PROT_EXEC)
        self.memory=0x200000000;self.mu.mem_map(self.memory,0x20000)
        self.stack=0x400000000;self.mu.mem_map(self.stack,0x10000);self.rsp=self.stack+0x10000-0x108
        self.sentinel=0x500000000;self.mu.mem_map(self.sentinel,0x1000)

    def reset_stack(self):
        self.mu.mem_write(self.rsp,struct.pack('<Q',self.sentinel))
        self.mu.reg_write(UC_X86_REG_RSP,self.rsp);self.mu.reg_write(UC_X86_REG_MXCSR,0x1f80)

    def run(self,entry,stop=None,budget=1000):
        end=self.sentinel if stop is None else self.base+stop
        self.mu.emu_start(self.base+entry,end,count=budget)
        return self.mu.reg_read(UC_X86_REG_RIP)
