"""Owned, sparse, fail-closed execution of the pinned original main step.

No process access. The backend requires the original local image and captured
numeric inputs. Unknown memory/code stops execution; this is not a complete
Trackmania simulator or a substitute for complete map initialization.
"""
import hashlib
import math
import struct
import sys
from dataclasses import dataclass
from types import MappingProxyType

from pinned_build import ROOT
from force_worker_fixture import require
from original_step_fixture import CONTROL_REGIONS

sys.path.insert(0, str(ROOT / "tools/physics-python"))
from unicorn import *
from unicorn.x86_const import *


def open_owned_machine(fixture_path, exe, ntdll, kernel32, max_steps=None, native_guard=None,
                       initialize_writes=False,counter_transcript=None):
    """Verify local images before mapping any original instructions."""
    from original_step_fixture import load_original_step_fixture, verify_original_step_images
    from pathlib import Path
    fixture = load_original_step_fixture(fixture_path)
    images = verify_original_step_images(fixture, tuple(map(Path, (exe,ntdll,kernel32))))
    return OriginalStepMachine(fixture, images, Path(kernel32), max_steps=max_steps,
                               native_guard=native_guard,initialize_writes=initialize_writes,
                               counter_transcript=counter_transcript)


class UncapturedStepError(RuntimeError):
    """The current owned state is unusable until restored or reset."""


@dataclass(frozen=True)
class OwnedCheckpoint:
    owner: object
    pages: object
    context: object
    frame: int
    heap_cursor: int
    allocations: object
    initialized_pages: object=None
    counter_cursor: int=0


