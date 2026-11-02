"""Pin the original world-scene service registry and singleton-index getters."""
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
from force_worker_fixture import require
from pe_unwind import PeCode
from pinned_build import ROOT,SHA


def main():
    exe=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
    require(hashlib.sha256(exe.read_bytes()).hexdigest()==SHA,"Unpinned original image")
    code=PeCode(exe)
    lookup=code.pe.get_data(0x6c26a0,8)
    require(lookup==bytes.fromhex("8bc2488b44c110c3"),"Service lookup changed")
    scene=code.instructions(0x12e9ea0)
    rows=[]
    for role,wrapper,getter,expected_word,callsite in (
        ("dynaManager",0x6a5b40,0x7ba440,0x2053b84,0x12e9fe6),
        ("collisionWorld",0x6a5b00,0x6c4380,0x202ddbc,0x12ea00d),
        ("vehicleForceContext",0x6b1140,0x7c5d20,0x2053bf4,0x12e9fa7)):
        body=code.instructions(wrapper)
        calls=[i for i in body if i.mnemonic=="call" and i.operands[0].type==X86_OP_IMM]
        require(len(calls)==1 and calls[0].operands[0].imm==getter
                and body[-1].mnemonic=="jmp" and body[-1].operands[0].imm==0x6c26a0,
                "Wrapper no longer delegates to expected slot lookup")
        raw=code.pe.get_data(getter,7)
        # Explicit leaf extent: six-byte RIP-relative MOV EAX and a RET.
        leaf=list(code.cs.disasm(raw,getter))
        require(len(leaf)==2 and leaf[0].size==6 and leaf[0].mnemonic=="mov"
                and leaf[0].op_str.startswith("eax, dword ptr [rip")
                and leaf[0].operands[1].type==X86_OP_MEM
                and leaf[0].operands[1].mem.base==X86_REG_RIP and leaf[1].mnemonic=="ret",
                "Slot getter is not a validated seven-byte leaf")
        word=leaf[0].address+leaf[0].size+leaf[0].operands[1].mem.disp
        require(word==expected_word,"Slot global changed")
        found=[i for i in scene if i.address==callsite and i.mnemonic=="call"
               and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==wrapper]
        require(len(found)==1,"Outer scene no longer calls this service wrapper")
        rows.append(dict(role=role,wrapperRva=hex(wrapper),slotGetterRva=hex(getter),
            slotGlobalRva=hex(word),getterBytes=raw.hex(),sceneCallRva=hex(callsite),
            sceneCallBytes=bytes(found[0].bytes).hex()))
    report=dict(schema="tm2020_scene_service_registry_static_v1",executableSha256=SHA,
        outerSceneRva="0x12e9ea0",registryPointerSceneOffset="0x7c8",
        lookupRva="0x6c26a0",lookupBytes=lookup.hex(),entryOffset=16,entryStride=8,
        indexIsUnsigned32=True,services=rows,sourceGameProcessAccessed=False,
        liveRegistryIdentityProven=False,completeSceneQualified=False)
    (ROOT/"local/recon/scene-service-registry-instructions.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PASS SCENE SERVICE REGISTRY instructions_pinned=true services=3 live_identity=false")


if __name__=="__main__":main()
