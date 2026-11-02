#!/usr/bin/env python3
"""Disassembler-verified read-only PE class/string cross references.

Proof level: a RIP-relative instruction really targets the static string RVA
in Trackmania 2026.2.2.1751. This does NOT identify live vehicle pointers,
object layouts, physics function semantics or injection locations.
Uses pre-installed pefile and capstone. No process memory access.
"""
import hashlib
import json
from pathlib import Path
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86_const import X86_OP_MEM, X86_REG_RIP

ROOT=Path(__file__).resolve().parents[1]
GAME=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
INPUT=ROOT/"local/recon/trackmania-2026.2.2.1751-vehicle-strings.json"
OUT=ROOT/"local/recon/disassembled-string-xrefs.json"

def decode_rva(x):
    return int(x,16)

def main():
    data=GAME.read_bytes()
    pe=pefile.PE(data=data,fast_load=True)
    input=json.loads(INPUT.read_text(encoding="utf-8-sig"))
    cs=Cs(CS_ARCH_X86,CS_MODE_64)
    cs.detail=True
    verified=[]
    disproven=0
    visited=set()
    executable=[s for s in pe.sections if s.Characteristics & 0x20000000]
    base=pe.OPTIONAL_HEADER.ImageBase
    for group in input["patterns"]:
        for occ in group["occurrences"]:
            target_rva=decode_rva(occ["rva"])
            if target_rva==0:continue
            for candidate in occ["candidateRipReferences"]:
                rva=decode_rva(candidate)
                if not any(s.VirtualAddress<=rva<s.VirtualAddress+s.SizeOfRawData for s in executable):
                    disproven+=1
                    continue
                try:
                    off=pe.get_offset_from_rva(rva)
                    instruction=next(cs.disasm(data[off:off+16],base+rva,count=1),None)
                    if instruction is None:continue
                    rip_targets=[]
                    for op in instruction.operands:
                        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                            rip_targets.append(instruction.address+instruction.size+op.mem.disp-base)
                    if target_rva not in rip_targets:
                        disproven+=1
                        continue
                    key=(group["term"],target_rva,rva)
                    if key in visited:continue
                    visited.add(key)
                    verified.append({
                        "string":group["term"],
                        "stringRVA":hex(target_rva),
                        "instructionRVA":hex(rva),
                        "instructionBytes":instruction.bytes.hex(),
                        "instruction":instruction.mnemonic+" "+instruction.op_str,
                        "confirmedInstructionBoundary":True,
                        "vehicleMemoryPointerProved":False
                    })
                except (ValueError,TypeError,pefile.PEFormatError):
                    disproven+=1
    result={
        "schema":"tm2020_disasm_verified_rip_strings_v1",
        "gameVersion":"2026.2.2.1751",
        "exeSHA256":hashlib.sha256(data).hexdigest(),
        "source":"static PE; capstone validates RIP-relative instruction target",
        "noGameProcessAccess":True,
        "codeSemanticMeaningVerified":False,
        "liveVehiclePointersKnown":False,
        "actualStructOffsetsKnown":False,
        "xrefTotal":len(verified),
        "falseCandidateXrefs":disproven,
        "xrefs":verified
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("PASS PE_ASSEMBLY_XREF verified",len(verified),"false",disproven,"exe hash",result["exeSHA256"][:12])
    for k in ("CSceneVehicleVis","CPlugVehicle","InputSteer","GroundContact","ReactorBoost"):
        matches=[x for x in verified if x["string"]==k]
        print(k,":",len(matches),"verified references")
        for x in matches[:4]:print(" ",x["instructionRVA"],x["instruction"])
    print("RESULT",OUT)
if __name__=="__main__":sys.exit(main())
