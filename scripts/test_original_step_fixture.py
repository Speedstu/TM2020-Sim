"""Reject corrupted source/reference fixtures before original code execution."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from zipfile import ZipFile

from original_step_fixture import SYNTHETIC, load_original_step_fixture, verify_pinned_readonly_constants
from pinned_build import SHA


class FixtureBounds(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "owned.tmstep"
        address = 0x100000000
        raw_mask = bytes([1] * 88 + [0] * (4096 - 88))
        self.raw = raw_mask + bytes(8192)
        self.mask = bytes([1] * 88 + [0] * (0x1D00 + 24))
        self.expected = bytes(len(self.mask) * 2)
        self.meta = dict(
            schema="tm2020_sparse_main_step_fixture_v2",
            entryRva="0x7bd0e0",
            sourceCodeBytesRetained=False,
            rawHeapPagesPersisted=False,
            originalWholeStepInstructionOracleQualified=False,
            modules=[
                dict(name="game", sha256=SHA, base=0x7FF600000000, imageSize=0x3000000),
                dict(
                    name="ntdll",
                    sha256="0" * 64,
                    base=0x7FFA00000000,
                    imageSize=0x270000,
                ),
            ],
            synthetic=SYNTHETIC,
            tickCount=2,
            timingWords=[10000, 10, 0x3C23D70B],
            stateCount=1,
            selectedBodyIndex=0,
            manager=address,
            stateAddress=address,
            vehicle=address + 128,
            codePages=[[0, 0x7BD000]],
            codeDataOverlays=[],
            dataPages=[
                dict(
                    address=address,
                    file=f"data/{address:016x}.bin",
                    sha256=hashlib.sha256(self.raw).hexdigest(),
                )
            ],
            externalPlatformModels=[
                dict(
                    module="kernel32",
                    function="HeapFree",
                    address=0x7FFA10023E50,
                    moduleSha256="0" * 64,
                )
            ],
            trace=dict(
                outputs=[
                    dict(name="rigidStates", address=address, bytes=88),
                    dict(name="vehicle", address=address + 128, bytes=0x1D00),
                    dict(name="forces", address=address + 256, bytes=24),
                ],
                frames=2,
                frameBytes=len(self.mask),
                maskFile="trace-mask.bin",
                expectedFile="trace-expected.bin",
                maskSha256=hashlib.sha256(self.mask).hexdigest(),
                expectedSha256=hashlib.sha256(self.expected).hexdigest(),
            ),
        )

    def tearDown(self):
        self.directory.cleanup()

    def write(self, meta=None, raw=None, mask=None, expected=None, extra=False):
        m = copy.deepcopy(self.meta if meta is None else meta)
        raw = self.raw if raw is None else raw
        mask = self.mask if mask is None else mask
        expected = self.expected if expected is None else expected
        # Rehash mutations to test the actual format contract, not just SHA failure.
        m["dataPages"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
        m["trace"]["maskSha256"] = hashlib.sha256(mask).hexdigest()
        m["trace"]["expectedSha256"] = hashlib.sha256(expected).hexdigest()
        with ZipFile(self.path, "w") as archive:
            archive.writestr("metadata.json", json.dumps(m))
            archive.writestr(m["dataPages"][0]["file"], raw)
            archive.writestr("trace-mask.bin", mask)
            archive.writestr("trace-expected.bin", expected)
            if extra:
                archive.writestr("unrequested.bin", b"not a numeric fixture record")

    def test_valid_round_trip(self):
        self.write()
        f = load_original_step_fixture(self.path)
        self.assertEqual(f.metadata["tickCount"], 2)
        self.assertEqual(len(f.trace_mask), 7536)

    def outer_metadata(self):
        meta=copy.deepcopy(self.meta)
        registers={name:"0x0" for name in ("rax","rbx","rcx","rdx","rsi","rdi","rbp","rsp",
            "r8","r9","r10","r11","r12","r13","r14","r15")}
        registers.update(rcx=hex(meta["manager"]),rsp="0x123400000",rdx=hex(10000),r8="0xa")
        stage=dict(schema="tm2020_stopped_scene_snapshot_lease_v1",pid=123,processCreationFiletime="456",
            moduleBase=hex(meta["modules"][0]["base"]),executableSha256=SHA,entryRva="0x12e9ea0",
            scene=registers["rcx"],stackPointer=registers["rsp"],clockWord=10000,intervalWord=10,modeWord=0,
            fifthArgument="0x0",sixthArgumentByte=254,gameTlsLayoutQualified=True,tlsCaptured=True,
            gameThreadsStopped=True,targetThreadsStopped=True,moduleTlsIndex=0,moduleTlsBytes=0x11d8,
            registers=registers,xmmWords=[[0]*4 for _ in range(16)],mxcsr=0x1f80,rflags=0x202,
            queryPerformanceCounterAddress="0x7ffa10023480",explorationCounterSeed="12345")
        meta.update(schema="tm2020_sparse_outer_scene_fixture_v1",entryRva="0x12e9ea0",outerSceneStage=stage,
            sourceSnapshotAtomicUnderLease=True,ownedStackReturnAddressReplaced=True,sourcePid=123,
            sourceProcessCreationFiletime="456")
        meta["externalPlatformModels"].append(dict(module="kernel32",function="QueryPerformanceCounter",
            address=int(stage["queryPerformanceCounterAddress"],0),moduleSha256="0"*64,
            mode="exploratoryHostClock",seed=stage["explorationCounterSeed"]))
        return meta

    def test_outer_scene_abi_and_platform_bounds(self):
        meta=self.outer_metadata();self.write(meta=meta)
        self.assertEqual(load_original_step_fixture(self.path).metadata["entryRva"],"0x12e9ea0")
        cases=[]
        for field,value in (("gameThreadsStopped",False),("moduleTlsIndex",1),("moduleTlsBytes",4567),
            ("modeWord",1),("fifthArgument","0x123400000"),("sixthArgumentByte",0),("pid",999)):
            bad=copy.deepcopy(meta);bad["outerSceneStage"][field]=value;cases.append(bad)
        for register,value in (("r8","0xb"),("r9","0x1"),("rcx","0x123400000"),("rsp","0x0")):
            bad=copy.deepcopy(meta);bad["outerSceneStage"]["registers"][register]=value;cases.append(bad)
        bad=copy.deepcopy(meta);bad["outerSceneStage"]["xmmWords"][0][0]=2**32;cases.append(bad)
        bad=copy.deepcopy(meta);bad["externalPlatformModels"][1]["function"]="Unknown";cases.append(bad)
        bad=copy.deepcopy(meta);bad["externalPlatformModels"][1]["address"]+=1;cases.append(bad)
        bad=copy.deepcopy(meta);bad["externalPlatformModels"][1]["seed"]="0";cases.append(bad)
        for i,bad in enumerate(cases):
            with self.subTest(case=i),self.assertRaises(ValueError):
                self.write(meta=bad);load_original_step_fixture(self.path)

    def test_reject_metadata_corruption(self):
        cases = []
        for field, value in (
            ("tickCount", 0),
            ("tickCount", 1001),
            ("stateCount", 0),
            ("selectedBodyIndex", 1),
            ("sourceCodeBytesRetained", True),
            ("rawHeapPagesPersisted", True),
            ("originalWholeStepInstructionOracleQualified", True),
        ):
            m = copy.deepcopy(self.meta)
            m[field] = value
            cases.append(m)
        m = copy.deepcopy(self.meta)
        m["modules"][0]["sha256"] = "f" * 64
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["modules"][0]["base"] += 1
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["codePages"] *= 2
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["codePages"][0][1] = 0x3000000
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["timingWords"][2] = 0x3C23D70A
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["trace"]["frames"] = 1
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["trace"]["frameBytes"] += 1
        cases.append(m)
        m = copy.deepcopy(self.meta)
        m["externalPlatformModels"][0]["function"] = "Unknown"
        cases.append(m)
        for m in cases:
            with self.subTest(metadata=m):
                self.write(meta=m)
                with self.assertRaises(ValueError):
                    load_original_step_fixture(self.path)

    def test_reject_payload_corruption(self):
        bad_mask = bytearray(self.raw)
        bad_mask[0] = 2
        leaked_initial = bytearray(self.raw)
        leaked_initial[4096 + 88] = 1
        leaked_final = bytearray(self.raw)
        leaked_final[8192 + 88] = 1
        for raw in (self.raw[:-1], bad_mask, leaked_initial, leaked_final):
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()):
                self.write(raw=raw)
                with self.assertRaises(ValueError):
                    load_original_step_fixture(self.path)
        for kwargs in (
            dict(expected=self.expected[:-1]),
            dict(extra=True),
            dict(mask=self.mask[:-1]),
            dict(expected=b"\0" * 88 + b"\1" + self.expected[89:]),
        ):
            self.write(**kwargs)
            with self.assertRaises(ValueError):
                load_original_step_fixture(self.path)

    def test_reject_trace_exposing_unobserved_bytes(self):
        mask = bytearray(self.mask)
        mask[88] = 1
        self.write(mask=mask)
        with self.assertRaises(ValueError):
            load_original_step_fixture(self.path)

    def test_scene_pipeline_bounds(self):
        for version in (1,2,3,4):
            meta=copy.deepcopy(self.meta)
            address=meta["manager"]
            meta.update(collisionWorld=address,registeredForceContext=address)
            pipeline=dict(version=version,collisionWorld=address,registeredForceContext=address,
                          entryRvas=[0x2a9b50,0x7bfcb0,0x7d2b90]
                            +([0x1501f50] if version>=2 else [])
                            +([0x7d2cf0] if version>=3 else []),
                          completeSceneUpdateQualified=False)
            if version>=2:pipeline["preEntryRvas"]=[0x1501f00]
            if version==4:pipeline["preEntryRvas"]=[0x2a6360,0x2a6960,0x1501f00]
            meta["postStepPipeline"]=pipeline
            self.write(meta=meta)
            self.assertEqual(load_original_step_fixture(self.path).metadata["postStepPipeline"],pipeline)
            for field,value in (("version",5),("entryRvas",[0x7d2b90]),
                                ("collisionWorld",address+4096),("completeSceneUpdateQualified",True)):
                bad=copy.deepcopy(meta);bad["postStepPipeline"][field]=value
                self.write(meta=bad)
                with self.subTest(version=version,field=field),self.assertRaises(ValueError):
                    load_original_step_fixture(self.path)


class ReadonlyConstants(unittest.TestCase):
    def test_pinned_constant_provenance(self):
        raw=b"\0\0\xc8\xc2" # -100 binary32
        base=0x7ff600000000
        extension=dict(module=0,rva=0x1000,bytes=4,sha256=hashlib.sha256(raw).hexdigest())
        section=SimpleNamespace(Name=b".rdata\0\0",Characteristics=0x40000040,
                                VirtualAddress=0x1000,SizeOfRawData=4096)
        image=SimpleNamespace(sections=[section],get_data=lambda r,n:raw[:n])
        page=SimpleNamespace(mask=b"\1"*4+bytes(4092),initial=raw+bytes(4092),expected=raw+bytes(4092))
        fixture=SimpleNamespace(metadata=dict(modules=[dict(base=base)],
                                pinnedReadonlyConstantExtensions=[extension]),pages={base+0x1000:page})
        verify_pinned_readonly_constants(fixture,image)
        for name,value in (("Characteristics",0xc0000040),("Characteristics",0x60000040),
                           ("Name",b".data\0\0\0"),("SizeOfRawData",3)):
            changed=copy.deepcopy(image);setattr(changed.sections[0],name,value)
            with self.subTest(section=name,value=value),self.assertRaises(ValueError):
                verify_pinned_readonly_constants(fixture,changed)
        for key,value in (("module",1),("bytes",0),("bytes",68),("rva",0x1001),
                          ("sha256","0"*64)):
            changed=copy.deepcopy(fixture)
            changed.metadata["pinnedReadonlyConstantExtensions"][0][key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):
                verify_pinned_readonly_constants(changed,image)
        for key in ("mask","initial","expected"):
            changed=copy.deepcopy(fixture)
            setattr(changed.pages[base+0x1000],key,bytes(4096))
            with self.subTest(payload=key),self.assertRaises(ValueError):
                verify_pinned_readonly_constants(changed,image)
        changed=copy.deepcopy(fixture)
        changed.metadata["pinnedReadonlyConstantExtensions"]*=2
        with self.assertRaises(ValueError):verify_pinned_readonly_constants(changed,image)


if __name__ == "__main__":
    unittest.main()
