"""Pin original instructions at guarded action-history failure frontiers.

These operands identify numeric dependencies, not guessed physical semantics.
Leaf addresses without unwind bounds are decoded for one instruction only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture
from pe_unwind import PeCode
from pinned_build import SHA


def main(args):
    require(hashlib.sha256(args.exe.read_bytes()).hexdigest()==SHA,"Unpinned executable")
    fixture=load_original_step_fixture(args.fixture)
    code=PeCode(args.exe);m=fixture.metadata;base=m["modules"][0]["base"]
    gaps={}
    for path in args.reports:
        report=json.loads(path.read_text())
        rows=report.get("plans",[])+[e for u in report.get("updates",[]) for e in u["episodes"]]
        for row in rows:
            g=row.get("firstUncapturedAccess")
            if g:gaps[(g["instructionGameRva"],g["address"])]=g
    results=[]
    for (pc,address),gap in sorted(gaps.items()):
        body=code.instructions(pc)
        instruction=next((i for i in body if i.address==pc),None)
        if instruction is None:instruction=next(code.cs.disasm(code.pe.get_data(pc,15),pc,count=1),None)
        require(instruction is not None,"Cannot decode rejected original instruction")
        rva=address-base
        section=next((s for s in code.pe.sections if s.VirtualAddress<=rva< s.VirtualAddress+s.SizeOfRawData),None)
        record=dict(instructionRva=hex(pc),instructionBytes=bytes(instruction.bytes).hex(),
            assembly=instruction.mnemonic+" "+instruction.op_str,
            unwindRootRva=hex(code.index.root(pc)) if code.index.root(pc) is not None else None,
            missingAddress=hex(address),accessBytes=gap["bytes"],
            configurationOffset=hex(address-m["configuration"]) if 0<=address-m["configuration"]<0x10000 else None,
            vehicleOffset=hex(address-m["vehicle"]) if 0<=address-m["vehicle"]<0x2000 else None,
            physicalMeaningEstablished=False)
        if section is not None and section.Name.rstrip(b"\0")==b".rdata" and gap["bytes"]==4:
            raw=code.pe.get_data(rva,4)
            record["pinnedReadonlyConstant"]=dict(rva=hex(rva),bits=raw.hex(),binary32=struct.unpack("<f",raw)[0])
        results.append(record)
    args.report.write_text(json.dumps(dict(schema="tm2020_owned_action_frontier_instructions_v1",
        executableSha256=SHA,fixtureSha256=fixture.sha256,dependencies=results,
        sourceGameProcessAccessed=False,completePhysicsQualified=False),indent=2)+"\n")
    print("PINNED ORIGINAL FRONTIER DEPENDENCIES",len(results))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("fixture","exe","report"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--reports",type=Path,nargs="+",required=True)
    main(p.parse_args())
