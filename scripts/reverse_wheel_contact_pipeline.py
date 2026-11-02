"""Pin wheel-contact producers, consumption/clear order and scene continuation.

Static instructions are evidence of code structure, not proof of live dispatch.
"""
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM
from force_worker_fixture import require
from pe_unwind import PeCode
from pinned_build import ROOT,SHA


def main():
    exe=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
    require(hashlib.sha256(exe.read_bytes()).hexdigest()==SHA,"Unknown game build")
    code=PeCode(exe)
    def calls(root,target):
        return [i for i in code.instructions(root) if i.mnemonic=="call"
                and i.operands[0].type==X86_OP_IMM and i.operands[0].imm==target]
    links=[(0x12e9ea0,0x7bd0e0,0x12eb053),(0x12e9ea0,0x2a9b50,0x12eb05c),
           (0x12e9ea0,0x7bfcb0,0x12eb065),(0x12e9ea0,0x7d2b90,0x12eb079),
           (0x12e9ea0,0x7d2cf0,0x12eb2b7),
           (0x1500140,0x840890,0x1500429),(0x840890,0x843920,0x840fd0)]
    evidence=[]
    def row(root,ins):
        return dict(rootRva=hex(root),rva=hex(ins.address),bytes=bytes(ins.bytes).hex(),
                    assembly=ins.mnemonic+" "+ins.op_str)
    for root,target,at in links:
        matches=calls(root,target)
        require(len(matches)==1 and matches[0].address==at,"Contact call site changed")
        evidence.append(row(root,matches[0]))
    scene_fixed_calls={0x7f4780:[0x15019c4],0x14ffee0:[0x1501c6a,0x1501d71],
                       0x14ff9d0:[0x1501c79,0x1501d7f],0x15009d0:[0x1501ca6,0x1501db0]}
    for target,expected in scene_fixed_calls.items():
        actual=calls(0x1501800,target)
        require([i.address for i in actual]==expected,"Fixed-body vehicle integration calls changed")
        evidence.extend(row(0x1501800,i) for i in actual)
    contact_adapter=calls(0x15009d0,0x1500140)
    require(len(contact_adapter)==1 and contact_adapter[0].address==0x1500ff5,
            "Vehicle substep contact adapter call changed")
    evidence.append(row(0x15009d0,contact_adapter[0]))
    scene_ins=code.instructions(0x1501800)
    for at in (0x15019c9,0x15019cb):
        found=[i for i in scene_ins if i.address==at]
        require(len(found)==1,"Missing fixed-body vehicle branch")
        evidence.append(row(0x1501800,found[0]))
    # The force callback consumes wheel flags, then clears all four before
    # returning. A zero at an end-of-step boundary cannot prove zero on entry.
    ins=code.instructions(0x8427d0)
    writes=[]
    for offset in (0x17b4,0x186c,0x1924,0x19dc):
        selected=[i for i in ins if i.mnemonic=="mov" and i.operands[0].type==X86_OP_MEM
                  and i.operands[0].mem.disp==offset and i.op_str.endswith(", r12d")]
        require(len(selected)==1,"Wheel-flag clear changed")
        writes.append(selected[0])
        evidence.append(row(0x8427d0,selected[0]))
    variant=calls(0x8427d0,0x851f00)
    require(len(variant)==1 and variant[0].address<min(i.address for i in writes),
            "Variant-5 update no longer precedes contact-flag clearing")
    evidence.append(row(0x8427d0,variant[0]))
    for root,offset in ((0x843190,0x17b4),(0x8447b0,0x17b4),
                        (0x843920,0x17b4),(0x83cc90,0x17d4)):
        matches=[i for i in code.instructions(root) if any(o.type==X86_OP_MEM
                 and o.mem.disp==offset for o in i.operands)]
        require(matches,"Missing wheel-contact field reference")
        evidence.extend(row(root,i) for i in matches)
    pose_copies=[]
    for offset in (0x12f0,0x12f8,0x12fc,0x1304,0x1308,0x1310):
        matches=[i for i in code.instructions(0x7d2cf0) if i.mnemonic.startswith("mov")
                 and i.operands[0].type==X86_OP_MEM and i.operands[0].mem.disp==offset]
        require(matches,"Missing original rigid-to-vehicle copy")
        pose_copies.extend(row(0x7d2cf0,i) for i in matches)
    evidence.extend(pose_copies)
    ranges={hex(root):[[hex(r.begin),hex(r.end)] for r in code.index.groups[root]]
            for root in {r for r,_,_ in links}|{0x8427d0,0x843190,0x8447b0,0x843920,0x83cc90,
                0x7d2cf0,0x1501800,0x15009d0,0x14ffee0,0x14ff9d0}}
    output=ROOT/"local/recon/wheel-contact-pipeline-evidence.json"
    output.write_text(json.dumps(dict(schema="tm2020_wheel_contact_pipeline_evidence_v1",
        executableSha256=SHA,instructions=evidence,completeUnwindRanges=ranges,
        sceneContinuationAfterMainStep=["0x2a9b50","0x7bfcb0","0x7d2b90"],
        wheelFlagOffsets=["0x17b4","0x186c","0x1924","0x19dc"],
        wheelFlagsClearedAfterVariant5=True,stepBoundaryZeroDoesNotProveAirborne=True,
        bodyToVehiclePoseSynchronizationRva="0x7d2cf0",
        fixedBodySceneVehicleIntegrationRva="0x1501800",
        fixedBodyVehicleContactSequence=["0x14ffee0","0x14ff9d0","0x15009d0","0x1500140","0x840890","0x843920"],
        sceneContinuationIsCompleteSceneUpdate=False,liveInvocationQualified=False,
        completeTirePhysicsQualified=False),indent=2)+"\n")
    print("PASS WHEEL_CONTACT_PIPELINE static_calls="+str(len(links))+" rigid_to_vehicle_sync_pinned=true")


if __name__=="__main__":main()
