"""Check the static callback-context path independently of live addresses."""
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_MEM,X86_REG_RIP
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown build')
    c=PeCode(exe)
    # Reviewed executable region precedes the registration function's jump
    # table. The complete chained root is not accepted as a linear decode.
    registration=list(c.cs.disasm(c.pe.get_data(0x7cb530,0x3b0),0x7cb530))
    if registration[-1].address+registration[-1].size!=0x7cb8e0:raise ValueError('Registration code boundary differs')
    functions={r:c.instructions(r) for r in (0x7bbb40,0x7bb860,0x8427d0)}
    instructions={i.address:i for body in [registration,*functions.values()] for i in body}
    expected={0x7cb55e:('mov','rsi, rcx'),0x7cb6da:('mov','qword ptr [rbp - 0x78], rsi'),
        0x7bb939:('mov','rdx, qword ptr [r12 + 0x28]'),0x7bb93e:('mov','qword ptr [rax + 0x10], rdx'),
        0x7bb94b:('mov','rdx, qword ptr [r12 + 0x30]'),0x7bb950:('mov','qword ptr [rax + 0x20], rdx'),
        0x842809:('mov','r15, rcx'),0x84282a:('mov','r14, qword ptr [r15 + 0x110]')}
    for address,(mnemonic,operands) in expected.items():
        i=instructions.get(address)
        if i is None or (i.mnemonic,i.op_str)!=(mnemonic,operands):raise ValueError('Callback-context layout differs')
    lea=instructions[0x7cb6bf]
    targets=[lea.address+lea.size+op.mem.disp for op in lea.operands if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP]
    if lea.mnemonic!='lea' or targets!=[0x8427d0]:raise ValueError('Force callback target differs')
    selected=[instructions[a] for a in sorted(expected)]+[lea]
    report={'schema':'tm2020_force_callback_context_evidence_v1','sha256':SHA,
        'registrationCodeRegion':['0x7cb530','0x7cb8e0'],'registrationWholeRootLinearDecodeQualified':False,
        'completeUnwindProcedures':[hex(r) for r in functions],
        'itemStride':56,'itemContextOffset':16,'itemForceCallbackOffset':32,'contextDynaLinkOffset':272,
        'forceCallbackRva':'0x8427d0','liveCaptureSeparatelyChecksVehicleListMembership':True,
        'instructions':[{'rva':hex(i.address),'bytes':bytes(i.bytes).hex(),'assembly':i.mnemonic+' '+i.op_str} for i in selected],
        'playerOwnerVerified':False,'internalPhysicsClockVerified':False}
    (ROOT/'local/recon/force-context-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS FORCE_CONTEXT_EVIDENCE item_context=0x10 callback=0x20 owner_dyna_link=0x110 player_and_tick_unverified=true')


if __name__=='__main__':main()
