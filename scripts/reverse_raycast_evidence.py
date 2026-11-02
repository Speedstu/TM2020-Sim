"""Pin triangle raycast ABI, both-sided sign-bit gate and helper bodies."""
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_IMM

from force_worker_fixture import require
from pe_unwind import PeCode
from pinned_build import ROOT,SHA


def main():
    exe=Path(r"D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe")
    require(hashlib.sha256(exe.read_bytes()).hexdigest()==SHA,"Unknown geometry game image")
    code=PeCode(exe);bounds={0x1af350:0x1af706,0x18ba80:0x18bb55,0x18ca50:0x18ca8f,
        0x1b2420:0x1b2947,0x1a0290:0x1a052d,0x19a580:0x19a597}
    records=[]
    for start,end in bounds.items():
        if start in (0x18ca50,0x19a580):
            require(code.index.root(start) is None,"Reviewed division leaf acquired unwind metadata")
            instructions=list(code.cs.disasm(code.pe.get_data(start,end-start),start))
        else:
            expected=([(0x1b2420,0x1b249a),(0x1b249a,0x1b2746),(0x1b2746,0x1b274f),
                (0x1b274f,0x1b2922),(0x1b2922,0x1b2947)] if start==0x1b2420 else [(start,end)])
            require([(r.begin,r.end) for r in code.index.groups[start]]==expected,"Original geometry unwind ranges changed")
            instructions=code.instructions(start)
        tail_ok=(instructions[-1].mnemonic=="jmp" and instructions[-1].op_str=="0x1a04e2") if start==0x1a0290 else instructions[-1].mnemonic=="ret"
        require(instructions and instructions[-1].address+instructions[-1].size==end and tail_ok,"Incomplete original function bounds")
        records.append(dict(rva=hex(start),endRva=hex(end),sha256=hashlib.sha256(code.pe.get_data(start,end-start)).hexdigest(),instructions=len(instructions),
            unwindRanges=[[hex(r.begin),hex(r.end)] for r in code.index.groups[start]] if start not in (0x18ca50,0x19a580) else []))
    ray=code.instructions(0x1af350);by={i.address:i for i in ray}
    critical={0x1af3f1:("addss","xmm4, xmm0"),0x1af430:("mulss","xmm2, xmm6"),
        0x1af451:("xor","eax, dword ptr [rbp + 0x38]"),0x1af454:("jns","0x1af6bd"),
        0x1af45a:("subss","xmm2, xmm4"),0x1af477:("andps","xmm5, xmmword ptr [rip + 0x1b72782]"),
        0x1af4e9:("comiss","xmm5, dword ptr [rbx]"),0x1af6a8:("movss","dword ptr [rbx], xmm5")}
    evidence=[]
    for address,(mnemonic,operands) in critical.items():
        i=by[address];require((i.mnemonic,i.op_str)==(mnemonic,operands),"Triangle branch semantics changed")
        evidence.append(dict(rva=hex(address),bytes=bytes(i.bytes).hex(),assembly=i.mnemonic+" "+i.op_str))
    calls=[i.operands[0].imm for i in ray if i.mnemonic=="call" and i.operands[0].type==X86_OP_IMM]
    require(calls==[0x18ca50,0x18ca50,0x18ba80],"Triangle helper call graph differs")
    full=code.instructions(0x1b2420)
    calls=[i.operands[0].imm for i in full if i.mnemonic=="call" and i.operands[0].type==X86_OP_IMM]
    require(calls==[0x1a0290,0x19a580,0x1af350,0x1a0290],"Full mesh raycast helper graph differs")
    output=ROOT/"local/recon/raycast-original-evidence-0.34-v2.json"
    require(not output.exists(),"Never overwrite sealed reverse evidence")
    report=dict(schema="tm2020_original_triangle_raycast_evidence_v1",exeSha256=SHA,functions=records,instructions=evidence,
        abi=dict(rcx="mesh descriptor: vertices at +0, cooked triangles at +0x10",rdx="origin xyz",r8="segment displacement xyz",r9="triangle index",
            stackArguments=["two sided uint32","fraction/max pointer","barycentric U pointer","barycentric V pointer"]),
        twoSidedGate="endpoint-plane sign-bit XOR; signed zeros retained",endpointSumOrder="X,Y,Z",originSumOrder="Y,X,Z",
        fullMeshClosestRecordBytes=48,fullMeshRecord=dict(fraction=0,point=4,normal=16,material=28,instance=32,triangle=40),
        originalGameProcessAccessed=False,completeExactSimulatorQualified=False)
    output.write_text(json.dumps(report,indent=2)+"\n")
    print("PINNED RAYCAST",len(records),"functions; exact sign-bit gate and ordered sums")


if __name__=="__main__":main()
