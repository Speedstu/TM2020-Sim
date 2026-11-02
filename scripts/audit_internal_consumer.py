#!/usr/bin/env python3
"""Read-only audit of the installed, SHA-pinned physics command consumer."""
import hashlib
import json
from pathlib import Path
from pe_unwind import PeCode
from run_fast_ppo import ROOT,steam_packs

def main():
    exe=steam_packs().parent/'Trackmania.exe';sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    if sha!='3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda':raise RuntimeError('Unsupported client build')
    code=PeCode(exe);prologue=code.pe.get_data(0x841500,13)
    if prologue.hex()!='488bc45341554881eca8000000':raise RuntimeError('Consumer prologue differs')
    roots=(0x841500,0x843190,0x7be690,0x869cd0,0x86b060,0x86bc50,0x851f00,0x7d1380)
    instructions={i.address:i for root in roots for i in code.instructions(root)}
    expected={0x841521:('mov','rbx, rdx'),0x841545:('movaps','xmm9, xmm3'),
              0x841550:('mov','edx, dword ptr [rdx + 0x10]'),
              0x84169e:('movss','xmm1, dword ptr [rbx + 0x9c]'),
              0x8416a8:('movss','xmm1, dword ptr [rbx + 0x98]'),
              0x8416da:('movss','xmm1, dword ptr [rbx + 0xa0]'),
              0x841734:('movss','dword ptr [rbx + 0x1430], xmm1'),
              0x843230:('movss','xmm0, dword ptr [r8 + 0x98]'),
              0x84327a:('movss','xmm1, dword ptr [r8 + 0x9c]'),
              **{address:('call','0x841500') for address in (0x869e8d,0x86b0f6,0x86bd10,0x852110)}}
    for address,assembly in expected.items():
        ins=instructions.get(address)
        if ins is None or (ins.mnemonic,ins.op_str)!=assembly:raise RuntimeError(f'Changed internal dataflow at {address:#x}')
    # A hook at entry must precede every direct command read, and the original
    # consumer must not overwrite the input scalars before using them.
    from capstone.x86 import X86_OP_MEM,X86_REG_RBX
    from capstone import CS_AC_WRITE
    writes=[]
    for ins in code.instructions(0x841500):
        for op in ins.operands:
            if op.type==X86_OP_MEM and op.mem.base==X86_REG_RBX and op.mem.disp in (0x98,0x9c,0xa0) and op.access&CS_AC_WRITE:writes.append(hex(ins.address))
    if writes:raise RuntimeError(f'Consumer overwrites requested controls: {writes}')
    output=ROOT/'local/recon/internal-0.46';output.mkdir(parents=True,exist_ok=True)
    evidence={'executable':str(exe),'sha256':sha,'entryRva':'0x841500','entryBytes':prologue.hex(),
              'checkedInstructions':{hex(a):' '.join(v) for a,v in expected.items()},'directInputWritesInConsumer':writes,
              'liveTickQualified':False,'raceStartFieldLiveQualified':False,'gameFinishVerified':False}
    (output/'consumer-audit.json').write_text(json.dumps(evidence,indent=2)+'\n')
    (output/'consumer-audit.asm').write_text('\n'.join(f'{i.address:#x} {i.mnemonic} {i.op_str}' for root in roots for i in code.instructions(root))+'\n')
    print('PASS pinned consumer entry, vehicle argument, pedal/steering reads, four call sites; live timing remains unqualified')
if __name__=='__main__':main()
