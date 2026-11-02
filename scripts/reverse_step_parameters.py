"""Retain complete step-constructor code and independently checked constants."""
import hashlib
import json
from pathlib import Path
import struct
from capstone.x86_const import X86_OP_IMM
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown build')
    code=PeCode(exe)
    leaf_start,leaf_end=0x7f3ec0,0x7f3f3a
    leaf=list(code.cs.disasm(code.pe.get_data(leaf_start,leaf_end-leaf_start),leaf_start))
    if code.index.root(leaf_start) is not None or leaf[-1].mnemonic!='ret' or leaf[-1].address+leaf[-1].size!=leaf_end:raise ValueError('Leaf bounds changed')
    constructor=code.instructions(0x8020a0)
    if code.index.root(0x8020a0)!=0x8020a0:raise ValueError('Constructor root changed')
    calls=[i.operands[0].imm for i in constructor if i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM]
    if calls!=[leaf_start,0x195dd00]:raise ValueError('Constructor callees changed')
    constants={0x1d1ee14:0x3c23d70b,0x1d1fc6c:0xbcb6c518,0x1d1f4a4:0x3fb8aa3b,
        0x1d1f3c8:0x3f800000,0x1d1fecc:0xc2fc0000,0x1d1f87c:0x41ddd2fe,
        0x1d1f760:0x409af5f8,0x1d1f97c:0x42f28c51,0x1d1f4cc:0x3fbebc8d,0x1d1fba8:0x4b000000}
    rows=[]
    for rva,bits in constants.items():
        raw=code.pe.get_data(rva,4)
        if struct.unpack('<I',raw)[0]!=bits:raise ValueError('Step constant changed')
        rows.append({'rva':hex(rva),'bits':hex(bits),'float':struct.unpack('<f',raw)[0]})
    destination=ROOT/'local/recon/step-parameter-evidence.json'
    report={'schema':'tm2020_step_parameter_evidence_v1','sha256':SHA,
        'completeConstructorRanges':[[hex(r.begin),hex(r.end)] for r in code.index.groups[0x8020a0]],
        'completeReviewedLeafRange':[hex(leaf_start),hex(leaf_end)],'constants':rows,
        'constructorCalls':[hex(x) for x in calls],
        'negativeSquaredNormFallbackUnreachableWithinFiniteGravityDomain':True,
        'opaqueOutputWordsRetained':[36,40],
        'instructions':[{'rva':hex(i.address),'bytes':bytes(i.bytes).hex(),'assembly':i.mnemonic+' '+i.op_str} for i in leaf+constructor],
        'sourceHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('native/include/tm2020/recovered_step.hpp','native/src/recovered_step.cpp','native/tests/step_oracle.cpp')},
        'completeAdaptiveSchedulerQualified':False}
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS STEP_PARAMETER_EVIDENCE complete_constructor=true complete_leaf=true constants=10 scheduler_qualified=false')


if __name__=='__main__':main()
