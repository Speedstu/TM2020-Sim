"""Original-instruction differential for the bounded vehicle substep selector.

The original selector slice is unchanged. The residual uses its unchanged
SUBSS instruction in an explicitly owned repeat/return scaffold. This is not
a complete function, collision scheduler, or original scene loop oracle.
"""
import argparse
import hashlib
import json
import random
import struct
import subprocess
import sys
from pathlib import Path
import pefile
from force_worker_fixture import require
from pinned_build import ROOT,SHA

sys.path.insert(0,str(ROOT/"tools/physics-python"))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_CODE
from unicorn.x86_const import *

def bits(x):return struct.unpack("<I",struct.pack("<f",x))[0]
def f32(x):return struct.unpack("<f",struct.pack("<f",x))[0]
def scalar(word):return struct.unpack("<f",struct.pack("<I",word))[0]


def main(args):
    require(hashlib.sha256(args.exe.read_bytes()).hexdigest()==SHA,"Unknown original build")
    pe=pefile.PE(str(args.exe),fast_load=True)
    require(pe.get_data(0x1d1fa9c,4)==struct.pack("<f",1000)
            and pe.get_data(0x1d1fe58,8)==struct.pack("<d",-1e9),"Original selector constants differ")
    base=0x140000000;data=0x200000000
    entry=base+0x1501b57;multi_end=base+0x1501bd7;single_end=base+0x1501ce4
    mu=Uc(UC_ARCH_X86,UC_MODE_64)
    for rva in (0x1501000,0x1d1e000,0x1d1f000):
        raw=pe.get_data(rva,4096);require(len(raw)==4096,"Truncated original page")
        mu.mem_map(base+rva,4096);mu.mem_write(base+rva,raw)
        mu.mem_protect(base+rva,4096,UC_PROT_READ|(UC_PROT_EXEC if rva==0x1501000 else 0))
    mu.mem_map(data,8192)
    def stop(uc,address,size,user):
        if address==single_end:uc.emu_stop()
        elif not entry<=address<multi_end:
            raise ValueError("Execution escaped the original selector slice")
    mu.hook_add(UC_HOOK_CODE,stop)
    # Isolated arithmetic recurrence: original SUBSS bytes, owned DEC/JNZ/RET.
    subtract=pe.get_data(0x1501bf2,5)
    require(subtract==bytes.fromhex("f3410f5cfb"),"Original residual subtraction changed")
    residual=Uc(UC_ARCH_X86,UC_MODE_64)
    loop=0x300000000;stack=loop+4096;sentinel=loop+8192
    residual.mem_map(loop,12288)
    residual.mem_write(loop,subtract+bytes.fromhex("ffc975f7c3"))
    residual.mem_protect(loop,4096,UC_PROT_READ|UC_PROT_EXEC)
    residual.mem_write(stack,struct.pack("<Q",sentinel))
    rng=random.Random(0x202610240030)
    rows=[]
    for n in range(20000):
        limit=rng.choice((.01,1.,1000.))
        ratio=rng.choice((0.,.99999994,1.,1.00000012,998.99994,999.,999.00006,1000.,999999.)) if n%3==0 else rng.uniform(0,2000)
        motion=f32(ratio*limit)
        scale=f32(rng.choice((.0001,1.,1.25,2.,100.)) if n%2 else rng.uniform(.1,4))
        dt=scalar(0x3c23d70b) if n%3 else f32(rng.choice((.000001,.001,.01,.1,1.)))
        rows.append((motion,f32(limit),scale,dt))
    observed={}
    if args.observed_report is not None:
        capture=json.loads(args.observed_report.read_text())["fixtures"][0]
        require(capture["completed"] is True and capture["allTypedPhysicalFramesBitExact"] is True
                and capture["allDataPagesBitExact"] is True,"Observed selector source replay is incomplete")
        inputs=capture["vehicleSubstepSelectionInputsByFrame"]
        require(len(inputs)==capture["tickCount"],"Observed selector does not cover every reference tick")
        for frame,values in inputs.items():
            require(len(values)==1,"Observed selector oracle requires one retained vehicle per frame")
            row=values[0]
            observed[len(rows)]=dict(frame=int(frame),total=row["totalScaledIntervalBits"],
                intervals=capture["vehiclePoseSubstepIntervalCountsByFrame"][frame])
            rows.append(tuple(scalar(row[k]) for k in
                              ("scaledMotionBits","motionLimitBits","timeScaleBits","intervalBits")))
    args.output.mkdir(parents=True,exist_ok=True)
    input_path=args.output/"selector-input.bin";output_path=args.output/"selector-port.bin"
    input_path.write_bytes(b"".join(struct.pack("<4f",*row) for row in rows))
    result=subprocess.run([str(args.runner.resolve()),str(input_path.resolve()),str(output_path.resolve())],
                          capture_output=True,text=True,timeout=60)
    require(result.returncode==0,"Portable selector runner failed: "+result.stderr)
    actual=output_path.read_bytes();require(len(actual)==len(rows)*28,"Portable selector output extent differs")
    counts={"single":0,"multiple":0,"clamped":0};subtractions=0
    for n,(motion,limit,scale,dt) in enumerate(rows):
        mu.mem_write(data+0x54,struct.pack("<f",limit))
        mu.mem_write(data+4096+8,struct.pack("<f",dt))
        total=bits(scale*dt)
        for register,value in ((UC_X86_REG_RAX,data),(UC_X86_REG_R15,data+4096),
            (UC_X86_REG_XMM6,bits(motion)),(UC_X86_REG_XMM7,total),
            (UC_X86_REG_XMM11,bits(scale)),(UC_X86_REG_MXCSR,0x1f80)):
            mu.reg_write(register,value)
        mu.emu_start(entry,multi_end,count=100)
        pc=mu.reg_read(UC_X86_REG_RIP)
        if pc==single_end:
            count=1;unscaled=scaled=delta=0;last=total;counts["single"]+=1
        else:
            require(pc==multi_end,"Original selector did not finish within its bounded slice")
            count=(mu.reg_read(UC_X86_REG_RAX)&0xffffffff)+1
            unscaled=mu.reg_read(UC_X86_REG_XMM2)&0xffffffff
            scaled=mu.reg_read(UC_X86_REG_XMM11)&0xffffffff
            delta=mu.reg_read(UC_X86_REG_RSI)
            if delta&(1<<63):delta-=1<<64
            require(2<=count<=1000,"Original selector count outside qualified domain")
            for register,value in ((UC_X86_REG_RCX,count-1),(UC_X86_REG_RSP,stack),
                (UC_X86_REG_XMM7,total),(UC_X86_REG_XMM11,scaled),(UC_X86_REG_MXCSR,0x1f80)):
                residual.reg_write(register,value)
            residual.emu_start(loop,sentinel,count=5000)
            require(residual.reg_read(UC_X86_REG_RIP)==sentinel,"Residual arithmetic scaffold did not return")
            last=residual.reg_read(UC_X86_REG_XMM7)&0xffffffff
            subtractions+=count-1;counts["multiple"]+=1
            if f32(motion/limit)>=1000:counts["clamped"]+=1
        expected=struct.pack("<5Iq",count,unscaled,scaled,total,last,delta)
        require(actual[n*28:(n+1)*28]==expected,f"Vehicle substep selector mismatch at case {n}: {rows[n]}")
        if n in observed:
            reference=observed[n]
            require(total==reference["total"],"Total duration differs from original scene selector input")
            predicted={}
            if count>1:predicted[f"0x{scaled:08x}"]=count-1
            key=f"0x{last:08x}";predicted[key]=predicted.get(key,0)+1
            require(predicted==reference["intervals"],
                    "Portable selector differs from actually executed scene substeps at frame "+str(reference["frame"]))
    args.report.write_text(json.dumps(dict(schema="tm2020_vehicle_substep_selector_oracle_v1",
        executableSha256=SHA,cases=len(rows),generatedCases=20000,bitExact=True,branches=counts,
        portableRunnerSha256=hashlib.sha256(args.runner.read_bytes()).hexdigest(),
        portableSourceSha256=hashlib.sha256((ROOT/"native/src/recovered_step.cpp").read_bytes()).hexdigest(),
        portableHeaderSha256=hashlib.sha256((ROOT/"native/include/tm2020/recovered_step.hpp").read_bytes()).hexdigest(),
        observedSelectorFramesCompared=len(observed),observedSceneIntervalsCompared=bool(observed),
        observedReplayReportSha256=hashlib.sha256(args.observed_report.read_bytes()).hexdigest() if observed else None,
        originalSelectorEntryRva="0x1501b57",originalSelectorEndRva="0x1501bd7",
        singleStepExitRva="0x1501ce4",originalResidualInstructionRva="0x1501bf2",
        originalResidualSubtractionsCompared=subtractions,residualLoopUsesOwnedControlScaffold=True,
        originalCodeModified=False,gameProcessAccessed=False,completeFunctionQualified=False,
        completeSceneSchedulerQualified=False,completeSimulatorQualified=False),indent=2)+"\n")
    print("PASS ORIGINAL VEHICLE SUBSTEP SLICE cases="+str(len(rows))+" observed_frames="+str(len(observed))+" bit_exact=true complete_scheduler=false")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe",type=Path,required=True)
    p.add_argument("--runner",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--observed-report",type=Path)
    main(p.parse_args())
