"""Capture bounded sparse numeric inputs to one complete original force worker.

The game process is opened read-only. Original instructions execute only in
Unicorn with copied data. The enclosing force callback is NOT qualified.
"""

import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
from reverse_physics import SHA, ROOT
from pe_unwind import PeCode
from force_worker_fixture import DataPage, encode_fixture, load_fixture

sys.path.insert(0, str(ROOT / "tools/physics-python"))
from unicorn import *
from unicorn.x86_const import *


def capture(args):
    exe = args.exe
    args.output.mkdir(parents=True, exist_ok=True)
    scenarios = (
        ("captured", None),
        ("owned_throttle_straight", (1.0, 0.0, 0.0, (0.0, 0.0, 30.0))),
        ("owned_throttle_left", (1.0, 0.0, 0.75, (0.0, 0.0, 30.0))),
        ("owned_brake_right", (0.0, 1.0, -0.75, (0.0, 0.0, 60.0))),
        ("owned_reverse", (0.5, 0.0, 0.5, (0.0, 0.0, -20.0))),
        ("owned_fast_sliding", (1.0, 0.25, 1.0, (20.0, 0.0, 80.0))),
        ("owned_idle_throttle", (1.0, 0.0, 0.0, (0.0, 0.0, 0.0))),
        ("owned_coast_right", (0.0, 0.0, -1.0, (-5.0, 0.0, 50.0))),
    )
    for name, _ in scenarios:
        if (args.output / (name + ".tmforce")).exists():
            raise FileExistsError("Capture never overwrites a fixture")
    if args.report.exists():
        raise FileExistsError("Capture never overwrites its report")
    manifest = args.manifest.read_text().splitlines()
    if not (manifest[0] == "TM2020_POSE_CANDIDATES_V3" and manifest[3] == SHA):
        raise ValueError("Invalid manifest/build")
    if hashlib.sha256(exe.read_bytes()).hexdigest() != SHA:
        raise ValueError("Unknown executable build")
    pid = int(manifest[1])
    base = args.base
    manager = args.manager
    k = C.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [C.c_uint32, C.c_int, C.c_uint32]
    k.OpenProcess.restype = C.c_void_p
    k.ReadProcessMemory.argtypes = [
        C.c_void_p,
        C.c_void_p,
        C.c_void_p,
        C.c_size_t,
        C.POINTER(C.c_size_t),
    ]
    k.ReadProcessMemory.restype = C.c_int
    k.GetProcessTimes.argtypes = [
        C.c_void_p,
        C.c_void_p,
        C.c_void_p,
        C.c_void_p,
        C.c_void_p,
    ]
    k.GetProcessTimes.restype = C.c_int
    k.QueryFullProcessImageNameW.argtypes = [
        C.c_void_p,
        C.c_uint32,
        C.c_wchar_p,
        C.POINTER(C.c_uint32),
    ]
    k.QueryFullProcessImageNameW.restype = C.c_int
    k.CloseHandle.argtypes = [C.c_void_p]
    h = k.OpenProcess(0x1010, False, pid)
    if not h:
        raise OSError(C.get_last_error())
    try:

        def identity():
            times = [C.c_uint64() for _ in range(4)]
            if not k.GetProcessTimes(h, *[C.byref(x) for x in times]) or times[
                0
            ].value != int(manifest[2]):
                raise ValueError("Stale process creation identity")
            path = C.create_unicode_buffer(32768)
            size = C.c_uint32(32768)
            if (
                not k.QueryFullProcessImageNameW(h, 0, path, C.byref(size))
                or Path(path.value).resolve() != exe.resolve()
            ):
                raise ValueError("Unexpected process executable")

        def read(address, size):
            if size > 4096 * 4:
                raise ValueError("Oversized individual read")
            out = C.create_string_buffer(size)
            got = C.c_size_t()
            if (
                not k.ReadProcessMemory(h, C.c_void_p(address), out, size, C.byref(got))
                or got.value != size
            ):
                raise OSError(f"Unreadable source numeric page at {address:#x}")
            return out.raw

        def u64(a):
            return struct.unpack("<Q", read(a, 8))[0]

        def u32(a):
            return struct.unpack("<I", read(a, 4))[0]

        identity()
        code = PeCode(exe)
        pe = code.pe
        if not (
            read(base, 2) == b"MZ"
            and read(base + pe.DOS_HEADER.e_lfanew, 24)
            == pe.get_data(pe.DOS_HEADER.e_lfanew, 24)
        ):
            raise ValueError("Loaded module differs from pinned PE")
        text_section = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
        code_start = base + text_section.VirtualAddress
        code_end = code_start + text_section.Misc_VirtualSize
        items = u64(manager + 0x20)
        users = u64(manager + 0x40)
        ids = u64(manager + 0xB0)
        index = u32(ids)
        if not all(
            index < u32(manager + offset + 8)
            for offset in (0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80)
        ):
            raise ValueError("Body index exceeds a typed manager span")
        vehicle = u64(users + index * 16 + 8)
        item = items + index * 56
        owner = u64(item + 16)
        item_id = u32(vehicle + 16)
        if not (
            item_id < 0x100000
            and u32(ids + item_id * 4) == index
            and u64(owner + 0x110) == manager
            and u64(item + 32) == base + 0x8427D0
        ):
            raise ValueError("Force context binding differs")
        force_address = u64(manager + 0xA0) + index * 24
        report = {
            "schema": "tm2020_sparse_force_worker_capture_v2",
            "sha256": SHA,
            "pid": pid,
            "readOnlyProcessHandle": True,
            "gameMemoryWritten": False,
            "codeExecutedInGame": False,
            "rawHeapPagesPersisted": False,
            "sparseAccessedNumericBytesPersisted": True,
            "sourceCodeBytesPersisted": False,
            "sourceBindingRecheckedAfterCapture": False,
            "playerOwnershipVerified": False,
            "internalTickVerified": False,
            "completePhysics": False,
            "atomicSnapshot": False,
            "trials": [],
        }
        try:
            for trial, inputs in scenarios:
                mu = Uc(UC_ARCH_X86, UC_MODE_64)
                pages = set()
                coverage = set()
                blocks = []
                writes = set()
                initial = {}
                fault_reason = []
                fetch_count = [0]
                write_pages = set()
                phase = [False]
                masks = {}
                synthetic = [
                    (0x300000000, 0x4000),
                    (0x400000000, 0x20000),
                    (0x500000000, 0x1000),
                ]
                for address, size in synthetic:
                    mu.mem_map(address, size)
                teb = synthetic[0][0]
                mu.mem_write(teb + 0x58, struct.pack("<Q", teb + 0x1000))
                mu.mem_write(teb + 0x1000, struct.pack("<Q", teb + 0x2000))
                mu.reg_write(UC_X86_REG_GS_BASE, teb)

                def load(page, execute=False):
                    if page in pages:
                        return
                    if len(pages) >= 16384:
                        raise ValueError("64 MiB ephemeral source-page bound reached")
                    if execute and not code_start <= page < code_end:
                        raise ValueError(
                            f"External/nonordinary code execution denied at {page:#x}"
                        )
                    data = read(page, 4096)
                    is_code = code_start <= page < code_end
                    if is_code:
                        expected = pe.get_data(page - base, 4096)
                        if data != expected:
                            raise ValueError(
                                f"Loaded code differs from pinned original at RVA {page-base:#x}"
                            )
                    mu.mem_map(page, 4096)
                    mu.mem_write(page, data)
                    mu.mem_protect(
                        page,
                        4096,
                        (
                            UC_PROT_READ | UC_PROT_EXEC
                            if is_code
                            else UC_PROT_READ | UC_PROT_WRITE
                        ),
                    )
                    pages.add(page)
                    if phase[0] and not is_code:
                        initial[page] = data

                def fault(uc, access, address, size, value, user):
                    try:
                        for page in range(
                            address & ~4095, (address + size + 4095) & ~4095, 4096
                        ):
                            load(
                                page,
                                access in [UC_MEM_FETCH_UNMAPPED, UC_MEM_FETCH_PROT],
                            )
                        return True
                    except Exception as error:
                        fault_reason.append(str(error))
                        return False

                mu.hook_add(UC_HOOK_MEM_UNMAPPED, fault)

                def block(uc, address, size, user):
                    if not code_start <= address < code_end:
                        fault_reason.append(
                            f"External/nonordinary block denied at {address:#x}"
                        )
                        uc.emu_stop()
                        return
                    rva = address - base
                    coverage.add(rva)
                    blocks.append(rva)
                    if len(blocks) > 128:
                        del blocks[0]

                mu.hook_add(UC_HOOK_BLOCK, block)

                def mark_access(address, size):
                    if not phase[0]:
                        return
                    for at in range(address, address + size):
                        if (
                            any(
                                start <= at < start + extent
                                for start, extent in synthetic
                            )
                            or code_start <= at < code_end
                        ):
                            continue
                        page = at & ~4095
                        masks.setdefault(page, bytearray(4096))[at - page] = 1

                def owned_read(uc, access, address, size, value, user):
                    mark_access(address, size)

                mu.hook_add(UC_HOOK_MEM_READ, owned_read)

                def owned_write(uc, access, address, size, value, user):
                    mark_access(address, size)

                    if not any(
                        start <= address < start + extent for start, extent in synthetic
                    ):
                        write_pages.add(address & ~4095)

                mu.hook_add(UC_HOOK_MEM_WRITE, owned_write)

                def own_read(address, size):
                    for page in range(
                        address & ~4095, (address + size + 4095) & ~4095, 4096
                    ):
                        load(page)
                    return bytes(mu.mem_read(address, size))

                def own_write(address, data):
                    own_read(address, len(data))
                    mu.mem_write(address, data)

                before = own_read(vehicle, 0x1D00)
                forces_before = own_read(force_address, 24)
                if inputs is not None:
                    throttle, brake, steering, velocity = inputs
                    own_write(vehicle + 0x98, struct.pack("<2f", throttle, brake))
                    own_write(vehicle + 0x1430, struct.pack("<f", steering))
                    state = u64(manager + 0x70) + index * 88
                    own_write(state + 0x40, struct.pack("<3f", *velocity))
                    own_write(vehicle + 0x12FC, struct.pack("<3f", *velocity))
                rsp = 0x400020000 - 0x108
                mu.mem_write(rsp, struct.pack("<Q", 0x500000000))
                mu.mem_write(rsp + 0x28, struct.pack("<I", 10000))
                for register, value in [
                    (UC_X86_REG_RSP, rsp),
                    (UC_X86_REG_RCX, owner),
                    (UC_X86_REG_RDX, item_id),
                    (UC_X86_REG_R8, 10000000000),
                    (UC_X86_REG_XMM3, 0x3C23D70B),
                    (UC_X86_REG_MXCSR, 0x1F80),
                ]:
                    mu.reg_write(register, value)

                def stop_at_worker(uc, address, size, user):
                    uc.emu_stop()

                entry_hook = mu.hook_add(
                    UC_HOOK_CODE,
                    stop_at_worker,
                    begin=base + 0x851F00,
                    end=base + 0x851F00,
                )
                started = time.perf_counter()
                error = None
                worker_entered = False

                try:
                    mu.emu_start(base + 0x8427D0, 0x500000000, count=2000000)
                    if mu.reg_read(UC_X86_REG_RIP) == base + 0x851F00:
                        worker_entered = True
                        mu.hook_del(entry_hook)
                        phase[0] = True
                        coverage.clear()
                        blocks.clear()
                        write_pages.clear()
                        initial.update(
                            {
                                page: bytes(mu.mem_read(page, 4096))
                                for page in pages
                                if not code_start <= page < code_end
                            }
                        )
                        abi_context = bytes(
                            mu.mem_read(mu.reg_read(UC_X86_REG_R8), 0x58)
                        )
                        abi_time = mu.reg_read(UC_X86_REG_RCX)
                        abi_float = mu.reg_read(UC_X86_REG_XMM1) & 0xFFFFFFFF
                        abi_r9 = mu.reg_read(UC_X86_REG_R9)

                        # Select the complete worker as the oracle boundary; its normal RET now
                        # returns to our owned sentinel. No instruction/callee is patched/skipped.
                        mu.mem_write(
                            mu.reg_read(UC_X86_REG_RSP), struct.pack("<Q", 0x500000000)
                        )
                        mu.emu_start(base + 0x851F00, 0x500000000, count=2000000)

                except UcError as exc:
                    error = str(exc)
                end = mu.reg_read(UC_X86_REG_RIP)
                completed = end == 0x500000000
                after = own_read(vehicle, 0x1D00)
                forces_after = own_read(force_address, 24)
                roots = sorted(
                    {
                        code.index.root(x)
                        for x in coverage
                        if code.index.root(x) is not None
                    }
                )
                result = {
                    "trial": trial,
                    "ownedInputOverride": inputs,
                    "completed": completed,
                    "endRva": (
                        hex(end - base)
                        if base <= end < base + pe.OPTIONAL_HEADER.SizeOfImage
                        else hex(end)
                    ),
                    "error": error,
                    "faultReasons": fault_reason,
                    "mappedPages": len(pages),
                    "writtenCopyPages": len(write_pages),
                    "executedRoots": [hex(x) for x in roots],
                    "executedVariant5": 0x851F00 in coverage,
                    "completeWorkerBoundarySelected": worker_entered,
                    "completeEnclosingCallbackQualified": False,
                    "lastBlocks": [hex(x) for x in blocks[-32:]],
                    "forcesBefore": list(struct.unpack("<6f", forces_before)),
                    "forcesAfter": list(struct.unpack("<6f", forces_after)),
                    "changedVehicleWordOffsets": [
                        hex(i)
                        for i in range(0, len(before), 4)
                        if before[i : i + 4] != after[i : i + 4]
                    ],
                    "elapsedSeconds": time.perf_counter() - started,
                }
                if completed:
                    fixture_dir = args.output
                    destination = fixture_dir / (trial + ".tmforce")
                    code_pages = sorted(
                        page - base for page in pages if code_start <= page < code_end
                    )
                    data_pages = sorted(
                        page for page, mask in masks.items() if any(mask)
                    )
                    saved = []
                    for page in data_pages:
                        mask = bytes(masks[page])
                        before_page = initial[page]
                        after_page = bytes(mu.mem_read(page, 4096))
                        saved.append(
                            DataPage(
                                page,
                                mask,
                                bytes(b if m else 0 for b, m in zip(before_page, mask)),
                                bytes(b if m else 0 for b, m in zip(after_page, mask)),
                            )
                        )
                    out = encode_fixture(
                        base,
                        pe.OPTIONAL_HEADER.SizeOfImage,
                        abi_time,
                        abi_float,
                        0x1F80,
                        abi_r9,
                        force_address,
                        vehicle,
                        abi_context,
                        code_pages,
                        saved,
                    )
                    with destination.open("xb") as target:
                        target.write(out)
                    load_fixture(destination, pe)
                    result["sparseFixtureSha256"] = hashlib.sha256(out).hexdigest()
                    result["sparseFixtureBytes"] = len(out)
                    result["codePages"] = len(code_pages)
                    result["dataPages"] = len(data_pages)
                    result["onlyAccessedDataBytesRetained"] = True
                    result["retainedDataBytes"] = sum(sum(masks[p]) for p in data_pages)
                    result["sourceCodeBytesRetained"] = False
                report["trials"].append(result)
                print(
                    json.dumps(
                        {
                            k: result[k]
                            for k in [
                                "trial",
                                "completed",
                                "endRva",
                                "error",
                                "faultReasons",
                                "mappedPages",
                                "executedVariant5",
                                "forcesAfter",
                            ]
                        }
                    ),
                    flush=True,
                )
                if not completed:
                    raise RuntimeError(
                        "Complete force worker failed: " + str(result["faultReasons"])
                    )
            identity()
            if not (
                u64(item + 16) == owner
                and u64(users + index * 16 + 8) == vehicle
                and u64(owner + 0x110) == manager
                and u32(ids + item_id * 4) == index
            ):
                raise ValueError("Typed body/context binding changed during capture")
            report["sourceBindingRecheckedAfterCapture"] = True
        finally:
            args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    finally:
        k.CloseHandle(h)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base", type=lambda x: int(x, 0), required=True)
    parser.add_argument("--manager", type=lambda x: int(x, 0), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    capture(parser.parse_args())
