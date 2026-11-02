"""Adversarial private microprograms for the compiled Unicorn coverage guard."""
import argparse
import json
from pathlib import Path
import sys
import hashlib
import struct
import gc
import weakref

from pinned_build import ROOT
sys.path.insert(0,str(ROOT/"tools/physics-python"))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RAX,UC_X86_REG_RCX,UC_X86_REG_RDX
from owned_native_guard import NativeGuard


def run(args):
    results=[]
    def case(name,program,code_at=0x100000,read_at=0x200000,hole=None,
             mutate=None,unregistered=False,scratch=False):
        mu=Uc(UC_ARCH_X86,UC_MODE_64)
        code_page=code_at&~4095
        mu.mem_map(code_page,8192)
        mu.mem_write(code_at,program)
        mu.mem_map(0x200000,8192)
        mu.mem_map(0x300000,4096)
        mu.mem_write(read_at,struct.pack("<Q",0x8877665544332211))
        mu.reg_write(UC_X86_REG_RCX,read_at)
        mu.reg_write(UC_X86_REG_RDX,0x300000)
        guard=NativeGuard(mu,args.dll)
        try:
            for page in (code_page,code_page+4096):
                if not unregistered:guard.add_page(page,bytes(mu.mem_read(page,4096)),True)
            for page in (0x200000,0x201000,0x300000):
                mask=bytearray(b"\1"*4096)
                if hole is not None and page==hole&~4095:mask[hole&4095]=0
                if not scratch:guard.add_page(page,mask)
            assert guard.range(guard.handle,0x300000,4096,0)
            if scratch:
                assert guard.range(guard.handle,0x200000,8192,1)
                assert guard.range(guard.handle,0x300000,4096,1)
            assert guard.start(guard.handle)
            mu.mem_protect(code_page,8192,UC_PROT_READ|UC_PROT_EXEC)
            if mutate is not None:
                at,value=mutate;mu.mem_write(at,bytes([value]))
            mu.emu_start(code_at,code_at+len(program),count=100)
            fault=guard.fault_info()
            if hole is not None:
                assert fault and fault["kind"]==1 and fault["address"]==hole,(name,fault)
            elif mutate is not None or unregistered:
                assert fault and fault["kind"]==2,(name,fault)
            else:
                assert fault is None,(name,fault)
                if program==b"\x48\x8b\x01\x48\x89\x02":
                    assert bytes(mu.mem_read(0x300000,8))==struct.pack("<Q",0x8877665544332211)
                else:assert mu.reg_read(UC_X86_REG_RAX)==0x8877665544332211
            if fault is None:
                assert guard.counters()["instructions"]>0
            if not fault or hole==0x300007:
                assert 0x300000 in guard.touched_pages() or program!=b"\x48\x8b\x01\x48\x89\x02"
            guard.clear(guard.handle)
            assert guard.fault_info() is None and not guard.touched_pages()
            results.append(dict(name=name,passed=True,fault=fault))
        finally:guard.close()
    def cyclic_engine():
        mu=Uc(UC_ARCH_X86,UC_MODE_64);guard=NativeGuard(mu,args.dll)
        assert guard.start(guard.handle)
        # Reproduce the interpreter callback -> guard -> engine ownership cycle.
        mu.hook_add(UC_HOOK_CODE,lambda uc,address,size,user:guard.counters())
        return weakref.ref(mu),weakref.ref(guard)
    for _ in range(8):
        refs=cyclic_engine();gc.collect()
        assert all(ref() is None for ref in refs),"Native guard roots an unreachable engine cycle"
    results.append(dict(name="unreachable_engine_callback_cycles_released",passed=True,cycles=8))
    copy=b"\x48\x8b\x01\x48\x89\x02"
    case("known_read_write",copy)
    case("last_read_byte_unknown",copy,hole=0x200007)
    case("last_write_byte_unknown",copy,hole=0x300007)
    case("cross_page_read_valid",copy,read_at=0x200ffc)
    case("cross_page_read_unknown_second_page",copy,read_at=0x200ffc,hole=0x201003)
    case("changed_instruction",copy,mutate=(0x100001,0x89))
    case("unknown_executable_page",copy,unregistered=True)
    immediate=b"\x48\xb8"+struct.pack("<Q",0x8877665544332211)
    case("cross_page_instruction_valid",immediate,code_at=0x100ffc)
    case("cross_page_instruction_changed",immediate,code_at=0x100ffc,mutate=(0x101001,0))
    case("explicit_scratch_and_dirty_pages",copy,scratch=True)
    for name,program,expected_gap in (
        ("read_before_write_denied",b"\x48\x8b\x11",0x200000),
        ("full_write_then_read",b"\x48\x89\x01\x48\x8b\x11",None),
        ("partial_write_leaves_upper_bytes_unknown",b"\x89\x01\x48\x8b\x11",0x200004)):
        mu=Uc(UC_ARCH_X86,UC_MODE_64);mu.mem_map(0x100000,4096);mu.mem_map(0x200000,4096)
        mu.mem_write(0x100000,program);mu.reg_write(UC_X86_REG_RCX,0x200000)
        mu.reg_write(UC_X86_REG_RAX,0x8877665544332211)
        guard=NativeGuard(mu,args.dll)
        try:
            guard.add_page(0x100000,bytes(mu.mem_read(0x100000,4096)),True)
            guard.add_page(0x200000,bytes(4096))
            guard.write_initialization(guard.handle,1)
            assert guard.start(guard.handle)
            mu.emu_start(0x100000,0x100000+len(program),count=10)
            fault=guard.fault_info()
            if expected_gap is None:
                assert fault is None and mu.reg_read(UC_X86_REG_RDX)==0x8877665544332211
                saved=guard.save_initialized()
                assert saved[0x200000][:8]==b"\1"*8 and not any(saved[0x200000][8:])
                guard.clear(guard.handle)
                mu.emu_start(0x100003,0x100006,count=10)
                assert guard.fault_info()["address"]==0x200000  # Clearing forgets initialized bytes.
                guard.clear(guard.handle);guard.restore_initialized(saved)
                mu.emu_start(0x100003,0x100006,count=10)
                assert guard.fault_info() is None and mu.reg_read(UC_X86_REG_RDX)==0x8877665544332211
            else:assert fault and fault["kind"]==1 and fault["address"]==expected_gap
            results.append(dict(name=name,passed=True,writeInitializationTracked=True))
        finally:guard.close()
    report=dict(schema="tm2020_owned_native_guard_adversarial_v1",cases=results,
        casesPassed=len(results),dllSha256=hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        gameProcessAccessed=False,originalGameInstructionsUsed=False,
        guardOnlyTest=True,fullSimulatorQualified=False)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+"\n")
    print("PASS NATIVE_UNICORN_GUARD adversarial_cases="+str(len(results)))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll",type=Path,required=True)
    parser.add_argument("--report",type=Path)
    run(parser.parse_args())
