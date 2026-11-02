"""Run the COMPLETE original force worker offline; never opens a game process."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

from reverse_physics import ROOT, SHA
from force_worker_fixture import ENTRY, SYNTHETIC, load_fixture, require


def replay(exe, paths, report_path):
    require(hashlib.sha256(exe.read_bytes()).hexdigest() == SHA, 'Unknown original executable')
    sys.path.insert(0, str(ROOT / 'tools/physics-python'))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_PROT_READ, UC_PROT_EXEC, UC_PROT_WRITE
    from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.x86_const import (UC_X86_REG_RSP, UC_X86_REG_RCX, UC_X86_REG_XMM1,
                                  UC_X86_REG_R8, UC_X86_REG_R9, UC_X86_REG_MXCSR,
                                  UC_X86_REG_GS_BASE, UC_X86_REG_RIP)
    import pefile
    pe = pefile.PE(str(exe), fast_load=True)
    reports = []
    for path in paths:
        f = load_fixture(path, pe)
        mu = Uc(UC_ARCH_X86, UC_MODE_64)
        for rva in f.code_pages:
            mu.mem_map(f.base+rva, 4096)
            mu.mem_write(f.base+rva, pe.get_data(rva, 4096))
            mu.mem_protect(f.base+rva, 4096, UC_PROT_READ | UC_PROT_EXEC)
        pages = {p.address: p for p in f.data_pages}
        for p in f.data_pages:
            mu.mem_map(p.address, 4096)
            mu.mem_write(p.address, p.initial)
            mu.mem_protect(p.address, 4096, UC_PROT_READ | UC_PROT_WRITE)
        for address, size in SYNTHETIC:
            mu.mem_map(address, size)
        mu.mem_write(0x200000000, f.context)
        mu.mem_write(0x300000058, struct.pack('<Q', 0x300001000))
        mu.mem_write(0x300001000, struct.pack('<Q', 0x300002000))
        rsp = 0x400020000 - 0x108
        mu.mem_write(rsp, struct.pack('<Q', 0x500000000))
        reasons = []
        code = {f.base+rva for rva in f.code_pages}

        def access(uc, kind, address, size, value, user):
            for at in range(address, address+size):
                if any(a <= at < a+n for a, n in SYNTHETIC) or at & ~4095 in code:
                    continue
                p = pages.get(at & ~4095)
                if p is None or p.mask[at & 4095] != 1:
                    reasons.append(f'Access outside captured byte mask: {at:#x}, kind={kind}')
                    uc.emu_stop()
                    return

        mu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access)
        for register, value in ((UC_X86_REG_RSP, rsp), (UC_X86_REG_RCX, f.timestamp),
                                (UC_X86_REG_XMM1, f.float_bits), (UC_X86_REG_R8, 0x200000000),
                                (UC_X86_REG_R9, f.r9), (UC_X86_REG_MXCSR, f.mxcsr),
                                (UC_X86_REG_GS_BASE, 0x300000000)):
            mu.reg_write(register, value)
        started = time.perf_counter()
        mu.emu_start(f.base+ENTRY, 0x500000000, count=2000000)
        require(mu.reg_read(UC_X86_REG_RIP) == 0x500000000 and not reasons,
                'Worker did not return within captured accesses: ' + str(reasons))
        for p in f.data_pages:
            require(bytes(mu.mem_read(p.address, 4096)) == p.expected,
                    f'Complete output page differs at {p.address:#x}')
        reports.append(dict(fixture=path.name, fixtureSha256=f.sha256,
                            codePages=len(f.code_pages), dataPages=len(f.data_pages),
                            retainedDataBytes=sum(sum(p.mask) for p in f.data_pages),
                            allDataPagesBitExact=True, allAccessesInsideCapturedByteMasks=True,
                            completeWorkerReturned=True, gameProcessAccessed=False,
                            functionsSkipped=False, originalCodeModified=False,
                            elapsedSeconds=time.perf_counter()-started))
        print('PASS OFFLINE_COMPLETE_FORCE_WORKER', path.name, flush=True)
    report = dict(schema='tm2020_offline_force_worker_v2', sha256=SHA, entryRva=hex(ENTRY),
                  fixtures=reports, originalExecutableRequired=True, wholeGameStepQualified=False,
                  fullVehicleSimulatorReady=False)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--fixtures', type=Path, nargs='+', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    replay(args.exe, args.fixtures, args.report)
