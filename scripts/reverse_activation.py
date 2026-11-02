"""Complete body-activation preparation scopes and original call evidence."""
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_IMM
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown build')
    c=PeCode(exe);bodies=[];leaves=[(0x7f4760,0x7f4774),(0x7f5130,0x7f513b)]
    for start,end in leaves:
        ins=list(c.cs.disasm(c.pe.get_data(start,end-start),start))
        if c.index.root(start) is not None or ins[-1].address+ins[-1].size!=end or ins[-1].mnemonic!='ret':raise ValueError('Reviewed leaf scope differs')
        bodies.extend(ins)
    ins=c.instructions(0x800c00)
    calls=[i.operands[0].imm for i in ins if i.mnemonic=='call' and i.operands[0].type==X86_OP_IMM]
    if calls!=[0x7f4760,0x7f5130]:raise ValueError('Activation callees differ')
    bodies.extend(ins)
    proof=json.loads((ROOT/'local/recon/recovered-activation-oracle.json').read_text())
    if proof['sha256']!=SHA or proof['cases_per_operation']!=20000 or not proof['bit_exact'] or proof['originalCodeModified'] or proof['functionsSkipped']:raise ValueError('Activation oracle failed')
    report={'schema':'tm2020_activation_evidence_v1','sha256':SHA,
        'completeBatchRanges':[[hex(r.begin),hex(r.end)] for r in c.index.groups[0x800c00]],
        'completeReviewedLeaves':[[hex(a),hex(b)] for a,b in leaves],'directCalls':[hex(x) for x in calls],
        'modelFixedWordOffset':80,'modelMassOffset':24,'itemStride':56,'itemMassOffset':8,
        'itemFlagOffset':4,'relatedItemIdOffset':40,'relatedStateIndexOffset':44,
        'shapeTagByteOffset':17,'sleepWordOffset':4,'coefficientInverseMassOffset':12,
        'coefficientOtherLanesUnchanged':True,'allSourceFlagBytesTested':True,
        'instructions':[{'rva':hex(i.address),'bytes':bytes(i.bytes).hex(),'assembly':i.mnemonic+' '+i.op_str} for i in bodies],
        'sourceHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('native/include/tm2020/recovered_activation.hpp','native/src/recovered_activation.cpp','native/tests/activation_oracle.cpp')},
        'completeSleepingOrWakeSchedulerQualified':False,'completePhysics':False}
    (ROOT/'local/recon/activation-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS ACTIVATION_EVIDENCE complete_batch=true complete_leaves=2 inverse_mass_and_flags_qualified=true sleep_scheduler=false')


if __name__=='__main__':main()
