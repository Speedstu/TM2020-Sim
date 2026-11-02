"""Identify original instructions/callers at strict sparse-input rejections.

This diagnostic reads only owned emulator state after rejection. It never
resumes the failed step or returns a physical observation from that step.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from force_worker_fixture import require
from owned_step_machine import open_owned_machine,UncapturedStepError
from pe_unwind import PeCode
from unicorn.x86_const import UC_X86_REG_RIP,UC_X86_REG_RSP,UC_X86_REG_RCX,UC_X86_REG_RDX


def main(args):
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32)
    code=PeCode(args.exe)
    base=machine.metadata["modules"][0]["base"]
    config=machine.metadata["configuration"]
    rows=[]
    for controls in ([0,0,0],[1,0.5,0]):
        machine.reset()
        try:
            machine.step(controls)
        except UncapturedStepError as error:
            require(machine.failed and machine.frame==0,"Rejected execution advanced time")
            pc=machine.mu.reg_read(UC_X86_REG_RIP)-base
            instruction=next((i for i in code.instructions(pc) if i.address==pc),None)
            require(instruction is not None,"Rejected instruction has no complete unwind body")
            rsp=machine.mu.reg_read(UC_X86_REG_RSP)
            size=min(1024,0x400020000-rsp)
            require(size>0,"Rejected execution stack is outside owned stack")
            callers=[]
            for offset,value in enumerate(struct.unpack("<"+"Q"*(size//8),machine.mu.mem_read(rsp,size//8*8))):
                rva=value-base
                if not 0<=rva<machine.metadata["modules"][0]["imageSize"]:continue
                call=next((i for i in code.instructions(rva-1)
                           if i.mnemonic=="call" and i.address+i.size==rva),None)
                if call is not None:
                    callers.append(dict(stackOffset=offset*8,callRva=hex(call.address),
                                        assembly=call.mnemonic+" "+call.op_str))
            args_offsets={name:(value if 0<=value<0x5000 else None)
                          for name,register in (("rcx",UC_X86_REG_RCX),("rdx",UC_X86_REG_RDX))
                          for value in [machine.mu.reg_read(register)-config]}
            gap=machine.report["uncapturedAccesses"][-1]
            rows.append(dict(controls=controls,rejected=True,error=str(error),instructionRva=hex(pc),
                rootRva=hex(code.index.root(pc)),assembly=instruction.mnemonic+" "+instruction.op_str,
                configurationRelativeRegisters=args_offsets,validatedStackCallSites=callers,
                uncapturedConfigurationOffset=hex(gap["address"]-config),
                stackCallSitesAreCandidatesNotAnUnwoundCallStack=True,
                physicalObservationReturned=False))
        else:
            rows.append(dict(controls=controls,rejected=False))
    args.report.write_text(json.dumps(dict(schema="tm2020_owned_input_gap_diagnostics_v1",
        fixtureSha256=machine.fixture.sha256,executableSha256=hashlib.sha256(args.exe.read_bytes()).hexdigest(),
        probes=rows,gameProcessAccessed=False,failedStepsResumed=False,
        completeSimulatorQualified=False),indent=2)+"\n")
    print("SAVED INPUT GAP INSTRUCTION/CALLER EVIDENCE",len(rows))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--exe",type=Path,required=True)
    p.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    p.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    p.add_argument("--report",type=Path,required=True)
    main(p.parse_args())
