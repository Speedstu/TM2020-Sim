"""Recover enqueue/deduplication and identify the unqualified activation boundary."""
import hashlib
import json
from pathlib import Path
from force_worker_fixture import require
from pinned_build import ROOT,SHA
from pe_unwind import PeCode


def main():
    exe=Path(r"D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe")
    require(hashlib.sha256(exe.read_bytes()).hexdigest()==SHA,"Unknown wake executable")
    code=PeCode(exe);rows=[]
    expected={0x7b9b74:("cmp","qword ptr [rcx + 0x100], 0"),
        0x7b9b90:("cmp","word ptr [rax + r8*8 + 4], cx"),
        0x7b9b98:("cmp","byte ptr [rax + r8*8 + 7], 1"),
        0x7b9ba0:("mov","byte ptr [rax + r8*8 + 7], 1"),
        0x7b9bb5:("call","0x13a3f00"),0x7b9bcc:("call","0x1dc0a0")}
    ins={i.address:i for i in code.instructions(0x7b9b70)}
    for at,parts in expected.items():
        i=ins[at];require((i.mnemonic,i.op_str)==parts,"Wake enqueue branch changed")
        rows.append(dict(rva=hex(at),bytes=bytes(i.bytes).hex(),assembly=i.mnemonic+" "+i.op_str))
    consumer={i.address:i for i in code.instructions(0x803920)}
    for at,parts in {0x803a05:("mov","byte ptr [rcx + 7], 0"),0x803a09:("call","0x7fc060"),0x803a2b:("call","0x10be60")}.items():
        i=consumer[at];require((i.mnemonic,i.op_str)==parts,"Wake consumer sequence changed")
        rows.append(dict(rva=hex(at),bytes=bytes(i.bytes).hex(),assembly=i.mnemonic+" "+i.op_str))
    error=None
    try:code.instructions(0x7fc060)
    except ValueError as exc:error=str(exc)
    require(error is not None,"Activation helper needs a new review")
    output=ROOT/"local/recon/wake-queue-original-evidence-0.34.json"
    require(not output.exists(),"Never overwrite wake evidence")
    output.write_text(json.dumps(dict(schema="tm2020_original_wake_enqueue_evidence_v1",exeSha256=SHA,instructions=rows,
        queuedByteOffset=7,queuedSentinel=1,inactiveIndexWord=65535,handleReverseMapOffset="capacity + body_slot",
        callbackPresenceGateOffset=256,activationHelperRva="0x7fc060",activationHelperDecodeError=error,
        queuedByteIsClearedBeforeActivation=True,activationConsumerQualified=False,
        completeExactSimulatorQualified=False),indent=2)+"\n")
    print("PINNED WAKE ENQUEUE; byte +7 is queued/dedup flag; activation remains unqualified")


if __name__=="__main__":main()
