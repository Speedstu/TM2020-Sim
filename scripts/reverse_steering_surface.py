"""Retain full steering, inverse-trig and surface-scalar instruction evidence."""
import hashlib
import json
from pathlib import Path
import struct
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown build')
    c=PeCode(exe);roots=[0x18d150,0x18d230,0x841b40,0x8465e0];rows=[];constants={}
    expected={0x18d150:[0x195dd00],0x18d230:[0x195dd00],0x841b40:[0x18d150,0x83dbd0],0x8465e0:[0x843150,0x195dd00,0x42bcb0]}
    for root in roots:
        ins=c.instructions(root)
        calls=[i.operands[0].imm for i in ins if i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM]
        if c.index.root(root)!=root or calls!=expected[root]:raise ValueError('Complete procedure/callees changed')
        for i in ins:
            for op in i.operands:
                if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                    rva=i.address+i.size+op.mem.disp;constants[hex(rva)]=hex(struct.unpack('<I',c.pe.get_data(rva,4))[0])
        rows.append({'root':hex(root),'ranges':[[hex(r.begin),hex(r.end)] for r in c.index.groups[root]],
            'directCalls':[hex(x) for x in calls],
            'instructions':[{'rva':hex(i.address),'bytes':bytes(i.bytes).hex(),'assembly':i.mnemonic+' '+i.op_str} for i in ins]})
    leaves=[]
    for start,end in [(0x83dbd0,0x83dbeb),(0x843150,0x84317b)]:
        ins=list(c.cs.disasm(c.pe.get_data(start,end-start),start))
        if c.index.root(start) is not None or ins[-1].address+ins[-1].size!=end or ins[-1].mnemonic!='ret':raise ValueError('Reviewed predicate bounds changed')
        leaves.append({'range':[hex(start),hex(end)],'instructions':[{'rva':hex(i.address),'bytes':bytes(i.bytes).hex(),'assembly':i.mnemonic+' '+i.op_str} for i in ins]})
    proof_path=ROOT/'local/recon/recovered-steering-surface-oracle.json';proof=json.loads(proof_path.read_text())
    if proof['sha256']!=SHA or proof['cases_per_operation']!=20000 or proof['operations']!=4 or not proof['bit_exact'] or proof['originalCodeModified'] or proof['functionsSkipped']:raise ValueError('Native original-code evidence failed')
    report={'schema':'tm2020_steering_surface_evidence_v1','sha256':SHA,'completeProcedures':rows,
        'completeReviewedPredicates':leaves,'binary32ConstantWordsByRva':constants,
        'steeringUsesEngineAsinApproximation':True,'inverseTrigAbsoluteArgumentLimit':100000,
        'outOfMathematicalDomainNativeSignedZeroRetained':True,
        'negativeSqrtFallbackUnreachableWithinQualifiedDomain':True,'surfaceScalarOffset':5028,
        'surfaceScalarPhysicalMeaningVerified':False,'curveOffset':1592,
        'oracleSha256':hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        'sourceHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('native/include/tm2020/recovered_steering.hpp','native/src/recovered_steering.cpp','native/tests/steering_oracle.cpp')},
        'completeTireForcesQualified':False,'completeVehiclePhysics':False}
    (ROOT/'local/recon/steering-surface-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS STEERING_SURFACE_EVIDENCE complete_functions=4 complete_predicates=2 original_domain_qualified=true full_tire_forces=false')


if __name__=='__main__':main()
