"""Capture sparse numeric inputs and references for complete original main steps.

Game process access is read-only. Execution takes place in a private emulator.
Windows heap/memory APIs are supplied by an explicit owned platform adapter.
The fixture is a bounded reference, not a complete autonomous game simulator.
"""

import argparse
import sys, ctypes as C, hashlib, json, struct, time, math, pefile
from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path
from reverse_physics import SHA, ROOT
from pe_unwind import PeCode
from original_step_fixture import load_original_step_fixture, verify_original_step_images

sys.path.insert(0, str(ROOT / "tools/physics-python"))
from unicorn import *
from unicorn.x86_const import *


def capture(args):
    exe = args.exe
    outer_stage_path=getattr(args,"outer_scene_stage",None)
    outer_stage=json.loads(outer_stage_path.read_text()) if outer_stage_path is not None else None
    outer_controls=getattr(args,"outer_scene_controls",None)
    scenario_path=getattr(args,"outer_scene_scenarios",None)
    outer_scenarios=json.loads(scenario_path.read_text()) if scenario_path else None
    if outer_scenarios is not None:
        if not (outer_stage and outer_controls is None and getattr(args,"native_capture",None)
                and isinstance(outer_scenarios,dict) and 1<=len(outer_scenarios)<=2
                and args.steps*(1+len(outer_scenarios))<=150):
            raise ValueError("Stopped scenario discovery requires a bounded native capture cohort")
        for name,plan in outer_scenarios.items():
            if not (name.isascii() and name.isidentifier() and name!="observed" and len(name)<=32
                and isinstance(plan,list) and len(plan)==args.steps and all(isinstance(row,list) and len(row)==3
                    and all(type(v) in (int,float) and math.isfinite(v) for v in row)
                    and 0<=row[0]<=1 and 0<=row[1]<=1 and abs(row[2])<=1 for row in plan)):
                raise ValueError("Malformed scene decoder scenario schedule")
    if outer_controls is not None:
        if not outer_stage or not (all(math.isfinite(v) for v in outer_controls)
            and 0<=outer_controls[0]<=1 and 0<=outer_controls[1]<=1 and abs(outer_controls[2])<=1):
            raise ValueError("Scene decoder controls require a stopped outer scene and normalized pedals/steering")
    initial_tick=10000
    if outer_stage is not None:
        if not (args.source_binding and args.active_only and not args.initial_fixture
                and not args.vehicle_scene_pipeline and not args.post_contact_dispatch
                and not args.control_schedule and getattr(args,"snapshot_observer_pid",None)
                and getattr(args,"snapshot_release_event",None)):
            raise ValueError("Outer scene requires a fresh stopped snapshot lease and no constructed sub-pipeline/control plan")
        if not 1<=args.steps<=100:raise ValueError("Stopped outer-scene discovery is bounded to 100 ticks")
        if args.steps>5 and not getattr(args,"native_capture",None):raise ValueError("Long stopped captures require the compiled discovery recorder")
        if not (outer_stage.get("schema")=="tm2020_stopped_scene_snapshot_lease_v1"
                and outer_stage.get("gameThreadsStopped") is True
                and outer_stage.get("executableSha256")==SHA
                and outer_stage.get("entryRva")=="0x12e9ea0"
                and outer_stage.get("intervalWord")==10 and outer_stage.get("modeWord")==0
                and int(outer_stage.get("fifthArgument","-1"),0)==0
                and outer_stage.get("sixthArgumentByte")==254
                and outer_stage.get("gameTlsLayoutQualified") is True):
            raise ValueError("Unverified outer scene ABI or unsupported nonzero-input mode")
        initial_tick=outer_stage["clockWord"]
    if args.post_contact_dispatch and args.vehicle_scene_pipeline:
        raise ValueError("Choose one owned scene-continuation experiment")
    if args.vehicle_pose_sync and not args.vehicle_scene_pipeline:
        raise ValueError("Vehicle pose synchronization requires the scene pipeline")
    if args.collision_query_cycle and not args.vehicle_pose_sync:
        raise ValueError("Collision query lifecycle requires synchronized vehicle-scene stepping")
    if args.source_body_activation and not (args.vehicle_scene_pipeline and args.active_only):
        raise ValueError("Source activation requires one owned vehicle-scene trial")
    if args.normalize_initial_controls and not (args.initial_fixture and args.control_schedule):
        raise ValueError("Normalized initial controls require a seed and a control schedule")
    if args.preserve_source_velocity and not (args.source_body_activation and args.active_only):
        raise ValueError("Preserved source velocity requires the observed source vehicle path")
    schedule = None
    if args.control_schedule is not None:
        schedule=json.loads(args.control_schedule.read_text())
        if not (isinstance(schedule,list) and len(schedule)==args.steps
                and all(isinstance(row,list) and len(row)==3
                        and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=1
                                for v in row) for row in schedule)):
            raise ValueError("Control schedule requires one finite [-1,1] triple per captured tick")
    active_trial = "owned_control_schedule" if schedule is not None else "owned_throttle_straight"
    args.output.mkdir(parents=True, exist_ok=True)
    for name in ("captured", active_trial):
        if (args.output / (name + ".tmstep")).exists():
            raise FileExistsError("Capture never overwrites a fixture")
    if args.report.exists():
        raise FileExistsError("Capture never overwrites its report")
    if args.source_binding is not None:
        if args.manifest is not None:
            raise ValueError("Choose a pose manifest or a typed binding report")
        binding=json.loads(args.source_binding.read_text())
        if not (binding.get("schema")=="tm2020_readonly_physics_binding_v1"
                and binding.get("executableSha256")==SHA and binding.get("readOnly") is True
                and 0<=args.candidate_index<len(binding["candidates"])):
            raise ValueError("Invalid current-build typed binding report")
        selected=binding["candidates"][args.candidate_index]
        if selected.get("typedBacklinksRechecked") is not True:
            raise ValueError("Typed binding was not rechecked")
        manifest=["TM2020_POSE_CANDIDATES_V3",str(binding["pid"]),
                  binding["processCreationFiletime"],SHA]
        reported_base=int(binding["moduleBase"],0)
        reported_manager=int(selected["manager"],0)
        if ((args.module_base is not None and args.module_base!=reported_base)
                or (args.manager is not None and args.manager!=reported_manager)):
            raise ValueError("Explicit address differs from typed discovery")
        base,manager=reported_base,reported_manager
    else:
        if args.manifest is None or args.module_base is None or args.manager is None:
            raise ValueError("Provide a binding report or a current manifest with module and manager addresses")
        manifest = args.manifest.read_text().splitlines()
        if not (len(manifest)>=4 and manifest[0]=="TM2020_POSE_CANDIDATES_V3" and manifest[3]==SHA):
            raise ValueError("Invalid current-build manifest")
        base,manager=args.module_base,args.manager
    if hashlib.sha256(exe.read_bytes()).hexdigest() != SHA:
        raise ValueError("Unknown executable build")
    pid = int(manifest[1])
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
    observer=None;release=None
    if outer_stage is not None:
        k.OpenEventW.argtypes=[C.c_uint32,C.c_int,C.c_wchar_p];k.OpenEventW.restype=C.c_void_p
        k.WaitForSingleObject.argtypes=[C.c_void_p,C.c_uint32];k.WaitForSingleObject.restype=C.c_uint32
        k.GetTickCount64.restype=C.c_uint64
        observer=k.OpenProcess(0x100000,False,args.snapshot_observer_pid)
        release=k.OpenEventW(0x100000,False,args.snapshot_release_event)
        if not observer or not release:raise ValueError("Cannot verify source snapshot lease handles")
        if not (outer_stage["pid"]==pid and outer_stage["processCreationFiletime"]==manifest[2]
                and int(outer_stage["moduleBase"],0)==base):raise ValueError("Stopped stage belongs to another source process")
    def lease():
        if outer_stage is not None and not (
            k.WaitForSingleObject(observer,0)==258 and k.WaitForSingleObject(release,0)==258
            and k.GetTickCount64()+100<outer_stage["leaseExpiresGetTickCount64"]):
            raise ValueError("Stopped source snapshot lease ended; no live fallback is permitted")
    h = k.OpenProcess(0x1010, False, pid)
    if not h:
        raise OSError(C.get_last_error())
    try:

        def identity():
            lease()
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
            lease()
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
            raise ValueError("Unexpected loaded PE headers")
        text_section = next(s for s in pe.sections if s.Name.rstrip(b"\0") == b".text")
        code_start = base + text_section.VirtualAddress
        code_end = code_start + text_section.Misc_VirtualSize
        executable_ranges = [
            (base + s.VirtualAddress, base + s.VirtualAddress + s.Misc_VirtualSize)
            for s in pe.sections
            if s.Characteristics & 0x20000000
        ]
        ntdll = C.WinDLL("ntdll")
        ntdll_base = ntdll._handle
        ntdll_file = Path(r"C:\Windows\System32\ntdll.dll")
        ntdll_pe = pefile.PE(str(ntdll_file), fast_load=True)
        ntdll_sha = hashlib.sha256(ntdll_file.read_bytes()).hexdigest()
        executable_ranges.extend(
            (
                ntdll_base + x.VirtualAddress,
                ntdll_base + x.VirtualAddress + x.Misc_VirtualSize,
            )
            for x in ntdll_pe.sections
            if x.Characteristics & 0x20000000
        )

        def executable_address(address):
            return any(a <= address < b for a, b in executable_ranges)

        kernel32 = C.WinDLL("kernel32")
        heap_free_api = C.cast(kernel32.HeapFree, C.c_void_p).value
        counter_api=C.cast(kernel32.QueryPerformanceCounter,C.c_void_p).value if outer_stage else None
        if outer_stage and counter_api!=int(outer_stage["queryPerformanceCounterAddress"],0):
            raise ValueError("Observed source platform counter address differs")
        external_apis={heap_free_api}|({counter_api} if counter_api else set())
        kernel32_sha = hashlib.sha256(
            Path(r"C:\Windows\System32\kernel32.dll").read_bytes()
        ).hexdigest()

        def source_code(address):
            if (
                ntdll_base
                <= address
                < ntdll_base + ntdll_pe.OPTIONAL_HEADER.SizeOfImage
            ):
                return ntdll_pe, ntdll_base
            return pe, base

        items = u64(manager + 0x20)
        users = u64(manager + 0x40)
        ids = u64(manager + 0xB0)
        index = selected["bodyIndex"] if args.source_binding is not None else u32(ids)
        if not all(
            index < u32(manager + off + 8)
            for off in (0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80)
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
            raise ValueError("Force callback/body binding mismatch")
        configuration=u64(vehicle+0x88)
        collision_world=u64(manager)
        if u64(owner+0x108)!=collision_world:
            raise ValueError("Collision world and registered force-context backlink differ")
        source_model=u64(u64(manager+0x10)+index*8)
        source_flags_address=u64(manager+0x30)+index
        source_activation=dict(modelWord50=u32(source_model+0x50),
            sourceFlags=read(source_flags_address,1)[0],modelAddress=source_model,
            sourceFlagsAddress=source_flags_address)
        if outer_stage is not None:
            scene=int(outer_stage["scene"],0)
            discovered=binding.get("sceneRegistryDiscovery",{})
            matches=[r for r in discovered.get("sceneRoots",[]) if int(r["address"],0)==scene and r["bindingIndex"]==args.candidate_index]
            if len(matches)!=1 or u64(scene+0x7c8)!=int(matches[0]["registry"],0):
                raise ValueError("Stopped outer scene differs from typed registry discovery")
        if args.source_binding is not None and not (
            vehicle==int(selected["vehicle"],0)
            and configuration==int(selected["configuration"],0)
            and u64(manager+0x70)+index*88==int(selected["rigidState"],0)
            and index==selected["bodyIndex"] and item_id==selected["itemId"]
        ):
            raise ValueError("Typed discovery binding changed before capture")
        seed=None
        if args.initial_fixture is not None:
            seed=load_original_step_fixture(args.initial_fixture)
            verify_original_step_images(seed,(exe,ntdll_file,Path(r"C:\Windows\System32\kernel32.dll")))
            sm=seed.metadata
            if not (sm.get("sourcePid")==pid and sm.get("sourceProcessCreationFiletime")==manifest[2]
                    and sm["modules"][0]["base"]==base and sm["modules"][1]["base"]==ntdll_base
                    and sm["manager"]==manager and sm["vehicle"]==vehicle
                    and sm.get("configuration")==configuration and sm["selectedBodyIndex"]==index
                    and sm["stateAddress"]==u64(manager+0x70)
                    and sm["externalPlatformModels"][0]["address"]==heap_free_api):
                raise ValueError("Snapshot seed is from another process, binding or platform cohort")
            if not args.active_only:
                raise ValueError("A retained initial state may seed only an owned active trial")
            if args.preserve_source_velocity and sm.get("sourceVelocityPreserved") is not True:
                raise ValueError("A forced-velocity fixture cannot seed a preserved source-velocity capture")
        force_address = u64(manager + 0xA0) + index * 24
        report = {
            "schema": "tm2020_owned_live_backed_main_step_prototype_v1",
            "sha256": SHA,
            "pid": pid,
            "readOnlyProcessHandle": True,
            "gameMemoryWritten": False,
            "codeExecutedInGame": False,
            "rawHeapPagesPersisted": False,
            "sparseAccessedDataBytesPersisted": True,
            "sourceCodeBytesPersisted": False,
            "sourceBindingRecheckedAfterCapture": False,
            "atomicSnapshot": False,
            "completePhysics": False,
            "allocationRequests": [],
            "ntdllSha256": ntdll_sha,
            "allNonordinaryExecutedInstructionsCheckedAgainstDisk": True,
            "systemCallsExecuted": False,
            "modeledOsImports": [],
            "wholeStepInstructionOracleQualified": False,
            "ownedWorkerCount": 0,
            "ownedConditionVariableInitiallyEmpty": True,
            "controlledInputScheduleProvided": schedule is not None,
            "rawPlayerActionMappingQualified": False,
            "initialSnapshotSeedFixtureSha256": seed.sha256 if seed is not None else None,
            "selectedPostContactDispatchEnabled": args.post_contact_dispatch,
            "selectedVehicleScenePipelineEnabled": args.vehicle_scene_pipeline,
            "selectedVehiclePoseSyncEnabled": args.vehicle_pose_sync,
            "selectedCollisionQueryCycleEnabled": args.collision_query_cycle,
            "sourceBodyActivationRestored": args.source_body_activation,
            "sourceVelocityPreserved":args.preserve_source_velocity,
            "observedSourceBodyActivation": source_activation,
            "newlyAccessedInputsReadFromCurrentSource": seed is not None,
            "trials": [],
        }
        try:
            trials = [
                ("captured", None),
                (active_trial, 1.0),
            ]
            if args.active_only:trials=trials[1:]
            if outer_stage is not None:trials=[("outer_scene_observed",None)]
            if outer_scenarios is not None:trials += [("outer_scene_"+name,None) for name in outer_scenarios]
            for trial, throttle in trials:
                outer_plan=outer_scenarios[trial.removeprefix("outer_scene_")] if outer_scenarios and trial!="outer_scene_observed" else None
                phase = [False]
                data_masks = {}
                code_reads = {}
                executed_masks = {}
                initial_data = {}
                loaded_code = {}
                mu = Uc(UC_ARCH_X86, UC_MODE_64)
                recorder=None
                if getattr(args,"native_capture",None):
                    from owned_native_capture import NativeCapture
                    recorder=NativeCapture(mu,args.native_capture)
                platform_boundaries = set()
                pages = set()
                coverage = set()
                blocks = []
                writes = set()
                initial = {}
                fault_reason = []
                fetch_count = [0]
                write_pages = set()
                synthetic = [
                    (0x200000000, 0x10000),
                    (0x300000000, 0x4000),
                    (0x400000000, 0x20000),
                    (0x500000000, 0x1000),
                    (0x600000000, 0x1000000),
                    (0x700000000, 0x4000000),
                    (0x800000000, 0x4000000),
                ]
                for address, size in synthetic:
                    mu.mem_map(address, size)
                if seed is not None:
                    for address,page in seed.pages.items():
                        if any(a<=address and address+4096<=a+n for a,n in synthetic):
                            mu.mem_write(address,page.initial)
                teb = 0x300000000
                mu.mem_write(teb + 0x60, struct.pack("<Q", teb + 0x3800))
                mu.mem_write(teb + 0x30, struct.pack("<Q", teb))
                mu.mem_write(teb + 0x40, struct.pack("<2Q", 1, 1))
                mu.mem_write(teb + 0x58, struct.pack("<Q", teb + 0x1000))
                mu.mem_write(teb + 0x1000, struct.pack("<Q", teb + 0x2000))
                mu.reg_write(UC_X86_REG_GS_BASE, teb)
                mu.mem_write(
                    teb + 0x2000 + 0x160,
                    struct.pack(
                        "<4QI", 0x600000000, 0x601000000, 0x600000000, 0x601000000, 0
                    ),
                )
                mu.mem_write(
                    teb + 0x2000 + 0x148, struct.pack("<Q", teb + 0x3000)
                )  # Owned TLS thread-context object; raw word +0x14 remains zero.

                def load(page, execute=False):
                    if page in pages:
                        return
                    if page in {at & ~4095 for at in external_apis}:
                        mu.mem_map(page, 4096)
                        mu.mem_write(page, b"\xcc" * 4096)
                        mu.mem_protect(page, 4096, UC_PROT_READ | UC_PROT_EXEC)
                        pages.add(page)
                        return
                    if len(pages) >= 16384:
                        raise ValueError("64 MiB ephemeral source-page bound reached")
                    if execute and not executable_address(page):
                        raise ValueError(
                            f"External/nonordinary code execution denied at {page:#x}"
                        )
                    data = read(page, 4096)
                    is_code = executable_address(page)
                    if seed is not None and page in seed.pages:
                        retained=seed.pages[page]
                        data=bytes(old if observed else live
                                   for observed,old,live in zip(retained.mask,retained.initial,data))
                    if is_code:
                        source_pe, source_base = source_code(page)
                        expected = source_pe.get_data(page - source_base, 4096)
                        if data != expected and code_start <= page < code_end:
                            raise ValueError(
                                f"Ordinary .text code differs from pinned original at RVA {page-base:#x}"
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
                    if is_code:
                        loaded_code[page] = (data, expected)
                        if recorder is not None:recorder.add_code(page,expected)
                    else:
                        initial_data[page] = data

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
                excluded = [
                    (0x200000000, 0x10000),
                    (0x300000000, 0x4000),
                    (0x400000000, 0x20000),
                    (0x500000000, 0x1000),
                ]

                def mark_access(address, size):
                    if not phase[0]:
                        return
                    for at in range(address, address + size):
                        if any(a <= at < a + n for a, n in excluded):
                            continue
                        page = at & ~4095
                        if executable_address(at):
                            code_reads.setdefault(page, bytearray(4096))[at - page] = 1
                            continue
                        data_masks.setdefault(page, bytearray(4096))[at - page] = 1
                        if page not in initial_data and any(
                            a <= page < a + n for a, n in synthetic
                        ):
                            initial_data[page] = bytes(mu.mem_read(page, 4096))

                def data_read(uc, access, address, size, value, user):
                    mark_access(address, size)

                if recorder is None:mu.hook_add(UC_HOOK_MEM_READ, data_read)

                def block(uc, address, size, user):
                    if address in external_apis:
                        return
                    if not executable_address(address):
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

                def instruction_guard(uc, address, size, user):
                    if address in platform_boundaries:
                        return  # Imported platform ABI is modeled, never executed.
                    if phase[0] and 0 < size <= 15:
                        for at in range(address, address + size):
                            executed_masks.setdefault(at & ~4095, bytearray(4096))[
                                at & 4095
                            ] = 1
                    if code_start <= address < code_end:
                        return
                    if size < 1 or size > 15:
                        fault_reason.append(f"Unsupported instruction at {address:#x}")
                        uc.emu_stop()
                        return
                    source_pe, source_base = source_code(address)
                    if not executable_address(address) or bytes(
                        uc.mem_read(address, size)
                    ) != source_pe.get_data(address - source_base, size):
                        fault_reason.append(
                            f"Executed instruction differs from pinned file RVA {address-base:#x}"
                        )
                        uc.emu_stop()

                if recorder is None:mu.hook_add(UC_HOOK_CODE, instruction_guard)

                def system_call_guard(uc, user):
                    fault_reason.append(
                        f"OS syscall reached at {uc.reg_read(UC_X86_REG_RIP):#x}"
                    )
                    uc.emu_stop()

                mu.hook_add(
                    UC_HOOK_INSN, system_call_guard, None, 1, 0, UC_X86_INS_SYSCALL
                )
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
                        raise ValueError(
                            "Owned platform memory operation bound exceeded"
                        )
                    for page in range(
                        address & ~4095, (address + count + 4095) & ~4095, 4096
                    ):
                        if executable_address(page):
                            raise ValueError(
                                "Platform ABI write to original code denied"
                            )
                        if not any(a <= page < a + n for a, n in synthetic):
                            load(page)

                def memory_fill(uc, address, size, user):
                    dst = uc.reg_read(UC_X86_REG_RCX)
                    value = uc.reg_read(UC_X86_REG_RDX) & 255
                    count = uc.reg_read(UC_X86_REG_R8)
                    ensure_memory(dst, count)
                    mark_access(dst, count)
                    uc.mem_write(dst, bytes([value]) * count)
                    report["modeledOsImports"].append(
                        {
                            "trial": trial,
                            "name": "memset",
                            "bytes": count,
                            "value": value,
                        }
                    )
                    import_return(uc, dst)

                def memory_copy(uc, address, size, user):
                    dst = uc.reg_read(UC_X86_REG_RCX)
                    src = uc.reg_read(UC_X86_REG_RDX)
                    count = uc.reg_read(UC_X86_REG_R8)
                    ensure_memory(dst, count)
                    ensure_memory(src, count)
                    mark_access(src, count)
                    mark_access(dst, count)
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
                    mark_access(at, min(previous, count))
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
                        fault_reason.append(
                            f"Unmodeled source heap size pointer {pointer:#x}"
                        )
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
                    at = C.cast(getattr(ntdll, name), C.c_void_p).value
                    if at in platform_boundaries:
                        continue
                    platform_boundaries.add(at)
                    mu.hook_add(UC_HOOK_CODE, handler, begin=at, end=at)
                platform_boundaries.add(heap_free_api)
                mu.hook_add(
                    UC_HOOK_CODE, free_heap, begin=heap_free_api, end=heap_free_api
                )
                if outer_stage:
                    # Discovery only. A recorded live transcript must replace
                    # these declared exploratory values during independent
                    # replay; this capture does not qualify a physical match.
                    counter_index=[0]
                    def exploratory_counter(uc,address,size,user):
                        dst=uc.reg_read(UC_X86_REG_RCX)
                        counter_rsp=uc.reg_read(UC_X86_REG_RSP)
                        mark_access(counter_rsp,8);mark_access(counter_rsp+0x30,8)
                        caller=struct.unpack("<Q",own_read(counter_rsp,8))[0]
                        wrapper_caller=struct.unpack("<Q",own_read(counter_rsp+0x30,8))[0]
                        ensure_memory(dst,8);mark_access(dst,8)
                        value=int(outer_stage["explorationCounterSeed"])+counter_index[0]
                        counter_index[0]+=1
                        uc.mem_write(dst,struct.pack("<Q",value))
                        report["modeledOsImports"].append(dict(trial=trial,name="QueryPerformanceCounter",
                            counterValue=str(value),exploratoryOnly=True,returnAddress=hex(caller),
                            clockWrapperReturnAddress=hex(wrapper_caller),outputAddress=hex(dst)))
                        import_return(uc,1)
                    platform_boundaries.add(counter_api)
                    mu.hook_add(UC_HOOK_CODE,exploratory_counter,begin=counter_api,end=counter_api)

                def allocation(uc, address, size, user):
                    pointer = uc.reg_read(UC_X86_REG_RCX)
                    raw = bytes(uc.mem_read(pointer, 16))
                    report["allocationRequests"].append(
                        {
                            "trial": trial,
                            "vector": hex(pointer),
                            "offsetFromManager": hex(pointer - manager),
                            "oldDataCountCapacity": list(struct.unpack("<QII", raw)),
                            "requestedCount": uc.reg_read(UC_X86_REG_RDX),
                            "returnAddress": hex(
                                struct.unpack(
                                    "<Q",
                                    bytes(uc.mem_read(uc.reg_read(UC_X86_REG_RSP), 8)),
                                )[0]
                                - base
                            ),
                        }
                    )

                mu.hook_add(
                    UC_HOOK_CODE, allocation, begin=base + 0x4D8C10, end=base + 0x4D8C10
                )

                def owned_write(uc, access, address, size, value, user):
                    mark_access(address, size)
                    if not any(
                        start <= address < start + extent for start, extent in synthetic
                    ):
                        write_pages.add(address & ~4095)

                if recorder is None:mu.hook_add(UC_HOOK_MEM_WRITE, owned_write)

                def own_read(address, size):
                    for page in range(
                        address & ~4095, (address + size + 4095) & ~4095, 4096
                    ):
                        load(page)
                    return bytes(mu.mem_read(address, size))

                def own_write(address, data):
                    own_read(address, len(data))
                    mu.mem_write(address, data)

                def scene_input_command(uc,address,size,user):
                    controls=outer_plan[frame] if outer_plan is not None else outer_controls
                    if controls is None:return
                    at=uc.reg_read(UC_X86_REG_RSP)+0x28;mark_access(at,8)
                    descriptor=struct.unpack("<Q",own_read(at,8))[0];mark_access(descriptor,16)
                    kind,_,selected_vehicle=struct.unpack("<IIQ",own_read(descriptor,16))
                    current=uc.reg_read(UC_X86_REG_R8);previous=uc.reg_read(UC_X86_REG_RDX)
                    mark_access(current,4);mark_access(previous,4)
                    if kind!=0x0a020000 or selected_vehicle!=vehicle or any(
                        struct.unpack("<I",own_read(pointer,4))[0]&15!=2 for pointer in (current,previous)):
                        fault_reason.append("Original scene input descriptor/type differs");uc.emu_stop();return
                    mark_access(current+4,12)
                    drive,brake,steering=controls
                    own_write(current+4,struct.pack("<3f",steering,drive,brake))
                    report.setdefault("outerSceneInputCommands",[]).append(dict(trial=trial,frame=frame+1,
                        decoderRva="0x12bce40",recordAddress=hex(current),drive=drive,brake=brake,steering=steering))
                if outer_controls is not None or outer_plan is not None:
                    mu.hook_add(UC_HOOK_CODE,scene_input_command,begin=base+0x12bce40,end=base+0x12bce40)

                before = own_read(vehicle, 0x1D00)
                forces_before = own_read(force_address, 24)
                own_write(
                    base + 0x2096AF8, struct.pack("<I", 0)
                )  # Owned runtime: zero worker threads.
                own_write(
                    base + 0x2096B08, struct.pack("<Q", 0)
                )  # Owned condition variable has no foreign waiters.
                own_write(
                    ntdll_base + 0x1D47E0, struct.pack("<I", 2)
                )  # Original RDTSCP processor-ID dispatch, supported by the owned emulator.
                own_write(
                    base + 0x1E64078, struct.pack("<I", 0)
                )  # Owned CRT __isa_available: original SSE memcpy path.
                for slot in range(64):
                    own_write(
                        manager + 0x14B0 + slot * 0x48,
                        struct.pack("<QII", 0x700000000 + slot * 0x100000, 0, initial_tick),
                    )
                if throttle is not None:
                    own_write(vehicle + 0x98, struct.pack("<2f", throttle, 0))
                    own_write(vehicle + 0x1430, struct.pack("<f", 0))
                    if schedule is not None:
                        initial_controls=(seed.metadata["scenarioControlSchedule"][0]
                                          if args.normalize_initial_controls else schedule[0])
                        for offset,value in zip((0x98,0x9c,0xa0),initial_controls):
                            own_write(vehicle+offset,struct.pack("<f",value))
                    state = u64(manager + 0x70) + index * 88
                    if not args.preserve_source_velocity:
                        own_write(state + 0x40, struct.pack("<3f", 0, 0, 30))
                        own_write(vehicle + 0x12FC, struct.pack("<3f", 0, 0, 30))
                if throttle is not None:
                    flags_address = u64(manager + 0x30) + index
                    model = u64(u64(manager + 0x10) + index * 8)
                    if args.source_body_activation:
                        own_write(flags_address,bytes([source_activation["sourceFlags"]]))
                        own_write(model+0x50,struct.pack("<I",source_activation["modelWord50"]))
                    else:
                        own_write(flags_address, bytes([own_read(flags_address, 1)[0] | 8]))
                        own_write(model + 0x50, struct.pack("<I", 0))
                mu.mem_write(0x200000000, struct.pack("<3I", initial_tick, 10, 0x3C23D70B))
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
                ]:
                    mu.reg_write(register, value)
                if outer_stage is not None:
                    for name,value in outer_stage["registers"].items():
                        mu.reg_write(globals()["UC_X86_REG_"+name.upper()],int(value,0))
                    for xmm_index,words in enumerate(outer_stage["xmmWords"]):
                        mu.reg_write(globals()["UC_X86_REG_XMM"+str(xmm_index)],sum(word<<(32*j) for j,word in enumerate(words)))
                    mu.reg_write(UC_X86_REG_MXCSR,outer_stage["mxcsr"])
                    mu.reg_write(UC_X86_REG_EFLAGS,outer_stage["rflags"]&~0x10000)
                    mu.reg_write(UC_X86_REG_GS_BASE,int(outer_stage["teb"],0))
                    rsp=int(outer_stage["stackPointer"],0)
                    own_write(rsp,struct.pack("<Q",0x500000000))
                body_count = u32(manager + 0x78)
                state_address = u64(manager + 0x70)
                rigid_before = own_read(state_address, body_count * 88)
                initial_data.update(
                    {
                        page: bytes(mu.mem_read(page, 4096))
                        for page in pages
                        if not executable_address(page)
                    }
                )
                phase[0] = True
                mark_access(state_address, body_count * 88)
                if recorder is not None:
                    for address,extent in excluded:
                        if not recorder.exclude(recorder.handle,address,extent):raise ValueError("Cannot exclude owned control scratch")
                    for address in platform_boundaries:
                        if not recorder.platform(recorder.handle,address):raise ValueError("Cannot register modeled platform API")
                    if not recorder.start(recorder.handle):raise ValueError("Cannot start native discovery recorder")
                frame_trace = []
                started = time.perf_counter()
                error = None
                try:
                    for frame in range(args.steps):
                        if throttle is not None and schedule is not None:
                            for offset,value in zip((0x98,0x9c,0xa0),schedule[frame]):
                                mark_access(vehicle+offset,4)
                                mu.mem_write(vehicle+offset,struct.pack("<f",value))
                        mu.mem_write(
                            0x200000000,
                            struct.pack("<3I", initial_tick + frame * 10, 10, 0x3C23D70B),
                        )
                        mu.mem_write(rsp, struct.pack("<Q", 0x500000000))
                        mu.reg_write(UC_X86_REG_RSP, rsp)
                        mu.reg_write(UC_X86_REG_RCX, manager)
                        mu.reg_write(UC_X86_REG_RDX, 0x200000000)
                        if outer_stage is not None:
                            mu.reg_write(UC_X86_REG_RCX,int(outer_stage["scene"],0))
                            mu.reg_write(UC_X86_REG_RDX,initial_tick+frame*10)
                            mu.reg_write(UC_X86_REG_R8,10)
                            mu.reg_write(UC_X86_REG_R9,0)
                            mu.emu_start(base+0x12e9ea0,0x500000000,count=10000000)
                        elif args.vehicle_scene_pipeline:
                            if args.collision_query_cycle:
                                for entry in (0x2a6360,0x2a6960):
                                    mu.reg_write(UC_X86_REG_RCX,collision_world)
                                    mu.emu_start(base+entry,0x500000000,count=2000000)
                                    if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                                    mu.mem_write(rsp,struct.pack("<Q",0x500000000))
                                    mu.reg_write(UC_X86_REG_RSP,rsp)
                                if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                            mu.reg_write(UC_X86_REG_RCX,owner)
                            mu.reg_write(UC_X86_REG_RDX,0x200000000)
                            mu.emu_start(base+0x1501f00,0x500000000,count=2000000)
                            if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                            mu.mem_write(rsp,struct.pack("<Q",0x500000000))
                            mu.reg_write(UC_X86_REG_RSP,rsp)
                            mu.reg_write(UC_X86_REG_RCX,manager)
                            mu.reg_write(UC_X86_REG_RDX,0x200000000)
                        if outer_stage is None:
                            mu.emu_start(base + 0x7BD0E0, 0x500000000, count=2000000)
                        if mu.reg_read(UC_X86_REG_RIP) != 0x500000000:
                            break
                        if args.post_contact_dispatch or args.vehicle_scene_pipeline:
                            for entry,receiver,second in ((0x2a9b50,collision_world,None),
                                    (0x7bfcb0,manager,None),(0x7d2b90,owner,0x200000000)):
                                mu.mem_write(rsp,struct.pack("<Q",0x500000000))
                                mu.reg_write(UC_X86_REG_RSP,rsp)
                                mu.reg_write(UC_X86_REG_RCX,receiver)
                                if second is not None:mu.reg_write(UC_X86_REG_RDX,second)
                                mu.emu_start(base+entry,0x500000000,count=2000000)
                                if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                            if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                            if args.vehicle_scene_pipeline:
                                mu.mem_write(rsp,struct.pack("<Q",0x500000000))
                                for register,value in ((UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,owner),
                                    (UC_X86_REG_RDX,manager),(UC_X86_REG_R8,10000+frame*10),
                                    (UC_X86_REG_XMM3,0x3c23d70b)):
                                    mu.reg_write(register,value)
                                mu.emu_start(base+0x1501f50,0x500000000,count=2000000)
                                if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                                if args.vehicle_pose_sync:
                                    mu.mem_write(rsp,struct.pack("<Q",0x500000000))
                                    mu.reg_write(UC_X86_REG_RSP,rsp)
                                    mu.reg_write(UC_X86_REG_RCX,owner)
                                    mu.emu_start(base+0x7d2cf0,0x500000000,count=2000000)
                                    if mu.reg_read(UC_X86_REG_RIP)!=0x500000000:break
                        frame_trace.append(
                            bytes(mu.mem_read(state_address, body_count * 88))
                            + bytes(mu.mem_read(vehicle, 0x1D00))
                            + bytes(mu.mem_read(force_address, 24))
                        )
                        if frame % 10 == 0:
                            print("STEP_CAPTURE", trial, frame + 1, flush=True)
                except UcError as exc:
                    error = str(exc)
                if recorder is not None:
                    fault=recorder.fault_info()
                    if fault:fault_reason.append("Native capture rejected instruction/access: "+str(fault))
                    for page,(accessed,executed,written) in recorder.snapshot().items():
                        if any(executed):executed_masks[page]=bytearray(executed)
                        if any(written) and not any(a<=page<a+n for a,n in synthetic):write_pages.add(page)
                        if any(accessed):
                            target_masks=code_reads if executable_address(page) else data_masks
                            mask=target_masks.setdefault(page,bytearray(4096))
                            for i,value in enumerate(accessed):mask[i]|=value
                            if page not in initial_data and not executable_address(page):
                                if not any(a<=page<a+n for a,n in synthetic):
                                    raise ValueError("Native recorder observed a page without a frozen initial copy")
                                initial_data[page]=seed.pages[page].initial if seed and page in seed.pages else bytes(4096)
                    report["nativeCaptureRecorder"]={"sha256":hashlib.sha256(args.native_capture.read_bytes()).hexdigest(),
                        "implementation":"separate_native_ephemeral_discovery",**recorder.counters(),
                        "offlineCoverageGuardChanged":False}
                    recorder.close()
                end = mu.reg_read(UC_X86_REG_RIP)
                completed = (end == 0x500000000 and len(frame_trace)==args.steps
                             and error is None and not fault_reason)
                after = own_read(vehicle, 0x1D00)
                forces_after = own_read(force_address, 24)
                rigid_after = own_read(state_address, body_count * 88)

                def rigid_record(raw, i):
                    chunk = raw[i * 88 : (i + 1) * 88]
                    return {
                        "position": list(struct.unpack_from("<3f", chunk, 0x24)),
                        "quaternionWxyz": list(struct.unpack_from("<4f", chunk, 0x30)),
                        "linearVelocity": list(struct.unpack_from("<3f", chunk, 0x40)),
                        "angularVelocity": list(struct.unpack_from("<3f", chunk, 0x4C)),
                        "bytesSha256": hashlib.sha256(chunk).hexdigest(),
                    }

                roots = sorted(
                    {
                        code.index.root(x)
                        for x in coverage
                        if code.index.root(x) is not None
                    }
                )
                result = {
                    "trial": trial,
                    "rigidStateCount": body_count,
                    "rigidBefore": [
                        rigid_record(rigid_before, i) for i in range(body_count)
                    ],
                    "rigidAfter": [
                        rigid_record(rigid_after, i) for i in range(body_count)
                    ],
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
                    output = args.output
                    target = output / (trial + ".tmstep")
                    if target.exists():
                        raise FileExistsError(target)
                    modules = [
                        {
                            "name": "game",
                            "sha256": SHA,
                            "base": base,
                            "imageSize": pe.OPTIONAL_HEADER.SizeOfImage,
                        },
                        {
                            "name": "ntdll",
                            "sha256": ntdll_sha,
                            "base": ntdll_base,
                            "imageSize": ntdll_pe.OPTIONAL_HEADER.SizeOfImage,
                        },
                    ]
                    metadata = {
                        "schema": "tm2020_sparse_outer_scene_fixture_v1" if outer_stage else "tm2020_sparse_main_step_fixture_v2",
                        "externalPlatformModels": [
                            {
                                "module": "kernel32",
                                "function": "HeapFree",
                                "address": heap_free_api,
                                "moduleSha256": kernel32_sha,
                            }
                        ]+([dict(module="kernel32",function="QueryPerformanceCounter",address=counter_api,
                            moduleSha256=kernel32_sha,mode="exploratoryHostClock",
                            seed=outer_stage["explorationCounterSeed"])] if outer_stage else []),
                        "modules": modules,
                        "entryRva": "0x12e9ea0" if outer_stage else "0x7bd0e0",
                        **({"outerSceneStage":outer_stage,"sourceSnapshotAtomicUnderLease":True,
                            "ownedStackReturnAddressReplaced":True} if outer_stage else {}),
                        "manager": manager,
                        "stateAddress": state_address,
                        "stateCount": body_count,
                        "vehicle": vehicle,
                        "configuration": configuration,
                        "registeredForceContext": owner,
                        "collisionWorld": collision_world,
                        "sourceBodyActivationRestored":args.source_body_activation,
                        "sourceVelocityPreserved":args.preserve_source_velocity or outer_stage is not None,
                        "observedSourceBodyActivation":source_activation,
                        "sourcePid": pid,
                        "sourceProcessCreationFiletime":manifest[2],
                        "initialSnapshotSeedFixtureSha256": seed.sha256 if seed is not None else
                            report["trials"][0]["sparseFixtureSha256"] if outer_scenarios and trial!="outer_scene_observed" else None,
                        **({"stoppedSnapshotCohortSha256":hashlib.sha256(outer_stage_path.read_bytes()).hexdigest()} if outer_scenarios else {}),
                        "selectedBodyIndex": index,
                        "tickCount": args.steps,
                        "timingWords": [initial_tick, 10, 0x3C23D70B],
                        "synthetic": synthetic,
                        "codePages": [],
                        "codeDataOverlays": [],
                        "dataPages": [],
                        "sourceCodeBytesRetained": False,
                        **({"pinnedReadonlyConstantExtensions":seed.metadata["pinnedReadonlyConstantExtensions"]}
                           if seed is not None and "pinnedReadonlyConstantExtensions" in seed.metadata else {}),
                        "rawHeapPagesPersisted": False,
                        "originalWholeStepInstructionOracleQualified": False,
                        "modeledPlatformApis": [
                            "RtlAllocateHeap",
                            "RtlFreeHeap",
                            "RtlReAllocateHeap",
                            "RtlSizeHeap",
                            "memset",
                            "memmove",
                            "memcpy",
                        ],
                        "rigidBefore": result["rigidBefore"],
                        "rigidAfter": result["rigidAfter"],
                    }
                    if args.post_contact_dispatch or args.vehicle_scene_pipeline:
                        metadata["postStepPipeline"]={"version":4 if args.collision_query_cycle else 3 if args.vehicle_pose_sync else 2 if args.vehicle_scene_pipeline else 1,"collisionWorld":collision_world,
                            "registeredForceContext":owner,"entryRvas":[0x2a9b50,0x7bfcb0,0x7d2b90],
                            "completeSceneUpdateQualified":False}
                        if args.vehicle_scene_pipeline:
                            metadata["postStepPipeline"]["entryRvas"].append(0x1501f50)
                            metadata["postStepPipeline"]["preEntryRvas"]=[0x1501f00]
                            if args.vehicle_pose_sync:
                                metadata["postStepPipeline"]["entryRvas"].append(0x7d2cf0)
                            if args.collision_query_cycle:
                                metadata["postStepPipeline"]["preEntryRvas"]=[0x2a6360,0x2a6960,0x1501f00]
                    if throttle is not None and schedule is not None:
                        metadata["scenarioControlSchedule"]=schedule
                        metadata["initialControlsNormalizedToSeed"]=args.normalize_initial_controls
                        metadata["initialControlRecord"]=list(initial_controls)
                        metadata["scenarioControls"]={"heldEveryStep":False,"ticks":len(schedule),
                            "source":"explicit controls in owned emulator during fresh read-only capture"}
                        metadata["scenarioSteeringOffset"]=0xa0
                    if outer_controls is not None or outer_plan is not None:
                        if sum(row["trial"]==trial for row in report.get("outerSceneInputCommands",[]))!=args.steps:
                            raise ValueError("Scene did not consume exactly one selected input command per tick")
                        metadata["scenarioControlSchedule"]=outer_plan if outer_plan is not None else [outer_controls]*args.steps
                        metadata["outerSceneInputAdapter"]={"version":1,"decoderRva":"0x12bce40",
                            "descriptorType":0x0a020000,"recordKind":2,"recordFloatOffsets":[8,12,4],
                            "rawKeyboardMappingQualified":False,"liveActionOracleQualified":False}
                    for page, (original, disk) in sorted(loaded_code.items()):
                        source_pe, source_base = source_code(page)
                        module = 1 if source_base == ntdll_base else 0
                        metadata["codePages"].append([module, page - source_base])
                        read_mask = code_reads.get(page, bytearray(4096))
                        exec_mask = executed_masks.get(page, bytearray(4096))
                        changes = [
                            [i, original[i]]
                            for i in range(4096)
                            if read_mask[i] and original[i] != disk[i]
                        ]
                        if any(exec_mask[i] for i, _ in changes):
                            raise ValueError(
                                "Code overlay would retain executed instruction bytes"
                            )
                        if changes:
                            metadata["codeDataOverlays"].append(
                                {
                                    "module": module,
                                    "rva": page - source_base,
                                    "bytes": changes,
                                }
                            )
                    # Explicit file constants are inputs in addition to observed
                    # working-set bytes. Preserve inherited constants even when
                    # this shorter branch never reads them. Their provenance
                    # remains pinned .rdata, never a claimed live access.
                    for extension in metadata.get("pinnedReadonlyConstantExtensions",[]):
                        raw=pe.get_data(extension["rva"],extension["bytes"])
                        if hashlib.sha256(raw).hexdigest()!=extension["sha256"]:
                            raise ValueError("Inherited constant differs from pinned file")
                        for offset,value in enumerate(raw):
                            address=base+extension["rva"]+offset
                            page=address&~4095;at=address&4095
                            load(page)
                            if initial_data[page][at]!=value or bytes(mu.mem_read(address,1))[0]!=value:
                                raise ValueError("Inherited read-only constant changed during capture")
                            data_masks.setdefault(page,bytearray(4096))[at]=1
                    with ZipFile(target, "x", ZIP_DEFLATED, compresslevel=7) as archive:
                        for page, mask in sorted(data_masks.items()):
                            initial_page = initial_data[page]
                            final_page = bytes(mu.mem_read(page, 4096))
                            mask = bytes(mask)
                            raw = (
                                mask
                                + bytes(
                                    b if m else 0 for b, m in zip(initial_page, mask)
                                )
                                + bytes(b if m else 0 for b, m in zip(final_page, mask))
                            )
                            name = f"data/{page:016x}.bin"
                            archive.writestr(name, raw)
                            metadata["dataPages"].append(
                                {
                                    "address": page,
                                    "file": name,
                                    "sha256": hashlib.sha256(raw).hexdigest(),
                                }
                            )
                        trace_outputs = [
                            {
                                "name": "rigidStates",
                                "address": state_address,
                                "bytes": body_count * 88,
                            },
                            {
                                "name": "selectedVehicleObservedBytes",
                                "address": vehicle,
                                "bytes": 0x1D00,
                            },
                            {
                                "name": "selectedForceAccumulator",
                                "address": force_address,
                                "bytes": 24,
                            },
                        ]
                        trace_mask = bytes(
                            data_masks.get(at & ~4095, bytes(4096))[at & 4095]
                            for out in trace_outputs
                            for at in range(
                                out["address"], out["address"] + out["bytes"]
                            )
                        )
                        trace_blob = b"".join(
                            bytes(b if m else 0 for b, m in zip(frame, trace_mask))
                            for frame in frame_trace
                        )
                        if len(frame_trace) != args.steps:
                            raise ValueError("Incomplete frame reference trace")
                        archive.writestr("trace-mask.bin", trace_mask)
                        archive.writestr("trace-expected.bin", trace_blob)
                        metadata["trace"] = {
                            "outputs": trace_outputs,
                            "frameBytes": len(trace_mask),
                            "frames": len(frame_trace),
                            "maskFile": "trace-mask.bin",
                            "maskSha256": hashlib.sha256(trace_mask).hexdigest(),
                            "expectedFile": "trace-expected.bin",
                            "expectedSha256": hashlib.sha256(trace_blob).hexdigest(),
                        }
                        archive.writestr(
                            "metadata.json",
                            json.dumps(metadata, indent=2, allow_nan=False) + "\n",
                        )
                    # Reject serialization/provenance mistakes before a capture
                    # is reported as retained, including inherited constants.
                    verify_original_step_images(load_original_step_fixture(target),
                        (exe,ntdll_file,Path(r"C:\Windows\System32\kernel32.dll")))
                    result["sparseFixtureSha256"] = hashlib.sha256(
                        target.read_bytes()
                    ).hexdigest()
                    result["sparseFixtureBytes"] = target.stat().st_size
                    result["codePages"] = len(loaded_code)
                    result["sparseDataPages"] = len(data_masks)
                    result["codeDataOverlayBytes"] = sum(
                        len(x["bytes"]) for x in metadata["codeDataOverlays"]
                    )
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
                if not completed or fault_reason:
                    raise RuntimeError("Complete original main-step sequence failed")
            identity()
            if not (
                u64(item + 16) == owner
                and u64(users + index * 16 + 8) == vehicle
                and u64(owner + 0x110) == manager
                and u32(ids + item_id * 4) == index
                and u64(vehicle+0x88)==configuration
            ):
                raise ValueError("Typed source binding changed")
            report["sourceBindingRecheckedAfterCapture"] = True
        finally:
            args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    finally:
        k.CloseHandle(h)
        if observer:k.CloseHandle(observer)
        if release:k.CloseHandle(release)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-binding",type=Path,
                        help="Fresh native callback/backlink discovery report")
    parser.add_argument("--candidate-index",type=int,default=0)
    parser.add_argument("--module-base", type=lambda x: int(x, 0))
    parser.add_argument("--manager", type=lambda x: int(x, 0))
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--outer-scene-stage",type=Path,help="Stopped original 0x12e9ea0 entry lease; mode0 only")
    parser.add_argument("--snapshot-observer-pid",type=int)
    parser.add_argument("--snapshot-release-event")
    parser.add_argument("--outer-scene-controls",nargs=3,type=float,metavar=("DRIVE","BRAKE","STEERING"))
    parser.add_argument("--native-capture",type=Path)
    parser.add_argument("--outer-scene-scenarios",type=Path)
    parser.add_argument("--control-schedule",type=Path,
                        help="JSON [drive,brake,steering command] triples applied only to the owned active trial")
    parser.add_argument("--active-only",action="store_true",
                        help="Capture only the owned active trial, omitting the inactive reference")
    parser.add_argument("--post-contact-dispatch",action="store_true",
                        help="Research only: append the three statically ordered scene contact procedures in owned memory")
    parser.add_argument("--vehicle-scene-pipeline",action="store_true",
                        help="Research only: include pre/post vehicle scene updates around the main step")
    parser.add_argument("--vehicle-pose-sync",action="store_true",
                        help="Research only: append the original scene's body-to-vehicle state synchronization")
    parser.add_argument("--collision-query-cycle",action="store_true",
                        help="Research only: include the original collision-world query begin/update calls")
    parser.add_argument("--source-body-activation",action="store_true",
                        help="Restore the observed source model/flags so the original scene chooses its own vehicle integration path")
    parser.add_argument("--normalize-initial-controls",action="store_true",
                        help="Keep seeded initial controls; apply the requested schedule before each tick")
    parser.add_argument("--preserve-source-velocity",action="store_true",
                        help="Retain observed rigid/vehicle velocity; do not inject the constructed [0,0,30] velocity")
    parser.add_argument("--initial-fixture",type=Path,
                        help="Retain observed initial inputs from a same-process owned fixture; read new working-set bytes from source")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.steps <= 1000:
        parser.error("Steps must be in [1,1000]")
    capture(args)