class OriginalStepMachine:
    def __init__(self, fixture, images, kernel32, data=None, trial=None, max_steps=None,
                 native_guard=None,initialize_writes=False,counter_transcript=None):
        require(not initialize_writes or native_guard is not None,
                "Write-initialization tracking requires the compiled guard")
        f = fixture
        metadata = f.metadata
        trial = trial or "owned_interactive"
        data = data if data is not None else {
            address: (p.mask, p.initial, p.expected) for address, p in f.pages.items()
        }
        images[1].parse_data_directories(directories=[0])
        export_rvas = {
            item.name.decode(): item.address
            for item in images[1].DIRECTORY_ENTRY_EXPORT.symbols if item.name
        }
        report = {"modeledOsImports": []}
        fault_reason = []
        watched_roots = {
            rva: 0
            for rva in (
                0x7BD0E0,
                0x8025A0,
                0x851F00,
                0x7F89D0,
                0x7F4D40,
                0x7F6EC0,
                0x7F63F0,
                0x7F6590,
                0x8603B0,
                0x860980,
                0x843920,
                0x840890,
                0x7d2b90,
                0x1500140,
                0x1501800,
                0x15009d0,
                0x14ffee0,
                0x14ff9d0,
            )
        }
        wheel_entry_samples = []
        current_frame = [0]
        vehicle_selection_inputs={}
        vehicle_substep_intervals = {}
        integration_intervals = {"forceVelocity": {}, "pose": {}}
        base, ntdll_base = [m["base"] for m in metadata["modules"]]
        manager = metadata["manager"]
        synthetic = metadata["synthetic"]
        platform_boundaries = set()
        counter_cursor=[0]
        outer_controls=[None];outer_action_calls=[0]
        require(counter_transcript is None or (metadata.get("outerSceneStage") is not None
            and isinstance(counter_transcript,list) and 0<len(counter_transcript)<=512),
            "Counter transcript requires a bounded outer-scene observation")
        if counter_transcript is not None:
            for row in counter_transcript:
                require({"returnAddress","outputAddress","counterValue","resultWord"}<=set(row)
                    and set(row)<={"returnAddress","outputAddress","counterValue","resultWord","clockWrapperReturnAddress"}
                    and 0<=int(row["counterValue"])<2**63 and row["resultWord"]==1
                    and all(0x10000<=int(row[k],0)<2**64 for k in ("returnAddress","outputAddress")),
                    "Malformed observed counter call")
        executable_ranges = [
            (
                m["base"] + s.VirtualAddress,
                m["base"] + s.VirtualAddress + s.Misc_VirtualSize,
            )
            for m, p in zip(metadata["modules"], images)
            for s in p.sections
            if s.Characteristics & 0x20000000
        ]

        def executable_address(address):
            return any(a <= address < b for a, b in executable_ranges)

        mu = Uc(UC_ARCH_X86, UC_MODE_64)
        for address, size in synthetic:
            mu.mem_map(address, size)
        code_pages = set()
        overlays = {
            (r["module"], r["rva"]): r["bytes"] for r in metadata["codeDataOverlays"]
        }
        for module, rva in metadata["codePages"]:
            address = metadata["modules"][module]["base"] + rva
            require(
                address not in code_pages and executable_address(address),
                "Invalid code page",
            )
            raw = bytearray(images[module].get_data(rva, 4096))
            require(len(raw) == 4096, "Truncated code page")
            for offset, value in overlays.get((module, rva), []):
                raw[offset] = value
            mu.mem_map(address, 4096)
            mu.mem_write(address, bytes(raw))
            mu.mem_protect(address, 4096, UC_PROT_READ | UC_PROT_EXEC)
            code_pages.add(address)
        external_pages=set()
        for external in metadata.get("externalPlatformModels", []):
            require(
                external["module"] == "kernel32" and external["function"] in
                    ("HeapFree","QueryPerformanceCounter"),
                "Unknown external binding",
            )
            require(
                hashlib.sha256(kernel32.read_bytes()).hexdigest()
                == external["moduleSha256"],
                "OS module cohort differs",
            )
            page = external["address"] & ~4095
            if page not in external_pages:
                mu.mem_map(page, 4096)
                mu.mem_write(page, b"\xcc" * 4096)
                mu.mem_protect(page, 4096, UC_PROT_READ | UC_PROT_EXEC)
                external_pages.add(page)
        for address, (mask, initial, expected) in data.items():
            if not any(a <= address < a + n for a, n in synthetic):
                mu.mem_map(address, 4096)
            require(address not in code_pages, "Code/data overlap")
            mu.mem_write(address, initial)

        def load(page):
            if page not in data and page not in code_pages:
                raise ValueError(f"Uncaptured source page requested {page:#x}")

        excluded = [
            (0x200000000, 0x10000),
            (0x300000000, 0x4000),
            (0x400000000, 0x20000),
            (0x500000000, 0x1000),
        ]

        touched = set()

        def mark_access(address, size, writing=False):
            if initialize_writes:
                compiled_guard.access(compiled_guard.handle,address,size,int(writing))
                self._sync_native_guard()
                return
            for page in range(address & ~4095, (address + size + 4095) & ~4095, 4096):
                if any(a <= page < a + n for a, n in synthetic):
                    touched.add(page)
            for at in range(address, address + size):
                if (
                    any(a <= at < a + n for a, n in excluded)
                    or at & ~4095 in code_pages
                ):
                    continue
                page = at & ~4095
                if page not in data or data[page][0][at & 4095] != 1:
                    pc=mu.reg_read(UC_X86_REG_RIP)
                    report.setdefault("uncapturedAccesses",[]).append(dict(
                        address=at,accessStart=address,bytes=size,instructionAddress=pc,
                        instructionGameRva=pc-base,frame=current_frame[0]+1))
                    fault_reason.append(f"Access outside captured bytes {at:#x}; instruction {pc:#x} (game RVA {pc-base:#x})")
                    mu.emu_stop()
                    return

        def memory_access(uc, access, address, size, value, user):
            mark_access(address, size)

        compiled_guard=None
        if native_guard is None:
            mu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, memory_access)
        else:
            from owned_native_guard import NativeGuard
            compiled_guard=NativeGuard(mu,native_guard)
            compiled_guard.write_initialization(compiled_guard.handle,int(initialize_writes))
            compiled_guard.sync_masks(data)
            for page in code_pages:
                module=1 if ntdll_base<=page<ntdll_base+metadata["modules"][1]["imageSize"] else 0
                raw=images[module].get_data(page-metadata["modules"][module]["base"],4096)
                compiled_guard.add_page(page,raw,code=True)
            for address,size in synthetic:
                require(compiled_guard.range(compiled_guard.handle,address,size,0),
                        "Cannot register synthetic guard range")
            for address,size in excluded:
                require(compiled_guard.range(compiled_guard.handle,address,size,1),
                        "Cannot register excluded guard range")
            require(compiled_guard.start(compiled_guard.handle),"Cannot start native guard")

        native_enabled=compiled_guard is not None
        def guard(uc, address, size, user):
            if address in platform_boundaries:
                return
            rva = address - base
            if rva in watched_roots:
                watched_roots[rva] += 1
            if rva==0x1501b57:
                selector_at=uc.reg_read(UC_X86_REG_RAX)+0x54
                selector_page=selector_at&~4095;selector_offset=selector_at&4095
                if selector_page in data and all(data[selector_page][0][selector_offset:selector_offset+4]):
                    row=dict(scaledMotionBits=uc.reg_read(UC_X86_REG_XMM6)&0xffffffff,
                        motionLimitBits=struct.unpack("<I",uc.mem_read(selector_at,4))[0],
                        timeScaleBits=uc.reg_read(UC_X86_REG_XMM11)&0xffffffff,
                        intervalBits=struct.unpack("<I",uc.mem_read(uc.reg_read(UC_X86_REG_R15)+8,4))[0],
                        totalScaledIntervalBits=uc.reg_read(UC_X86_REG_XMM7)&0xffffffff)
                    vehicle_selection_inputs.setdefault(str(current_frame[0]+1),[]).append(row)
            if rva==0x14ff9d0:
                bits=uc.reg_read(UC_X86_REG_XMM2)&0xffffffff
                counts=vehicle_substep_intervals.setdefault(str(current_frame[0]+1),{})
                key=f"0x{bits:08x}"
                counts[key]=counts.get(key,0)+1
            if rva == 0x8447b0:
                vehicle = uc.reg_read(UC_X86_REG_RCX)
                flags = []
                for index in range(4):
                    at = vehicle + 0x17b4 + index*0xb8
                    mark_access(at,4)
                    if fault_reason:
                        return
                    flags.append(struct.unpack("<I",bytes(uc.mem_read(at,4)))[0])
                if len(wheel_entry_samples)>=1000:
                    wheel_entry_samples.pop(0)
                wheel_entry_samples.append(dict(groundFlags=flags,
                    driveArgument=struct.unpack("<f",struct.pack("<I",
                        uc.reg_read(UC_X86_REG_XMM1)&0xffffffff))[0]))
            if rva in (0x7F89D0, 0x7F4D40):
                offset = 0x48 if rva == 0x7F89D0 else 0x28
                bits = struct.unpack(
                    "<I", bytes(uc.mem_read(uc.reg_read(UC_X86_REG_RSP) + offset, 4))
                )[0]
                values = integration_intervals[
                    "forceVelocity" if rva == 0x7F89D0 else "pose"
                ]
                key = f"0x{bits:08x}"
                values[key] = values.get(key, 0) + 1
            if native_enabled:
                return  # The C++ hook validates EVERY executed instruction.
            if not 0 < size <= 15:
                fault_reason.append(f"Unsupported instruction at {address:#x}")
                uc.emu_stop()
                return
            module = (
                1
                if ntdll_base
                <= address
                < ntdll_base + metadata["modules"][1]["imageSize"]
                else 0
            )
            if address & ~4095 not in code_pages or bytes(
                uc.mem_read(address, size)
            ) != images[module].get_data(
                address - metadata["modules"][module]["base"], size
            ):
                fault_reason.append(f"Unvalidated instruction at {address:#x}")
                uc.emu_stop()

        if compiled_guard is None:
            mu.hook_add(UC_HOOK_CODE, guard)
        else:
            for rva in watched_roots.keys() | {0x1501b57,0x8447b0}:
                mu.hook_add(UC_HOOK_CODE,guard,begin=base+rva,end=base+rva)

        def invalid_mapping(uc,access,address,size,value,user):
            pc=uc.reg_read(UC_X86_REG_RIP)
            report.setdefault("uncapturedMappings",[]).append(dict(
                address=address,accessStart=address,bytes=size,instructionAddress=pc,
                instructionGameRva=pc-base,frame=current_frame[0]+1,
                accessType=access,mappingRejected=True))
            return False  # No live reader, implicit zero page or guessed code.
        mu.hook_add(UC_HOOK_MEM_INVALID,invalid_mapping)

        def outer_input_adapter(uc,address,size,user):
            controls=outer_controls[0]
            if controls is None:return
            # 0x12bce40 is the original scene's seven-argument decoder. Its
            # fifth argument is a typed object descriptor; R8 is the current
            # 28-byte input record. Never write vehicle force/pose fields.
            rsp=uc.reg_read(UC_X86_REG_RSP);mark_access(rsp+0x28,8)
            if fault_reason:return
            descriptor=struct.unpack("<Q",bytes(uc.mem_read(rsp+0x28,8)))[0]
            mark_access(descriptor,16)
            if fault_reason:return
            kind,_,vehicle=struct.unpack("<IIQ",bytes(uc.mem_read(descriptor,16)))
            if kind!=0x0a020000 or vehicle!=metadata["vehicle"]:
                fault_reason.append("Outer input adapter selected object identity differs");uc.emu_stop();return
            current=uc.reg_read(UC_X86_REG_R8);previous=uc.reg_read(UC_X86_REG_RDX)
            mark_access(current,4);mark_access(previous,4)
            if fault_reason:return
            if any(struct.unpack("<I",bytes(uc.mem_read(at,4)))[0]&15!=2 for at in (current,previous)):
                fault_reason.append("Outer input adapter requires the observed type-two record pair");uc.emu_stop();return
            mark_access(current+4,12,writing=True)
            if fault_reason:return
            drive,brake,steering=controls
            uc.mem_write(current+4,struct.pack("<3f",steering,drive,brake))
            outer_action_calls[0]+=1
            report.setdefault("outerSceneInputCommands",[]).append(dict(frame=current_frame[0]+1,
                decoderRva="0x12bce40",recordAddress=hex(current),drive=drive,brake=brake,steering=steering,
                rawKeyboardMappingQualified=False))
        if metadata.get("outerSceneStage") is not None:
            mu.hook_add(UC_HOOK_CODE,outer_input_adapter,begin=base+0x12bce40,end=base+0x12bce40)

        def syscall(uc, user):
            fault_reason.append("OS syscall denied")
            uc.emu_stop()

        mu.hook_add(UC_HOOK_INSN, syscall, None, 1, 0, UC_X86_INS_SYSCALL)
        heap_cursor = [0x800000000]
        heap_allocations = {}

        def import_return(uc, value):
            rsp = uc.reg_read(UC_X86_REG_RSP)
            target = struct.unpack("<Q", bytes(uc.mem_read(rsp, 8)))[0]
            uc.reg_write(UC_X86_REG_RAX, value)
            uc.reg_write(UC_X86_REG_RSP, rsp + 8)
            uc.reg_write(UC_X86_REG_RIP, target)

        def allocate_heap(uc, address, size, user):
            heap = uc.reg_read(UC_X86_REG_RCX)
            flags = uc.reg_read(UC_X86_REG_RDX)
            count = uc.reg_read(UC_X86_REG_R8)
            if (
                count > 4 * 1024 * 1024
                or heap_cursor[0] + max(1, count) + 16 > 0x804000000
            ):
                fault_reason.append("Owned OS allocation model bound exceeded")
                uc.emu_stop()
                return
            at = (heap_cursor[0] + 15) & ~15
            heap_cursor[0] = at + max(1, count)
            heap_allocations[at] = count
            report["modeledOsImports"].append(
                {
                    "trial": trial,
                    "name": "RtlAllocateHeap",
                    "bytes": count,
                    "flags": flags,
                    "result": hex(at),
                }
            )
            import_return(uc, at)

        def free_heap(uc, address, size, user):
            pointer = uc.reg_read(UC_X86_REG_R8)
            if pointer:
                if pointer not in heap_allocations:
                    fault_reason.append(f"Unmodeled source heap free pointer {pointer:#x}")
                    uc.emu_stop()
                    return
                heap_allocations.pop(pointer)
            report["modeledOsImports"].append(
                {
                    "trial": trial,
                    "name": "RtlFreeHeap",
                    "pointer": hex(pointer),
                    "ownedBumpStorageRetainedUntilRunEnds": True,
                }
            )
            import_return(uc, 1)

        def ensure_memory(address, count):
            if count > 4 * 1024 * 1024:
                raise ValueError("Owned platform memory operation bound exceeded")
            for page in range(address & ~4095, (address + count + 4095) & ~4095, 4096):
                if executable_address(page):
                    raise ValueError("Platform ABI write to original code denied")
                if not any(a <= page < a + n for a, n in synthetic):
                    load(page)

        def memory_fill(uc, address, size, user):
            dst = uc.reg_read(UC_X86_REG_RCX)
            value = uc.reg_read(UC_X86_REG_RDX) & 255
            count = uc.reg_read(UC_X86_REG_R8)
            ensure_memory(dst, count)
            mark_access(dst, count,writing=True)
            if fault_reason:return
            uc.mem_write(dst, bytes([value]) * count)
            report["modeledOsImports"].append(
                {"trial": trial, "name": "memset", "bytes": count, "value": value}
            )
            import_return(uc, dst)

        def memory_copy(uc, address, size, user):
            dst = uc.reg_read(UC_X86_REG_RCX)
            src = uc.reg_read(UC_X86_REG_RDX)
            count = uc.reg_read(UC_X86_REG_R8)
            ensure_memory(dst, count)
            ensure_memory(src, count)
            mark_access(src, count)
            mark_access(dst, count,writing=True)
            if fault_reason:return
            uc.mem_write(dst, bytes(uc.mem_read(src, count)))
            report["modeledOsImports"].append(
                {"trial": trial, "name": "memmove", "bytes": count}
            )
            import_return(uc, dst)

        def realloc_heap(uc, address, size, user):
            pointer = uc.reg_read(UC_X86_REG_R8)
            count = uc.reg_read(UC_X86_REG_R9)
            flags = uc.reg_read(UC_X86_REG_RDX)
            if pointer not in heap_allocations:
                fault_reason.append(
                    f"Unmodeled source heap reallocation pointer {pointer:#x}"
                )
                uc.emu_stop()
                return
            previous = heap_allocations[pointer]
            if count <= previous:
                heap_allocations[pointer] = count
                import_return(uc, pointer)
                return
            if flags & 0x10:
                import_return(uc, 0)
                return
            at = (heap_cursor[0] + 15) & ~15
            if count > 4 * 1024 * 1024 or at + count > 0x804000000:
                fault_reason.append("Owned reallocation bound exceeded")
                uc.emu_stop()
                return
            heap_cursor[0] = at + count
            heap_allocations[at] = count
            mark_access(pointer, min(previous, count))
            mark_access(at, min(previous, count),writing=True)
            if fault_reason:return
            uc.mem_write(at, bytes(uc.mem_read(pointer, min(previous, count))))
            heap_allocations.pop(pointer)
            report["modeledOsImports"].append(
                {
                    "trial": trial,
                    "name": "RtlReAllocateHeap",
                    "oldBytes": previous,
                    "newBytes": count,
                }
            )
            import_return(uc, at)

        def size_heap(uc, address, size, user):
            pointer = uc.reg_read(UC_X86_REG_R8)
            if pointer not in heap_allocations:
                fault_reason.append(f"Unmodeled source heap size pointer {pointer:#x}")
                uc.emu_stop()
                return
            import_return(uc, heap_allocations[pointer])

        for name, handler in [
            ("RtlAllocateHeap", allocate_heap),
            ("RtlFreeHeap", free_heap),
            ("RtlReAllocateHeap", realloc_heap),
            ("RtlSizeHeap", size_heap),
            ("memset", memory_fill),
            ("memmove", memory_copy),
            ("memcpy", memory_copy),
        ]:
            at = ntdll_base + export_rvas[name]
            if at in platform_boundaries:
                continue
            platform_boundaries.add(at)
            if compiled_guard is not None:
                require(compiled_guard.platform(compiled_guard.handle,at),"Cannot register platform guard boundary")
            mu.hook_add(UC_HOOK_CODE, handler, begin=at, end=at)

        def platform_counter(uc,address,size,user):
            dst=uc.reg_read(UC_X86_REG_RCX)
            rsp=uc.reg_read(UC_X86_REG_RSP)
            mark_access(rsp,8)
            caller=struct.unpack("<Q",bytes(uc.mem_read(rsp,8)))[0]
            index=counter_cursor[0]
            if counter_transcript is not None:
                if index>=len(counter_transcript):
                    fault_reason.append("Observed platform counter transcript exhausted");uc.emu_stop();return
                row=counter_transcript[index]
                if int(row["returnAddress"],0)!=caller or int(row["outputAddress"],0)!=dst:
                    fault_reason.append(f"Observed platform counter ABI differs at call {index}");uc.emu_stop();return
                value=int(row["counterValue"])
            else:value=int(metadata["externalPlatformModels"][1]["seed"])+index
            counter_cursor[0]+=1
            ensure_memory(dst,8);mark_access(dst,8,writing=True)
            if fault_reason:uc.emu_stop();return
            uc.mem_write(dst,struct.pack("<Q",value))
            report["modeledOsImports"].append(dict(name="QueryPerformanceCounter",counterValue=str(value),
                returnAddress=hex(caller),outputAddress=hex(dst),
                clockSource="observedLiveTranscript" if counter_transcript is not None else "exploratoryHostClock"))
            import_return(uc,1)

        for external in metadata.get("externalPlatformModels", []):
            at = external["address"]
            platform_boundaries.add(at)
            if compiled_guard is not None:
                require(compiled_guard.platform(compiled_guard.handle,at),"Cannot register external guard boundary")
            mu.hook_add(UC_HOOK_CODE, free_heap if external["function"]=="HeapFree" else platform_counter, begin=at, end=at)
        teb = 0x300000000
        for offset, value in (
            (0x30, teb),
            (0x40, 1),
            (0x48, 1),
            (0x58, teb + 0x1000),
            (0x60, teb + 0x3800),
            (0x1000, teb + 0x2000),
            (0x2148, teb + 0x3000),
        ):
            mu.mem_write(teb + offset, struct.pack("<Q", value))
        mu.mem_write(
            teb + 0x2160,
            struct.pack("<4QI", 0x600000000, 0x601000000, 0x600000000, 0x601000000, 0),
        )
        mu.mem_write(0x200000000, struct.pack("<3I", *metadata["timingWords"]))
        rsp = 0x400020000 - 0x108
        mu.mem_write(rsp, struct.pack("<Q", 0x500000000))
        mu.mem_write(rsp + 0x28, struct.pack("<I", 10000))
        for register, value in [
            (UC_X86_REG_RSP, rsp),
            (UC_X86_REG_RCX, manager),
            (UC_X86_REG_RDX, 0x200000000),
            (UC_X86_REG_R8, 10000000000),
            (UC_X86_REG_XMM3, 0x3C23D70B),
            (UC_X86_REG_MXCSR, 0x1F80),
            (UC_X86_REG_GS_BASE, teb),
        ]:
            mu.reg_write(register, value)
        outer=metadata.get("outerSceneStage")
        if outer is not None:
            for name,value in outer["registers"].items():mu.reg_write(globals()["UC_X86_REG_"+name.upper()],int(value,0))
            for index,words in enumerate(outer["xmmWords"]):
                mu.reg_write(globals()["UC_X86_REG_XMM"+str(index)],sum(v<<(32*j) for j,v in enumerate(words)))
            mu.reg_write(UC_X86_REG_GS_BASE,int(outer["teb"],0))
            mu.reg_write(UC_X86_REG_MXCSR,outer["mxcsr"])
            mu.reg_write(UC_X86_REG_EFLAGS,outer["rflags"]&~0x10000)
            rsp=int(outer["stackPointer"],0)
            mu.mem_write(rsp,struct.pack("<Q",0x500000000))

        self.fixture, self.metadata, self.data = f, metadata, data
        self.mu, self.report, self.fault_reason = mu, report, fault_reason
        self.native_guard=compiled_guard
        self.initialize_writes=initialize_writes
        report["previouslyUnknownBytesReadableOnlyAfterFullWrite"]=initialize_writes
        report["coverageGuardImplementation"]="native_cpp_unicorn_hooks" if compiled_guard else "python_unicorn_hooks"
        self.vehicle_selection_inputs=vehicle_selection_inputs
        self.watched_roots, self.integration_intervals = watched_roots, integration_intervals
        self.base, self.manager, self.rsp = base, manager, rsp
        self.code_pages = code_pages
        self.wheel_entry_samples = wheel_entry_samples
        self.vehicle_substep_intervals = vehicle_substep_intervals
        self._current_frame = current_frame
        self._mark_access, self._touched = mark_access, touched
        self._heap_cursor, self._allocations = heap_cursor, heap_allocations
        self._counter_cursor=counter_cursor
        self._outer_controls,self._outer_action_calls=outer_controls,outer_action_calls
        self.counter_transcript=counter_transcript
        self._owner = object()
        self.frame = 0
        self.failed = False
        self.max_steps = metadata["tickCount"] if max_steps is None else max_steps
        require(type(self.max_steps) is int and 1 <= self.max_steps <= 1000,
                "Owned episode horizon outside [1,1000]")
        self._control_pages = {
            page for address, size in CONTROL_REGIONS
            for page in range(address, address+size, 4096)
        }
        self._initial_controls = {page: bytes(mu.mem_read(page,4096))
                                  for page in self._control_pages}
        self._initial_context = mu.context_save()

    def _initial_page(self, page):
        if page in self.data:
            return self.data[page][1]
        return self._initial_controls.get(page, bytes(4096))

    def _sync_native_guard(self):
        if self.native_guard is None:return
        self._touched.update(self.native_guard.touched_pages())
        fault=self.native_guard.fault_info()
        if fault and not self.fault_reason:
            if fault["kind"]==1:
                self.report.setdefault("uncapturedAccesses",[]).append(dict(
                    address=fault["address"],accessStart=fault["start"],bytes=fault["size"],
                    instructionAddress=fault["pc"],instructionGameRva=fault["pc"]-self.base,
                    frame=self.frame+1))
                self.fault_reason.append(f"Access outside captured bytes {fault['address']:#x}; instruction {fault['pc']:#x} (game RVA {fault['pc']-self.base:#x})")
            else:
                self.fault_reason.append(f"Native guard rejected instruction/access at {fault['pc']:#x}; kind {fault['kind']}")

    def _emulate(self,*args,**kwargs):
        require(self.native_guard is None or self.native_guard.handle,
                "Compiled guard has been closed")
        try:
            self.mu.emu_start(*args,**kwargs)
        finally:
            self._sync_native_guard()

    def reset(self):
        self._sync_native_guard()
        for page in self.data.keys() | self._control_pages | self._touched:
            self.mu.mem_write(page, self._initial_page(page))
        self.mu.context_restore(self._initial_context)
        self._heap_cursor[0] = 0x800000000
        self._allocations.clear()
        self._counter_cursor[0]=0
        self._outer_controls[0]=None;self._outer_action_calls[0]=0
        self._touched.clear()
        if self.native_guard is not None:self.native_guard.clear(self.native_guard.handle)
        self.fault_reason.clear()
        self.report["modeledOsImports"].clear()
        self.report.pop("outerSceneInputCommands",None)
        self.report.pop("uncapturedAccesses",None)
        self.report.pop("uncapturedMappings",None)
        self.wheel_entry_samples.clear()
        self.vehicle_substep_intervals.clear()
        self.vehicle_selection_inputs.clear()
        for rva in self.watched_roots:
            self.watched_roots[rva] = 0
        for counts in self.integration_intervals.values():
            counts.clear()
        self.frame, self.failed = 0, False
        return self.observation()

    def save(self):
        require(not self.failed, "Restore or reset after an incomplete step")
        self._sync_native_guard()
        pages = self.data.keys() | self._control_pages | self._touched
        return OwnedCheckpoint(self._owner,
            MappingProxyType({page: bytes(self.mu.mem_read(page,4096)) for page in pages}),
            self.mu.context_save(), self.frame, self._heap_cursor[0],
            MappingProxyType(dict(self._allocations)),
            MappingProxyType(self.native_guard.save_initialized()) if self.native_guard else None,
            self._counter_cursor[0])

    def restore(self, checkpoint):
        require(isinstance(checkpoint, OwnedCheckpoint) and checkpoint.owner is self._owner,
                "Checkpoint belongs to a different owned machine")
        self._sync_native_guard()
        pages = self.data.keys() | self._control_pages | self._touched | checkpoint.pages.keys()
        for page in pages:
            self.mu.mem_write(page, checkpoint.pages.get(page, self._initial_page(page)))
        self.mu.context_restore(checkpoint.context)
        self._heap_cursor[0] = checkpoint.heap_cursor
        self._allocations.clear()
        self._allocations.update(checkpoint.allocations)
        self._counter_cursor[0]=checkpoint.counter_cursor
        self._touched.clear()
        self._touched.update(checkpoint.pages.keys() - self.data.keys() - self._control_pages)
        if self.native_guard is not None:self.native_guard.clear(self.native_guard.handle)
        if self.native_guard is not None and checkpoint.initialized_pages is not None:
            self.native_guard.restore_initialized(checkpoint.initialized_pages)
        self.fault_reason.clear()
        self.frame, self.failed = checkpoint.frame, False
        self.report.pop("uncapturedAccesses",None)
        self.report.pop("uncapturedMappings",None)
        return self.observation()

    def trace_frame(self):
        parts, mask_at = [], 0
        for out in self.metadata["trace"]["outputs"]:
            part, at = bytearray(out["bytes"]), 0
            while at < len(part):
                address = out["address"] + at
                count = min(4096 - (address & 4095), len(part) - at)
                if any(self.fixture.trace_mask[mask_at+at:mask_at+at+count]):
                    part[at:at+count] = self.mu.mem_read(address,count)
                at += count
            mask_at += len(part)
            parts.append(part)
        return b"".join(parts)

    def observation(self):
        require(not self.failed, "No observation after an incomplete step")
        address = self.metadata["stateAddress"] + self.metadata["selectedBodyIndex"]*88
        raw = bytes(self.mu.mem_read(address,88))
        if not all(math.isfinite(v) for v in struct.unpack("<22f",raw)):
            self.failed=True
            raise UncapturedStepError("Original step produced nonfinite rigid state")
        return dict(tick=self.frame, timeSeconds=self.frame*0.01,
                    position=list(struct.unpack_from("<3f",raw,0x24)),
                    quaternionWxyz=list(struct.unpack_from("<4f",raw,0x30)),
                    linearVelocity=list(struct.unpack_from("<3f",raw,0x40)),
                    angularVelocity=list(struct.unpack_from("<3f",raw,0x4c)),
                    rigidStateSha256=hashlib.sha256(raw).hexdigest(),
                    sparseInputCoverageGuarded=True, fullSimulatorQualified=False)

    def step(self, controls=None, action_axis=None, steering_offset=0xa0):
        require(not self.failed, "Restore or reset after an incomplete step")
        require(self.frame < self.max_steps, "Owned episode horizon reached")
        outer=self.metadata.get("outerSceneStage")
        require(outer is None or action_axis is None,
                "Outer-scene action-axis override is not identified")
        require(steering_offset in (0xa0,0x1430), "Unsupported steering command field")
        if controls is not None:
            require(isinstance(controls,(list,tuple)) and len(controls)==3
                    and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=1 for v in controls),
                    "Controls require a finite [-1,1] triple")
            require(outer is None or (0<=controls[0]<=1 and 0<=controls[1]<=1),
                    "Decoded outer-scene pedal scalars require [0,1]")
        require(action_axis is None or (type(action_axis) in (int,float)
                and math.isfinite(action_axis) and abs(action_axis)<=1), "Invalid action axis")
        self._current_frame[0]=self.frame
        self._outer_controls[0]=tuple(controls) if outer is not None and controls is not None else None
        self._outer_action_calls[0]=0
        try:
            if self.native_guard is not None:self.native_guard.sync_masks(self.data)
            if controls is not None and outer is None:
                for offset,value in zip((0x98,0x9c,steering_offset),controls):
                    address=self.metadata["vehicle"]+offset
                    self._mark_access(address,4,writing=True)
                    if self.fault_reason:
                        raise UncapturedStepError(self.fault_reason[-1])
                    self.mu.mem_write(address,struct.pack("<f",value))
            if action_axis is not None:
                address=self.metadata["vehicle"]+0x1374
                self._mark_access(address,4,writing=True)
                if self.fault_reason:
                    raise UncapturedStepError(self.fault_reason[-1])
                self.mu.mem_write(address,struct.pack("<f",action_axis))
            self.mu.mem_write(0x200000000,struct.pack("<3I",
                self.metadata["timingWords"][0]+self.frame*10,10,0x3c23d70b))
            self.mu.mem_write(self.rsp,struct.pack("<Q",0x500000000))
            if outer is not None:
                for register,value in ((UC_X86_REG_RSP,self.rsp),(UC_X86_REG_RCX,int(outer["scene"],0)),
                    (UC_X86_REG_RDX,self.metadata["timingWords"][0]+self.frame*10),(UC_X86_REG_R8,10),(UC_X86_REG_R9,0)):
                    self.mu.reg_write(register,value)
                self._emulate(self.base+0x12e9ea0,0x500000000,count=10000000)
                if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                    raise UncapturedStepError("; ".join(self.fault_reason) or "Original outer scene did not return")
                if controls is not None and self._outer_action_calls[0]!=1:
                    raise UncapturedStepError("Original outer scene did not consume exactly one selected input command")
                self.frame+=1
                return self.trace_frame()
            for register,value in ((UC_X86_REG_RSP,self.rsp),(UC_X86_REG_RCX,self.manager),
                                   (UC_X86_REG_RDX,0x200000000)):
                self.mu.reg_write(register,value)
            pipeline=self.metadata.get("postStepPipeline")
            if pipeline is not None and pipeline["version"]>=2:
                if pipeline["version"]==4:
                    for entry in (0x2a6360,0x2a6960):
                        self.mu.reg_write(UC_X86_REG_RCX,pipeline["collisionWorld"])
                        self._emulate(self.base+entry,0x500000000,count=2000000)
                        if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                            raise UncapturedStepError("; ".join(self.fault_reason) or "Collision query preparation did not return")
                        self.mu.mem_write(self.rsp,struct.pack("<Q",0x500000000))
                        self.mu.reg_write(UC_X86_REG_RSP,self.rsp)
                    self.mu.reg_write(UC_X86_REG_RDX,0x200000000)
                self.mu.reg_write(UC_X86_REG_RCX,pipeline["registeredForceContext"])
                self._emulate(self.base+0x1501f00,0x500000000,count=2000000)
                if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                    raise UncapturedStepError("; ".join(self.fault_reason) or "Vehicle pre-step did not return")
                self.mu.mem_write(self.rsp,struct.pack("<Q",0x500000000))
                for register,value in ((UC_X86_REG_RSP,self.rsp),(UC_X86_REG_RCX,self.manager),
                                       (UC_X86_REG_RDX,0x200000000)):
                    self.mu.reg_write(register,value)
            self._emulate(self.base+0x7bd0e0,0x500000000,count=2000000)
            if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                raise UncapturedStepError("; ".join(self.fault_reason) or "Original step did not return")
            pipeline=self.metadata.get("postStepPipeline")
            if pipeline is not None:
                for entry,receiver,second in ((0x2a9b50,pipeline["collisionWorld"],None),
                        (0x7bfcb0,self.manager,None),
                        (0x7d2b90,pipeline["registeredForceContext"],0x200000000)):
                    self.mu.mem_write(self.rsp,struct.pack("<Q",0x500000000))
                    self.mu.reg_write(UC_X86_REG_RSP,self.rsp)
                    self.mu.reg_write(UC_X86_REG_RCX,receiver)
                    if second is not None:self.mu.reg_write(UC_X86_REG_RDX,second)
                    self._emulate(self.base+entry,0x500000000,count=2000000)
                    if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                        raise UncapturedStepError("; ".join(self.fault_reason) or "Scene contact procedure did not return")
                if pipeline["version"]>=2:
                    self.mu.mem_write(self.rsp,struct.pack("<Q",0x500000000))
                    for register,value in ((UC_X86_REG_RSP,self.rsp),
                            (UC_X86_REG_RCX,pipeline["registeredForceContext"]),(UC_X86_REG_RDX,self.manager),
                            (UC_X86_REG_R8,self.metadata["timingWords"][0]+self.frame*10),
                            (UC_X86_REG_XMM3,0x3c23d70b)):
                        self.mu.reg_write(register,value)
                    self._emulate(self.base+0x1501f50,0x500000000,count=2000000)
                    if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                        raise UncapturedStepError("; ".join(self.fault_reason) or "Vehicle post-step did not return")
                    if pipeline["version"]>=3:
                        self.mu.mem_write(self.rsp,struct.pack("<Q",0x500000000))
                        self.mu.reg_write(UC_X86_REG_RSP,self.rsp)
                        self.mu.reg_write(UC_X86_REG_RCX,pipeline["registeredForceContext"])
                        self._emulate(self.base+0x7d2cf0,0x500000000,count=2000000)
                        if self.fault_reason or self.mu.reg_read(UC_X86_REG_RIP)!=0x500000000:
                            raise UncapturedStepError("; ".join(self.fault_reason) or "Vehicle pose synchronization did not return")
        except (UcError,UncapturedStepError,ValueError) as exc:
            self.failed=True
            raise UncapturedStepError(str(exc)) from exc
        self.frame+=1
        return self.trace_frame()
