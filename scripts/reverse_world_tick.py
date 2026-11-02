"""Pin the caller-side 10 ms scene tick schedule in the known game build."""

import hashlib
import json
from pathlib import Path

from pe_unwind import PeCode
from reverse_physics import ROOT, SHA


def main():
    exe = Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
    if hashlib.sha256(exe.read_bytes()).hexdigest() != SHA:
        raise ValueError("Unknown Trackmania executable build")
    code = PeCode(exe)
    instructions = {
        i.address: i for root in (0x1312870, 0x12E9EA0) for i in code.instructions(root)
    }
    expected = {
        0x13128CA: ("cmp", "r14d, 0xa"),
        0x13128CE: ("jbe", "0x1313874"),
        0x13128F4: ("mov", "r15, qword ptr [rsi + 0xd78]"),
        0x13128FB: ("mov", "qword ptr [rsp + 0x70], r15"),
        0x131291C: ("mov", "rdx, qword ptr [r15 + 0x660]"),
        0x1312925: ("mov", "ecx, dword ptr [r15 + 0x668]"),
        0x1312940: ("mov", "rcx, qword ptr [rdx]"),
        0x1312947: ("and", "dword ptr [rcx + 0x1030], 0xfffffffe"),
        0x131294E: ("or", "dword ptr [rcx + 0x1030], 2"),
        0x1312955: ("mov", "qword ptr [rcx + 0x1038], r13"),
        0x131295C: ("cmp", "rdx, r8"),
        0x131295F: ("jne", "0x1312940"),
        0x1312961: ("mov", "eax, dword ptr [rsi + 0xe30]"),
        0x131296C: ("cmp", "eax, ecx"),
        0x1312970: ("lea", "eax, [r14 - 0xa]"),
        0x1312974: ("mov", "dword ptr [rsi + 0xe30], eax"),
        0x131297C: ("cmp", "r14d, eax"),
        0x131297F: ("jbe", "0x1313864"),
        0x13133EA: ("mov", "r9d, r13d"),
        0x13133F2: ("mov", "r8d, 0xa"),
        0x13133FD: ("mov", "rcx, rbx"),
        0x1313400: ("mov", "edx, esi"),
        0x1313402: ("mov", "qword ptr [rsp + 0x20], rax"),
        0x1313407: ("call", "0x12e9ea0"),
        0x131336C: ("mov", "r15, qword ptr [rsp + 0x70]"),
        0x13133ED: ("mov", "rbx, qword ptr [rsp + 0x70]"),
        0x1313778: ("mov", "byte ptr [rsp + 0x28], 0xfe"),
        0x131377D: ("xor", "r9d, r9d"),
        0x1313780: ("mov", "qword ptr [rsp + 0x20], r13"),
        0x1313785: ("mov", "edx, r14d"),
        0x1313788: ("mov", "rcx, r15"),
        0x131378B: ("lea", "r8d, [r13 + 0xa]"),
        0x131378F: ("call", "0x12e9ea0"),
        0x131366E: ("mov", "r14d, dword ptr [rsi + 0xe30]"),
        0x1313675: ("add", "r14d, 0xa"),
        0x1313679: ("cmp", "r14d, dword ptr [rsp + 0x60]"),
        0x131367E: ("ja", "0x1313800"),
        0x13137EA: ("mov", "dword ptr [rsi + 0xe30], r14d"),
        0x13137F1: ("add", "r14d, 0xa"),
        0x13137F5: ("cmp", "r14d, dword ptr [rsp + 0x60]"),
        0x13137FA: ("jbe", "0x1313690"),
        0x12EA4D1: ("call", "0x12dd6d0"),
        0x12EA4D6: ("mov", "r14, rax"),
        0x12EA4D9: ("test", "rax, rax"),
        0x12EA4DE: ("mov", "rdx, rbx"),
        0x12EA4E1: ("mov", "rcx, rsi"),
        0x12EA4E4: ("call", "0x12e8650"),
        0x12EA4E9: ("mov", "rdx, rbx"),
        0x12EA4EC: ("mov", "rcx, rsi"),
        0x12EA4EF: ("mov", "r11d, eax"),
        0x12EA4F2: ("call", "0x12e85e0"),
        0x12EA4F7: ("mov", "r8d, eax"),
        0x12EA4FA: ("mov", "r9d, r11d"),
        0x12EA4FD: ("mov", "rdx, r14"),
        0x12EA500: ("call", "0x722d90"),
    }
    for address, assembly in expected.items():
        instruction = instructions.get(address)
        if (
            instruction is None
            or (instruction.mnemonic, instruction.op_str) != assembly
        ):
            raise ValueError(f"Tick scheduler instruction changed at {address:#x}")

    update_leaf = list(code.cs.disasm(code.pe.get_data(0x722D90, 15), 0x722D90))
    leaf_expected = [
        ("mov", "dword ptr [rdx + 0x1268], r8d"),
        ("mov", "dword ptr [rdx + 0x126c], r9d"),
        ("ret", ""),
    ]
    if [(i.mnemonic, i.op_str) for i in update_leaf] != leaf_expected:
        raise ValueError("Per-object tick prepass leaf changed")

    def row(address):
        item = instructions[address]
        return {
            "rva": hex(address),
            "bytes": bytes(item.bytes).hex(),
            "assembly": f"{item.mnemonic} {item.op_str}",
        }

    report = {
        "schema": "tm2020_scene_tick_schedule_evidence_v1",
        "executableSha256": SHA,
        "callerRva": "0x1312870",
        "sceneUpdateRva": "0x12e9ea0",
        "scheduler": "fixed_integer_millisecond_catch_up",
        "incomingTimestampMustExceedStoredTimestamp": True,
        "firstStoredTimestampInitializedToIncomingMinusMs": 10,
        "eachPrimaryLoopTimestampAdvancesMs": 10,
        "primaryLoopProcessesTicksThroughIncomingTimestamp": True,
        "updateReceiverLoadedFromCallerOffset": "0xd78",
        "receiverChildPointerArrayOffset": "0x660",
        "receiverChildPointerCountOffset": "0x668",
        "perChildPrepassStateWordOffset": "0x1030",
        "perChildPrepassClearsBitMask": "0x1",
        "perChildPrepassSetsBitMask": "0x2",
        "perChildPrepassZeroesWordOffset": "0x1038",
        "childStructureSemanticsVerified": False,
        "childUpdateCallbackRva": "0x722d90",
        "childUpdateCallbackWritesDwords": {
            "rdxPlus0x1268": "r8d",
            "rdxPlus0x126c": "r9d",
        },
        "childUpdateCallbackR8Source": "return of 0x12e85e0",
        "childUpdateCallbackR9Source": "return of 0x12e8650",
        "childUpdateCallbackExactLeafBytes": True,
        "primaryCallRva": "0x1313407",
        "primaryCallSuppliesIntegerIntervalMs": 10,
        "primaryCallPassesEsiAsIntegerTimestamp": True,
        "auxiliaryCallRva": "0x131378f",
        "auxiliaryCallSuppliesR13PlusTenAsIntegerIntervalMs": True,
        "auxiliaryCallUsesDistinctMarkerByte": "0xfe",
        "integerTimestampLoopStoresSceneOffset": "0xe30",
        "integerTimestampLoopIncrementMs": 10,
        "stablePlayerRootVerified": False,
        "authoritativePhysicsTickBindingVerified": False,
        "instructions": [row(address) for address in sorted(expected)],
    }
    output = ROOT / "local/recon/scene-tick-schedule-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "PASS SCENE_TICK_SCHEDULE catch_up=true primary_ms=10 loop_ms=10 "
        "scene_tick_root_unverified=true authoritative_physics_tick_unverified=true"
    )


if __name__ == "__main__":
    main()
