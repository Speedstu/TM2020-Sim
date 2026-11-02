"""Compare the owned SDK active-list operation with an original instruction slice.

This starts after the original synchronization call and ends before its unlock.
It does not qualify either synchronization, the full function, or wake processing.
"""
import argparse
import json
from pathlib import Path
import random
import struct
import subprocess
from physics_emulator import PhysicsEmulator
from pinned_build import SHA
from unicorn.x86_const import UC_X86_REG_R14, UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RBP


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--oracle',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    em=PhysicsEmulator(args.executable,[(0x7fc09a,0x7fc0bd),(0x117f70,0x117f74)])
    mu=em.mu;state=em.memory;context=em.memory+0x100;active=em.memory+0x1000
    rng=random.Random(2026102903);out=bytearray(b'TMACT001'+struct.pack('<I',20000));inserted=0
    for case in range(20000):
        rest=rng.getrandbits(32);index=0xffff if case%3 else rng.randrange(0xffff)
        packed=index|(rng.randrange(256)<<16)|(rng.randrange(256)<<24)
        slot=rng.getrandbits(32);count=rng.randrange(16);items=[rng.getrandbits(32) for _ in range(16)]
        initial=struct.pack('<II',rest,packed);mu.mem_write(state,initial)
        mu.mem_write(context,struct.pack('<QII',active,count,16));mu.mem_write(active,struct.pack('<16I',*items))
        em.reset_stack()
        for reg,value in ((UC_X86_REG_R14,0xffff),(UC_X86_REG_RDI,state),(UC_X86_REG_RSI,context),(UC_X86_REG_RBP,slot)):
            mu.reg_write(reg,value)
        if em.run(0x7fc09a,0x7fc0bd,budget=50)!=em.base+0x7fc0bd:raise RuntimeError('Original instruction slice escaped')
        after=bytes(mu.mem_read(state,8));new_rest,new_packed=struct.unpack('<II',after)
        if new_rest!=rest:raise AssertionError('Original changed unrelated index bytes')
        new_count=struct.unpack('<I',bytes(mu.mem_read(context+8,4)))[0]
        new_items=struct.unpack('<16I',bytes(mu.mem_read(active,64)))
        inserted+=int(index==0xffff)
        out.extend(struct.pack('<20I',rest,packed,slot,count,*items))
        out.extend(struct.pack('<18I',new_packed,new_count,*new_items))
    cases=args.output/'active-slot.cases';cases.write_bytes(out)
    result=subprocess.run([str(args.oracle.resolve()),str(cases.resolve())],text=True,capture_output=True,check=True)
    (args.output/'report.json').write_text(json.dumps(dict(schema='tm2020_active_slot_original_slice_v1',
        exeSha256=SHA,cases=20000,insertions=inserted,originalRvaStart='0x7fc09a',originalRvaStop='0x7fc0bd',
        cppDefinedOutputsExact=True,originalInstructionsExecuted=True,synchronizationQualified=False,
        entireActivationHelperQualified=False,wakeConsumerQualified=False,sourceGameProcessAccessed=False,
        completeExactSimulatorQualified=False,oracleOutput=result.stdout.strip()),indent=2)+'\n')
    print(result.stdout.strip())


if __name__=='__main__':main()
