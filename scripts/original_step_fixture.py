"""Bounded private numeric fixtures for complete original main-step references.

No archive is extracted to disk. Executable instructions come from separately
digest-pinned local binaries; overlays contain only captured nonexecuted data.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from zipfile import ZipFile

from force_worker_fixture import DataPage, require
from pinned_build import SHA

CONTROL_REGIONS = (
    (0x200000000, 0x10000),
    (0x300000000, 0x4000),
    (0x400000000, 0x20000),
    (0x500000000, 0x1000),
)
SYNTHETIC = CONTROL_REGIONS + (
    (0x600000000, 0x1000000),
    (0x700000000, 0x4000000),
    (0x800000000, 0x4000000),
)


@dataclass(frozen=True)
class OriginalStepFixture:
    sha256: str
    metadata: dict
    pages: dict
    trace_mask: bytes
    trace_expected: bytes


def load_original_step_fixture(path):
    path = Path(path)
    require(0 < path.stat().st_size <= 128 * 1024 * 1024, "Fixture archive size bound")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with ZipFile(path) as archive:
        infos = archive.infolist()
        require(
            len(infos) == len({i.filename for i in infos}) and len(infos) <= 16388,
            "Duplicate/oversized archive directory",
        )
        require(
            all(0 <= i.file_size <= 16 * 1024 * 1024 for i in infos)
            and sum(i.file_size for i in infos) <= 256 * 1024 * 1024,
            "Uncompressed archive size bound",
        )
        require(
            archive.getinfo("metadata.json").file_size <= 4 * 1024 * 1024,
            "Metadata size bound",
        )
        m = json.loads(archive.read("metadata.json"))
        outer=m.get("schema")=="tm2020_sparse_outer_scene_fixture_v1"
        require(
            (m["schema"] == "tm2020_sparse_main_step_fixture_v2" and m["entryRva"] == "0x7bd0e0" and "outerSceneStage" not in m)
            or (outer and m["entryRva"]=="0x12e9ea0"),
            "Unknown main-step fixture format",
        )
        if outer:
            s=m.get("outerSceneStage",{})
            require(s.get("schema")=="tm2020_stopped_scene_snapshot_lease_v1"
                    and s.get("gameThreadsStopped") is True and s.get("executableSha256")==SHA
                    and s.get("entryRva")=="0x12e9ea0" and s.get("modeWord")==0
                    and s.get("intervalWord")==10 and s.get("fifthArgument")=="0x0"
                    and s.get("sixthArgumentByte")==254 and s.get("gameTlsLayoutQualified") is True
                    and m.get("sourceSnapshotAtomicUnderLease") is True and m.get("ownedStackReturnAddressReplaced") is True
                    and "postStepPipeline" not in m and 1<=m.get("tickCount",0)<=100,
                    "Unsupported stopped outer-scene snapshot")
            names={"rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp","r8","r9","r10","r11","r12","r13","r14","r15"}
            require(set(s.get("registers",{}))==names and all(isinstance(v,str) and 0<=int(v,0)<1<<64 for v in s["registers"].values())
                    and s["registers"]["rcx"]==s["scene"] and s["registers"]["rsp"]==s["stackPointer"]
                    and int(s["registers"]["rdx"],0)==s["clockWord"]
                    and s["clockWord"]==m["timingWords"][0],"Outer scene register ABI differs")
            require(len(s.get("xmmWords",[]))==16 and all(isinstance(row,list) and len(row)==4
                    and all(type(v) is int and 0<=v<1<<32 for v in row) for row in s["xmmWords"])
                    and type(s.get("mxcsr")) is int and 0<=s["mxcsr"]<=0xffff
                    and type(s.get("rflags")) is int and 0<=s["rflags"]<1<<32,
                    "Invalid captured SIMD/control registers")
            require(s.get("pid")==m.get("sourcePid") and s.get("processCreationFiletime")==m.get("sourceProcessCreationFiletime")
                    and int(s.get("moduleBase","0"),0)==m["modules"][0]["base"]
                    and int(s["registers"]["r8"],0)==10 and int(s["registers"]["r9"],0)==0
                    and s.get("moduleTlsIndex")==0 and s.get("moduleTlsBytes")==0x11d8
                    and s.get("targetThreadsStopped") is True and s.get("tlsCaptured") is True,
                    "Outer scene source/TLS identity differs")
            plan=m.get("scenarioControlSchedule")
            if plan is not None:
                require(m.get("outerSceneInputAdapter")==dict(version=1,decoderRva="0x12bce40",
                    descriptorType=0x0a020000,recordKind=2,recordFloatOffsets=[8,12,4],
                    rawKeyboardMappingQualified=False,liveActionOracleQualified=False)
                    and isinstance(plan,list) and len(plan)==m["tickCount"]
                    and all(isinstance(row,list) and len(row)==3
                        and all(type(v) in (int,float) and math.isfinite(v) for v in row)
                        and 0<=row[0]<=1 and 0<=row[1]<=1 and abs(row[2])<=1 for row in plan),
                    "Unsupported outer scene decoder control schedule")
            else:require("outerSceneInputAdapter" not in m,"Scene input adapter has no explicit command schedule")
        require(
            m["sourceCodeBytesRetained"] is False
            and m["rawHeapPagesPersisted"] is False
            and m["originalWholeStepInstructionOracleQualified"] is False,
            "Unexpected capture content or overstated scope",
        )
        require(
            m["modules"][0]["name"] == "game"
            and m["modules"][0]["sha256"] == SHA
            and len(m["modules"]) == 2
            and m["modules"][1]["name"] == "ntdll",
            "Mixed executable builds",
        )
        for module in m["modules"]:
            base, size = module["base"], module["imageSize"]
            require(
                0x100000000 <= base < 0x7FFF00000000
                and base % 65536 == 0
                and 4096 <= size < 128 * 1024 * 1024,
                "Invalid module extent",
            )
            require(
                len(module["sha256"]) == 64
                and len(bytes.fromhex(module["sha256"])) == 32,
                "Invalid module digest",
            )
        require(
            tuple(map(tuple, m["synthetic"])) == SYNTHETIC,
            "Unexpected synthetic memory layout",
        )
        require(
            type(m["tickCount"]) is int
            and 1 <= m["tickCount"] <= 1000
            and m["timingWords"][1:] == [10, 0x3C23D70B]
            and 0 <= m["timingWords"][0] <= 0xFFFFFFFF - 10000,
            "Unsupported timing/horizon",
        )
        require(
            1 <= m["stateCount"] <= 64
            and 0 <= m["selectedBodyIndex"] < m["stateCount"],
            "Invalid rigid state span",
        )
        require(
            0 < len(m["codePages"]) <= 16384
            and len(m["codePages"]) == len(set(map(tuple, m["codePages"]))),
            "Duplicate/oversized code page list",
        )
        code_addresses = set()
        for module, rva in m["codePages"]:
            require(
                module in (0, 1)
                and rva % 4096 == 0
                and 0 <= rva <= m["modules"][module]["imageSize"] - 4096,
                "Code page extent",
            )
            code_addresses.add(m["modules"][module]["base"] + rva)
        overlay_seen = set()
        for overlay in m["codeDataOverlays"]:
            key = (overlay["module"], overlay["rva"])
            require(
                key not in overlay_seen and list(key) in m["codePages"],
                "Invalid/duplicate overlay page",
            )
            overlay_seen.add(key)
            changes = overlay["bytes"]
            require(
                0 < len(changes) <= 4096
                and len({i for i, v in changes}) == len(changes)
                and all(0 <= i < 4096 and 0 <= v <= 255 for i, v in changes),
                "Invalid numeric overlay",
            )
        pages = {}
        expected_names = {"metadata.json", "trace-mask.bin", "trace-expected.bin"}
        require(0 < len(m["dataPages"]) <= 16384, "Data page count bound")
        for rec in m["dataPages"]:
            address = rec["address"]
            name = f"data/{address:016x}.bin"
            require(
                rec["file"] == name
                and address % 4096 == 0
                and address not in pages
                and address not in code_addresses,
                "Duplicate/misaligned/code-colliding data page",
            )
            require(
                0x100000000 <= address <= 0x40000000000 - 4096
                or (outer and address==0x7ffe0000)
                or any(
                    module["base"]
                    <= address
                    <= module["base"] + module["imageSize"] - 4096
                    for module in m["modules"]
                ),
                "Data page exceeds captured address domain",
            )
            require(
                not any(
                    a < address + 4096 and address < a + n for a, n in CONTROL_REGIONS
                ),
                "Source page collides with replay control memory",
            )
            raw = archive.read(name)
            require(
                len(raw) == 12288 and hashlib.sha256(raw).hexdigest() == rec["sha256"],
                "Data page digest/extent mismatch",
            )
            mask, initial, expected = raw[:4096], raw[4096:8192], raw[8192:]
            require(
                all(
                    v in (0, 1) and (v or a == b == 0)
                    for v, a, b in zip(mask, initial, expected)
                ),
                "Unaccessed source bytes retained",
            )
            pages[address] = DataPage(address, mask, initial, expected)
            expected_names.add(name)
        if "postStepPipeline" in m:
            pipeline=m["postStepPipeline"]
            require(pipeline.get("version") in (1,2,3,4)
                    and pipeline.get("entryRvas")==([0x2a9b50,0x7bfcb0,0x7d2b90]
                        +([0x1501f50] if pipeline["version"]>=2 else [])
                        +([0x7d2cf0] if pipeline["version"]>=3 else []))
                    and (pipeline.get("preEntryRvas")==([0x2a6360,0x2a6960,0x1501f00]
                            if pipeline["version"]==4 else [0x1501f00]) if pipeline["version"]>=2
                         else "preEntryRvas" not in pipeline)
                    and pipeline.get("completeSceneUpdateQualified") is False,
                    "Unsupported post-step pipeline")
            for name in ("collisionWorld","registeredForceContext"):
                address=pipeline[name]
                require(type(address) is int and 0x100000000<=address<0x40000000000
                        and address==m[name] and (address&~4095) in pages,
                        "Post-step receiver outside captured inputs")
        trace = m["trace"]
        require(
            trace["frames"] == m["tickCount"]
            and trace["maskFile"] == "trace-mask.bin"
            and trace["expectedFile"] == "trace-expected.bin",
            "Trace/horizon mismatch",
        )
        outputs = trace["outputs"]
        require(
            len(outputs) == 3
            and outputs[0]["address"] == m["stateAddress"]
            and outputs[0]["bytes"] == m["stateCount"] * 88
            and outputs[1]["address"] == m["vehicle"]
            and outputs[1]["bytes"] == 0x1D00
            and outputs[2]["bytes"] == 24,
            "Unexpected typed output layout",
        )
        width = sum(o["bytes"] for o in outputs)
        mask = archive.read(trace["maskFile"])
        expected = archive.read(trace["expectedFile"])
        require(
            width == trace["frameBytes"] == len(mask)
            and len(expected) == width * m["tickCount"]
            and hashlib.sha256(mask).hexdigest() == trace["maskSha256"]
            and hashlib.sha256(expected).hexdigest() == trace["expectedSha256"],
            "Trace digest/extent mismatch",
        )
        require(
            all(v in (0, 1) for v in mask)
            and all(mask[i % width] or b == 0 for i, b in enumerate(expected)),
            "Invalid trace masks",
        )
        require(
            all(mask[: m["stateCount"] * 88]),
            "Complete rigid-state output is not retained",
        )
        mask_at = 0
        for out in outputs:
            require(
                out["address"] > 0 and out["address"] + out["bytes"] < 0x800000000000,
                "Typed output address bound",
            )
            for offset, observed in enumerate(mask[mask_at : mask_at + out["bytes"]]):
                if observed:
                    address = out["address"] + offset
                    page = pages.get(address & ~4095)
                    require(
                        page is not None and page.mask[address & 4095] == 1,
                        "Typed trace exposes uncaptured bytes",
                    )
            mask_at += out["bytes"]
        require(
            {i.filename for i in infos} == expected_names, "Unexpected archive content"
        )
        external = m["externalPlatformModels"]
        require(
            len(external) == (2 if outer else 1)
            and external[0]["module"] == "kernel32"
            and external[0]["function"] == "HeapFree"
            and len(bytes.fromhex(external[0]["moduleSha256"])) == 32,
            "Unknown external platform binding",
        )
        if outer:
            counter=external[1]
            require(counter["module"]=="kernel32" and counter["function"]=="QueryPerformanceCounter"
                and counter["moduleSha256"]==external[0]["moduleSha256"]
                and counter["mode"]=="exploratoryHostClock" and int(counter["seed"])>=0
                and int(s["queryPerformanceCounterAddress"],0)==counter["address"]
                and s["explorationCounterSeed"]==counter["seed"],
                "Unknown exploratory outer platform binding")
    return OriginalStepFixture(digest, m, pages, mask, expected)


def verify_original_step_images(fixture, paths):
    import pefile

    m = fixture.metadata
    require(len(paths) == 3, "Need the pinned game, ntdll and kernel32 images")
    for path, digest in zip(
        paths,
        (
            m["modules"][0]["sha256"],
            m["modules"][1]["sha256"],
            m["externalPlatformModels"][0]["moduleSha256"],
        ),
    ):
        require(
            hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest,
            "Different executable/OS cohort",
        )
    images = [pefile.PE(str(p), fast_load=True) for p in paths]
    images[2].parse_data_directories(directories=[0])
    exports={item.name.decode():item for item in images[2].DIRECTORY_ENTRY_EXPORT.symbols if item.name}
    external=m["externalPlatformModels"]
    platform_base=external[0]["address"]-exports["HeapFree"].address
    require(0x100000000<=platform_base<0x7fff00000000 and platform_base%65536==0
        and all(platform_base+images[2].OPTIONAL_HEADER.SizeOfImage<=module["base"]
                or module["base"]+module["imageSize"]<=platform_base for module in m["modules"]),
        "External platform image aliases original/synthetic code")
    for model in external:
        symbol=exports[model["function"]]
        require(not symbol.forwarder and model["address"]==platform_base+symbol.address,
                "External platform binding differs from pinned export")
    for image, module in zip(images, m["modules"]):
        require(
            image.OPTIONAL_HEADER.SizeOfImage == module["imageSize"],
            "Captured module extent differs from the pinned image",
        )
    for module, rva in m["codePages"]:
        require(
            any(
                s.Characteristics & 0x20000000
                and s.VirtualAddress <= rva
                and rva + 4096 <= s.VirtualAddress + s.SizeOfRawData
                for s in images[module].sections
            ),
            "Code page lies outside original executable sections",
        )
        require(
            len(images[module].get_data(rva, 4096)) == 4096,
            "Truncated original code page",
        )
    verify_pinned_readonly_constants(fixture,images[0])
    return images


def verify_pinned_readonly_constants(fixture,image):
    """Validate explicitly constructed .rdata bytes, without trusting metadata alone."""
    m=fixture.metadata
    extensions=m.get("pinnedReadonlyConstantExtensions",[])
    require(isinstance(extensions,list) and len(extensions)<=16,"Constant extension count bound")
    seen=set()
    for extension in extensions:
        require(extension.get("module")==0,"Only pinned game constants are supported")
        rva,count=extension["rva"],extension["bytes"]
        require(type(rva) is int and type(count) is int and rva>=0 and rva%4==0
                and 0<count<=64 and count%4==0,"Invalid explicit constant span")
        require(any(s.Name.rstrip(b"\0")==b".rdata" and not s.Characteristics&0xa0000000
                    and s.VirtualAddress<=rva and rva+count<=s.VirtualAddress+s.SizeOfRawData
                    for s in image.sections),"Constant is outside file-backed read-only .rdata")
        raw=image.get_data(rva,count)
        require(len(raw)==count and hashlib.sha256(raw).hexdigest()==extension["sha256"],
                "Pinned constant digest mismatch")
        for offset,value in enumerate(raw):
            address=m["modules"][0]["base"]+rva+offset
            require(address not in seen,"Overlapping explicit constant extensions")
            seen.add(address)
            page=fixture.pages.get(address&~4095);at=address&4095
            require(page is not None and page.mask[at]==1 and page.initial[at]==value
                    and page.expected[at]==value,"Constant extension differs from pinned file")
