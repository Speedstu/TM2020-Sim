#!/usr/bin/env python3
"""Read-only pinning of input-decoder entry, player layout and caller clock."""
import hashlib
import json
from capstone.x86 import X86_OP_MEM,X86_REG_RIP
from pe_unwind import PeCode
from run_fast_ppo import ROOT,steam_packs


def main():
    exe=steam_packs().parent/'Trackmania.exe';sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    if sha!='3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda':raise RuntimeError('Unsupported image')
    c=PeCode(exe);prologue=bytes.fromhex('4c894c242048894c240855535741554156')
    if c.pe.get_data(0x12bce40,len(prologue))!=prologue:raise RuntimeError('Decoder prologue changed')
    ins=list(c.cs.disasm(prologue,0x12bce40))
    if sum(i.size for i in ins)!=len(prologue):raise RuntimeError('Split instruction')
    for i in ins:
        if i.mnemonic.startswith(('j','call')) or any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP for o in i.operands):
            raise RuntimeError('Prologue requires relocation')
    body=list(c.cs.disasm(c.pe.get_data(0x12bf000,0x900),0x12bf000));by={i.address:(i.mnemonic,i.op_str) for i in body}
    expected={0x12bf042:('mov','dword ptr [rsp + 0x58], edx'),0x12bf7f9:('mov','r8, rsi'),0x12bf801:('mov','rdx, r15'),
        0x12bf81e:('mov','qword ptr [rsp + 0x20], rax'),0x12bf823:('call','0x12bce40')}
    for at,value in expected.items():
        if by.get(at)!=value:raise RuntimeError(f'Callsite changed at {at:#x}')
    clock_writes=[i for i in body if i.address<0x12bf823 and i.mnemonic not in ('cmp','test') and i.op_str.startswith('dword ptr [rsp + 0x58],')]
    if len(clock_writes)!=1 or clock_writes[0].address!=0x12bf042:raise RuntimeError('Saved clock overwritten')
    # These player-relative addresses were recovered from the same caller;
    # require both instructions, rather than trusting decompiler field names.
    fields={(i.mnemonic,i.op_str) for i in body}
    if not {('lea','rax, [rdi + 0x188]'),('lea','rax, [rdi + 0x1a8]')}<=fields:
        raise RuntimeError('Player input layout changed')
    report={'exeSha256':sha,'entryRva':'0x12bce40','entryBytes':prologue.hex(),
        'returnAddressRva':'0x12bf828','macroClockSlot':'caller RSP+0x58 / decoder entry RSP+0x60','playerRegister':'rdi',
        'currentInputOffset':'0x188','previousInputOffset':'0x1a8','gameAccessed':False,
        'recordingVerifiedInClient':False}
    out=ROOT/'local/recon/replay-controls-0.68/input-entry-audit.json';out.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS pinned input decoder, whole instructions, player records and macro clock')


if __name__=='__main__':main()
