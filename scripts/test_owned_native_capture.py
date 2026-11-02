"""Check ephemeral discovery masks and pinned-code refusal on owned programs."""
import argparse
import gc
import json
from pathlib import Path
import struct
import sys
import weakref
from pinned_build import ROOT
sys.path.insert(0,str(ROOT/"tools/physics-python"))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX
from owned_native_capture import NativeCapture


def run(args):
    results=[]
    program=b"\x48\x8b\x01\x48\x89\x02"
    for name,cross,changed,unknown,excluded in (
        ("read_and_write_masks",False,False,False,False),
        ("cross_page_masks",True,False,False,False),
        ("changed_instruction_denied",False,True,False,False),
        ("unknown_code_denied",False,False,True,False),
        ("explicit_scratch_excluded",False,False,False,True)):
        mu=Uc(UC_ARCH_X86,UC_MODE_64);mu.mem_map(0x100000,8192);mu.mem_map(0x200000,8192);mu.mem_map(0x300000,4096)
        pc=0x100ffd if cross else 0x100000;source=0x200ffc if cross else 0x200000
        mu.mem_write(pc,program);mu.mem_write(source,struct.pack("<Q",1234567))
        mu.reg_write(UC_X86_REG_RCX,source);mu.reg_write(UC_X86_REG_RDX,0x300000)
        rec=NativeCapture(mu,args.dll)
        try:
            if not unknown:
                for page in (0x100000,0x101000):rec.add_code(page,bytes(mu.mem_read(page,4096)))
            if excluded:assert rec.exclude(rec.handle,0x300000,4096)
            assert rec.start(rec.handle)
            if changed:mu.mem_write(pc+1,b"\x89")
            mu.emu_start(pc,pc+len(program),count=100)
            fault=rec.fault_info();snapshot=rec.snapshot()
            if changed or unknown:assert fault and fault["kind"]==2,(name,fault)
            else:
                assert fault is None
                for at in range(source,source+8):assert snapshot[at&~4095][0][at&4095]==1
                for at in range(pc,pc+len(program)):assert snapshot[at&~4095][1][at&4095]==1
                if excluded:assert 0x300000 not in snapshot
                else:
                    assert snapshot[0x300000][0][:8]==b"\1"*8
                    assert snapshot[0x300000][2][:8]==b"\1"*8
                assert not any(snapshot[source&~4095][2])
                assert bytes(mu.mem_read(0x300000,8))==struct.pack("<Q",1234567)
            results.append(dict(name=name,passed=True,fault=fault))
        finally:rec.close()
    def cyclic():
        from unicorn import UC_HOOK_CODE
        mu=Uc(UC_ARCH_X86,UC_MODE_64);rec=NativeCapture(mu,args.dll)
        assert rec.start(rec.handle)
        mu.hook_add(UC_HOOK_CODE,lambda *a:rec.counters())
        return weakref.ref(mu),weakref.ref(rec)
    refs=cyclic();gc.collect();assert all(r() is None for r in refs)
    results.append(dict(name="unreachable_capture_cycle_released",passed=True))
    report=dict(schema="tm2020_native_ephemeral_capture_owned_v1",cases=results,
        offlineGuardApiChanged=False,gameProcessAccessed=False,completeSimulatorQualified=False)
    if args.report:args.report.write_text(json.dumps(report,indent=2)+"\n")
    print("PASS NATIVE_EPHEMERAL_CAPTURE cases="+str(len(results))+" separate_from_offline_guard=true")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--dll",type=Path,required=True)
    p.add_argument("--report",type=Path);run(p.parse_args())
