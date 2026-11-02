#!/usr/bin/env python3
"""Read-only, build-pinned proof that injection precedes cached pedal reads."""
import hashlib
import json
from pathlib import Path
from pe_unwind import PeCode
from run_fast_ppo import ROOT, steam_packs


def main():
    exe = steam_packs().parent / 'Trackmania.exe'
    sha = hashlib.sha256(exe.read_bytes()).hexdigest()
    if sha != '3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda':
        raise RuntimeError('Unsupported client image')
    code = PeCode(exe)
    prologue = bytes.fromhex('4883ec284c8b49084c8bd9498d8980120000')
    if code.pe.get_data(0x83de60, len(prologue)) != prologue:
        raise RuntimeError('Early entry bytes differ')
    instructions = {i.address: (i.mnemonic, i.op_str) for i in code.instructions(0x851f00)}
    expected = {
        0x851f23: ('mov', 'r10d, 4'),
        0x851f9e: ('call', '0x83de60'),
        0x851fa3: ('movss', 'xmm0, dword ptr [rdi + 0x9c]'),
        0x851fbb: ('movss', 'xmm0, dword ptr [rdi + 0x98]'),
        0x852013: ('mov', 'r8d, r10d'),
        0x852110: ('call', '0x841500'),
    }
    for address, value in expected.items():
        if instructions.get(address) != value:
            raise RuntimeError(f'Changed pedal dataflow at {address:#x}')
    # Every copied instruction must be whole and independently relocatable.
    from capstone.x86 import X86_OP_MEM, X86_REG_RIP
    copied = [i for i in code.instructions(0x83de60) if i.address < 0x83de60 + len(prologue)]
    if sum(i.size for i in copied) != len(prologue):
        raise RuntimeError('Hook would split an instruction')
    for ins in copied:
        if ins.mnemonic.startswith(('j', 'call')) or any(
                op.type == X86_OP_MEM and op.mem.base == X86_REG_RIP for op in ins.operands):
            raise RuntimeError('Prologue requires relocation')
    report = {'exeSha256': sha, 'earlyEntryRva': '0x83de60',
              'entryBytes': prologue.hex(), 'oldHookOccursAfterCachedPedals': True,
              'r10LiveAcrossEarlyCall': True,
              'checkedInstructions': {hex(a): ' '.join(v) for a, v in expected.items()},
              'gameAccessed': False, 'gameFinishVerified': False}
    output = ROOT / 'local/recon/internal-0.65/pedal-order-audit.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS pinned early entry, whole relocatable instructions, cached-pedal ordering')


if __name__ == '__main__':
    main()
