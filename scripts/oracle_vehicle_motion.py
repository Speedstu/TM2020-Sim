"""Original SSE prefix differential for all four vehicle substep motion lengths.

Executes unchanged 0x15019f7..0x1501b52 and stops before model lookup.
Finite vector inputs keep negative-square-root error branches unreachable.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import pefile
from force_worker_fixture import require
from pinned_build import ROOT,SHA
sys.path.insert(0,str(ROOT/"tools/physics-python"))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_CODE
from unicorn.x86_const import *
from oracle_vehicle_substeps import bits,f32,scalar


def main(args):
    require(hashlib.sha256(args.exe.read_bytes()).hexdigest()==SHA,"Unknown original build")
    pe=pefile.PE(str(args.exe),fast_load=True)
    base=0x140000000;data=0x200000000;entry=base+0x15019f7;end=base+0x1501b52
    mu=Uc(UC_ARCH_X86,UC_MODE_64)
    mu.mem_map(base+0x1501000,4096)
    mu.mem_write(base+0x1501000,pe.get_data(0x1501000,4096))
    mu.mem_protect(base+0x1501000,4096,UC_PROT_READ|UC_PROT_EXEC)
    mu.mem_map(data,0x8000)
    def guard(uc,address,size,user):
        require(entry<=address<end,"Original motion slice escaped into a callee/error path")
    mu.hook_add(UC_HOOK_CODE,guard)
    rows=[];rng=random.Random(0x202610240031)
    edge=[-10000.,-1.,-0.,0.,scalar(1),-scalar(1),scalar(0x00800000),1.,10000.]
    for n in range(20000):
        v=[f32(rng.uniform(-10000,10000)) for _ in range(12)]
        if n%3==0:v=[edge[(n+i*7)%len(edge)] for i in range(12)]
        scale=f32(rng.choice((.0001,1.,1.25,2.,100.)))
        interval=scalar(0x3c23d70b) if n%3 else f32(rng.choice((.000001,.001,.01,.1,1.)))
        rows.append(v+[scale,interval])
    args.output.mkdir(parents=True,exist_ok=True)
    input_path=args.output/"motion-input.bin";output_path=args.output/"motion-port.bin"
    input_path.write_bytes(b"".join(struct.pack("<14f",*row) for row in rows))
    result=subprocess.run([str(args.runner.resolve()),str(input_path.resolve()),str(output_path.resolve())],
                          capture_output=True,text=True,timeout=60)
    require(result.returncode==0,"Portable motion runner failed: "+result.stderr)
    actual=output_path.read_bytes();require(len(actual)==len(rows)*4,"Motion output extent differs")
    for n,row in enumerate(rows):
        state=data;vehicle=data+0x1000;stack=data+0x4000
        mu.mem_write(state+0x40,struct.pack("<6f",*row[:6]))
        mu.mem_write(vehicle+0x1348,struct.pack("<6f",*row[6:12]))
        for register,value in ((UC_X86_REG_RAX,state),(UC_X86_REG_RBP,vehicle),(UC_X86_REG_RSP,stack),
            (UC_X86_REG_XMM7,bits(row[12]*row[13])),(UC_X86_REG_MXCSR,0x1f80)):
            mu.reg_write(register,value)
        mu.emu_start(entry,end,count=200)
        require(mu.reg_read(UC_X86_REG_RIP)==end,"Original motion prefix did not complete")
        expected=mu.reg_read(UC_X86_REG_XMM6)&0xffffffff
        require(struct.unpack_from("<I",actual,n*4)[0]==expected,
                "Four-vector motion differential failed at case "+str(n))
    args.report.write_text(json.dumps(dict(schema="tm2020_vehicle_substep_motion_oracle_v1",
        executableSha256=SHA,cases=len(rows),bitExact=True,originalEntryRva="0x15019f7",
        portableRunnerSha256=hashlib.sha256(args.runner.read_bytes()).hexdigest(),
        portableSourceSha256=hashlib.sha256((ROOT/"native/src/recovered_step.cpp").read_bytes()).hexdigest(),
        portableHeaderSha256=hashlib.sha256((ROOT/"native/include/tm2020/recovered_step.hpp").read_bytes()).hexdigest(),
        originalEndBeforeModelLookupRva="0x1501b52",motionVectors=4,vectorComponentLimit=10000,
        includesSignedZeroAndSubnormals=True,originalCodeModified=False,gameProcessAccessed=False,
        completeFunctionQualified=False,completeSceneSchedulerQualified=False,
        completeSimulatorQualified=False),indent=2)+"\n")
    print("PASS ORIGINAL VEHICLE MOTION PREFIX cases=20000 vectors=4 bit_exact=true")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe",type=Path,required=True)
    p.add_argument("--runner",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    main(p.parse_args())
