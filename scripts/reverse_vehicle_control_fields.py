"""Pin the internal pedal and steering scalar dataflow in the game build."""

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
        i.address: i
        for root in (
            0x841500,
            0x843190,
            0x850E50,
            0x869CD0,
            0x86B060,
            0x86BC50,
            0x829950,
            0x80F5F0,
            0x81A820,
            0x851F00,
            0x7CFCE0,
            0x7CFAC0,
            0x7D1FA0,
            0x7D1380,
            0x842500,
            0x83DE60,
            0x83DD90,
        )
        for i in code.instructions(root)
    }
    expected = {
        0x843230: ("movss", "xmm0, dword ptr [r8 + 0x98]"),
        0x843239: ("comiss", "xmm0, xmm9"),
        0x84327A: ("movss", "xmm1, dword ptr [r8 + 0x9c]"),
        0x843286: ("comiss", "xmm1, xmm9"),
        0x8432CB: ("movss", "xmm0, dword ptr [r8 + 0x98]"),
        0x8432FA: ("mulss", "xmm3, dword ptr [rbx + 0xd90]"),
        0x843476: ("movss", "xmm5, dword ptr [r8 + 0x9c]"),
        0x843498: ("comiss", "xmm1, xmm3"),
        0x8434B8: ("movss", "xmm0, dword ptr [r8 + 0x98]"),
        0x84169E: ("movss", "xmm1, dword ptr [rbx + 0x9c]"),
        0x8416A8: ("movss", "xmm1, dword ptr [rbx + 0x98]"),
        0x8416B7: ("call", "0x8447b0"),
        0x8416DA: ("movss", "xmm1, dword ptr [rbx + 0xa0]"),
        0x8416F8: ("movss", "xmm2, dword ptr [rbx + 0x1430]"),
        0x841734: ("movss", "dword ptr [rbx + 0x1430], xmm1"),
        0x8516E2: ("movss", "xmm0, dword ptr [rdi + 0x98]"),
        0x8516EA: ("subss", "xmm0, dword ptr [rdi + 0x9c]"),
        0x8516F6: ("mulss", "xmm2, xmm0"),
        0x8516FD: ("call", "0x42bcb0"),
        0x851909: ("movss", "xmm1, dword ptr [rdi + 0x1430]"),
        0x851911: ("xorps", "xmm1, xmm15"),
        0x851915: ("mulss", "xmm1, dword ptr [rip + 0x14cdbdb]"),
        0x851948: ("call", "0x193880"),
        0x851B8D: ("movss", "xmm6, dword ptr [rdi + 0x1430]"),
        0x851BA6: ("call", "0x42bcb0"),
        0x869E8D: ("call", "0x841500"),
        0x86B0F6: ("call", "0x841500"),
        0x86BD10: ("call", "0x841500"),
        0x829A53: ("call", "0x8295c0"),
        0x829AAA: ("call", "0x8295c0"),
        0x80F6EA: ("call", "0x819ff0"),
        0x81A9CC: ("call", "0x819ff0"),
        0x852110: ("call", "0x841500"),
        0x8415B2: ("call", "0x843190"),
        0x7CFDA8: ("call", "0x7d1fa0"),
        0x7D202F: ("call", "0x7d1380"),
        0x7D2017: ("lea", "r9, [rbx + 0x90]"),
        0x7D1A1B: ("movss", "xmm0, dword ptr [rbx + 0x10]"),
        0x7D1A20: ("movss", "dword ptr [rdi + 0x10], xmm0"),
        0x7D1A25: ("mov", "eax, dword ptr [rbx + 8]"),
        0x7D1A28: ("mov", "dword ptr [rdi + 0x14], eax"),
        0x7D1A2B: ("mov", "eax, dword ptr [rbx + 0xc]"),
        0x7D1A2E: ("mov", "dword ptr [rdi + 0x18], eax"),
        0x7D1427: ("call", "0x842500"),
        0x7CFD4E: ("call", "0x7cfac0"),
        0x7CFAE8: ("call", "0x1467c90"),
        0x7CFAF5: ("call", "0x7c79e0"),
        0x7CFB94: ("call", "0x1467ca0"),
        0x7CFBA8: ("call", "0x7c7c70"),
        0x7CFE5D: ("mov", "rdx, qword ptr [rdi + 0x1c98]"),
        0x7CFE64: ("lea", "rcx, [rdi + 0x1280]"),
        0x7CFE6B: ("mov", "r8d, 0x878"),
        0x7CFE71: ("call", "0x18d7510"),
        0x83DE72: ("call", "0x83dc30"),
        0x83DE82: ("call", "0x83dd90"),
        0x83DE87: ("movss", "dword ptr [r9 + 0x98], xmm0"),
        0x83DE97: ("call", "0x83dbf0"),
        0x83DEAA: ("call", "0x83db80"),
        0x83DDF3: ("call", "0x1955c0"),
        0x83DDFB: ("call", "0x83dd60"),
    }
    for address, assembly in expected.items():
        instruction = instructions.get(address)
        if (
            instruction is None
            or (instruction.mnemonic, instruction.op_str) != assembly
        ):
            raise ValueError(f"Vehicle control instruction changed at {address:#x}")

    reviewed_leaf_ranges = {
        0x83DB80: 0x83DBA2,
        0x83DBF0: 0x83DC0B,
        0x83DC30: 0x83DC60,
        0x83DD60: 0x83DD85,
        0x7C79E0: 0x7C7A42,
        0x7C7C70: 0x7C7C7D,
        0x1467C90: 0x1467C9C,
    }
    leaf_expected = {
        0x83DB80: ("mov", "eax, dword ptr [rcx + 0x4ec]"),
        0x83DBF0: ("test", "byte ptr [rcx + 0x4ec], 4"),
        0x83DBF9: ("test", "byte ptr [rcx + 0xf0], 4"),
        0x83DC30: ("movsx", "eax, word ptr [rcx + 0x4e8]"),
        0x83DC48: ("movss", "xmm0, dword ptr [rcx + 0xf4]"),
        0x83DD60: ("movsx", "eax, word ptr [rcx + 0x4e8]"),
        0x83DD78: ("movss", "xmm0, dword ptr [rcx + 0xf4]"),
        0x7C79E0: ("mov", "rax, qword ptr [rdx + 0x78]"),
        0x7C7C70: ("movzx", "ecx, byte ptr [rcx + 0x13]"),
        0x1467C90: ("test", "rcx, rcx"),
    }
    for start, end in reviewed_leaf_ranges.items():
        if code.index.root(start) is not None:
            raise ValueError(f"Reviewed control leaf gained unwind metadata at {start:#x}")
        body = list(code.cs.disasm(code.pe.get_data(start, end - start), start))
        if not body or body[-1].address + body[-1].size != end or body[-1].mnemonic != "ret":
            raise ValueError(f"Reviewed control leaf boundary changed at {start:#x}")
    leaf_instructions = {}
    for address, assembly in leaf_expected.items():
        instruction = next(
            (i for i in code.cs.disasm(code.pe.get_data(address, 15), address)), None
        )
        if instruction is None or (instruction.mnemonic, instruction.op_str) != assembly:
            raise ValueError(f"Nested control-state instruction changed at {address:#x}")
        leaf_instructions[hex(address)] = {
            "bytes": bytes(instruction.bytes).hex(),
            "assembly": f"{instruction.mnemonic} {instruction.op_str}",
        }

    report = {
        "schema": "tm2020_internal_vehicle_control_fields_v1",
        "executableSha256": SHA,
        "offsetsAreGlobalUntypedFields": False,
        "rawControlEventMappingVerified": False,
        "fields": {
            "0x98": {
                "storage": "binary32",
                "candidateMeaning": "drive_or_acceleration_scalar",
                "offsetUseIsContextRelative": True,
                "observedContexts": [
                    "0x843190 wheel-spin input",
                    "0x850e50 force input",
                    "0x841500 default scalar passed to 0x8447b0 before the steering branch",
                ],
                "evidence": "0x843190 gates wheel-spin updates on this scalar and forms a drive target from it times tuning +0xd90; 0x850e50 combines it with 0x9c before curve evaluation.",
                "publicInputRangeVerified": False,
            },
            "0x9c": {
                "storage": "binary32",
                "candidateMeaning": "brake_scalar",
                "offsetUseIsContextRelative": True,
                "observedContexts": [
                    "0x843190 wheel-spin input",
                    "0x850e50 force input",
                    "0x841500 alternate scalar passed to 0x8447b0 before the steering branch",
                ],
                "evidence": "0x843190 has a separate branch and brake-tuning path; 0x850e50 subtracts it from 0x98 before curve evaluation.",
                "publicInputRangeVerified": False,
            },
            "0xa0": {
                "storage": "binary32",
                "candidateMeaning": "unslewed_steering_command",
                "offsetUseIsContextRelative": True,
                "observedContexts": ["0x841500 steering target at 0x8416da", "0x7d1380 snapshot steering output"],
                "evidence": "0x7d1fa0 passes vehicle +0x90 as the fourth argument to 0x7d1380; +0x10 is copied to snapshot steering +0x10. 0x841500 slews this vehicle +0xa0 command into +0x1430 unless a nested-state gate forces zero.",
                "publicInputRangeVerified": False,
            },
            "0x1430": {
                "storage": "binary32",
                "candidateMeaning": "steering_angle_scalar",
                "offsetUseIsContextRelative": True,
                "observedContexts": [
                    "0x850e50 steering transform",
                    "0x841500 slewed angle state",
                ],
                "evidence": "0x850e50 sign-adjusts and scales it, passes the value into quaternion construction at 0x193880, and separately evaluates an angle curve from its magnitude.",
                "publicInputRangeVerified": False,
            },
        },
        "steeringUpdateCallers": [
            {
                "rva": hex(address),
                "callerRva": hex(caller),
                "classification": classification + "; raw input mapping unverified",
            }
            for address, caller, classification in (
                (0x869E8D, 0x869CD0, "vehicle update variant"),
                (0x86B0F6, 0x86B060, "vehicle update variant"),
                (0x86BD10, 0x86BC50, "vehicle update variant"),
                (0x852110, 0x851F00, "force callback variant 5"),
            )
        ],
        "wheelSpinUpdateCallSite": {
            "rva": "0x8415b2",
            "callerRva": "0x841500",
            "targetRva": "0x843190",
        },
        "candidateScalarWriterDisposition": {
            "writerRva": "0x8295c0",
            "callerRva": "0x829950",
            "classification": "configuration descriptor conversion; not public input event decoding",
            "callInstructionRvas": ["0x829a53", "0x829aaa"],
        },
        "candidateBodyRecordWriterDisposition": {
            "writerRva": "0x819ff0",
            "callerRvas": ["0x80f5f0", "0x81a820"],
            "callInstructionRvas": ["0x80f6ea", "0x81a9cc"],
            "classification": "body interaction record assembly/registration; not public control decoding",
        },
        "inputStateDataflow": {
            "physicsUpdaterRva": "0x83de60",
            "nestedRecordOffset": "0x1280",
            "priorityValue": {
                "offset": "0x4e8",
                "storage": "signed 16-bit",
                "activation": "nonzero short OR nonzero float at subrecord +0xf4",
                "selection": "the nonzero short wins; otherwise the +0xf4 float is used",
                "verifiedBy": ["0x83dc30", "0x83dd60"],
            },
            "driveScalarUpdate": {
                "source": "0x83dd90",
                "conversionHelper": "0x1955c0",
                "threshold": "third component after quaternion-conjugate rotation of vector at subrecord +0x7c; not the untransformed +0x84 value",
                "result": "writes vehicle +0x98 as zero or the pinned binary32 one constant",
                "rawPlayerActionSemanticsVerified": False,
            },
            "brakeGating": {
                "flagTests": ["subrecord +0x4ec bit 2", "subrecord +0xf0 bit 2"],
                "secondaryModeTests": ["subrecord +0x4ec low bits == 2", "subrecord +0xf0 low bits == 2"],
                "effect": "conditionally clears vehicle +0x9c",
            },
            "higherLevelSnapshotRoute": {
                "sceneUpdater": "0x7cfce0",
                "callInstructionRva": "0x7cfda8",
                "stateBuilder": "0x7d1fa0",
                "destinationOffsetFromVehicle": "0x4e8",
                "builderCallInstructionRva": "0x7d202f",
                "copyHelper": "0x7d1380",
                "contactSummaryCallInstructionRva": "0x7d1427",
                "classification": "per-vehicle simulation-state snapshot construction; this route does not identify the raw input event source",
            },
            "recordBindingRoute": {
                "sceneUpdater": "0x7cfce0",
                "recordBindingUpdate": "0x7cfac0",
                "callInstructionRva": "0x7cfd4e",
                "modeSelector": "0x1467c90",
                "bindingTableLookup": "0x1467ca0",
                "recordIdentityCheck": "0x7c7c70 compares byte +0x13 on records; controller provenance is unverified",
                "perVehicleBindingState": {"mode": "+0x1c90", "recordPointer": "+0x1c98"},
                "copyToPhysicsControlRecord": {
                    "callInstructionRva": "0x7cfe71",
                    "destination": "vehicle +0x1280",
                    "source": "vehicle +0x1c98",
                    "bytes": "0x878",
                    "copyHelper": "0x18d7510 (overlap-safe byte copy)",
                    "condition": "binding mode at vehicle +0x1c90 equals 1",
                },
                "classification": "generic typed-record lookup and 0x878-byte state copy; raw controller provenance is unverified",
            },
            "recordAliases": {
                "vehicle+0x176a": "nested+0x4ea signed-short limit",
                "vehicle+0x176c": "nested+0x4ec flags; these are the same bytes",
            },
            "steeringDataflow": {
                "commandOffset": "vehicle+0xa0",
                "slewedOffset": "vehicle+0x1430",
                "commandReadRva": "0x8416da",
                "writeRva": "0x841734",
                "previousInterpretationCorrected": "+0x98/+0x9c feed 0x8447b0, not the steering target; their use here does not establish distinct record layouts",
            },
            "empiricalLimit": "holding vehicle +0x1374 at 0.5 in the captured 100-step fixture changed only that stored byte; rigid and force outputs did not change",
        },
        "instructions": [
            {
                "rva": hex(address),
                "bytes": bytes(instructions[address].bytes).hex(),
                "assembly": f"{instructions[address].mnemonic} {instructions[address].op_str}",
            }
            for address in sorted(expected)
        ],
        "reviewedLeafInstructions": leaf_instructions,
    }
    output = ROOT / "local/recon/vehicle-control-fields-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        "PASS VEHICLE_CONTROL_FIELDS contextual_drive_brake_steer=true "
        "steering_command_a0_pinned=true "
        "raw_control_mapping_unverified=true"
    )


if __name__ == "__main__":
    main()
