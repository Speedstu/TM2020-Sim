"""Verify public numeric claims against the SHA-pinned local PE, without importing them."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
import pefile

from force_worker_fixture import require
from pinned_build import SHA


def main(args):
    require(not args.output.exists(),"Never overwrite public-value evidence")
    require(hashlib.sha256(args.exe.read_bytes()).hexdigest()==SHA,"Unknown game image")
    manifest=json.loads((args.sources/"source-manifest.json").read_text())
    for source in manifest["files"]:
        require(hashlib.sha256((args.sources/source["localPath"]).read_bytes()).hexdigest()==source["sha256"],"Public evidence changed")
    path=args.sources/"sources/Kelvination-TM2020/docs/plan/07-physics-constants.md"
    text=path.read_text(encoding="utf-8-sig");pe=pefile.PE(str(args.exe),fast_load=True);rows=[]
    for line in text.splitlines():
        columns=[v.strip() for v in line.strip().strip("|").split("|")]
        if len(columns)!=5:continue
        name,value,address,context,confidence=columns
        if not re.fullmatch(r"`0x[0-9A-Fa-f]+`",address):continue
        try:expected=float(value)
        except ValueError:continue
        rva=int(address.strip("`"),16)-pe.OPTIONAL_HEADER.ImageBase
        raw=pe.get_data(rva,4);require(len(raw)==4,"Public address outside local file")
        kind="u32" if name in ("Sleep enable flag","Max iterations") else "f32"
        actual=struct.unpack("<I" if kind=="u32" else "<f",raw)[0]
        expected_bits=struct.pack("<I",int(expected)) if kind=="u32" else struct.pack("<f",expected)
        rows.append(dict(name=name,claimedValue=expected,claimedVa=address.strip("`"),rva=hex(rva),
            fileOffset=pe.get_offset_from_rva(rva),interpretation=kind,localValue=actual,localBits=raw.hex(),
            claimedBitsMatch=expected_bits==raw,
            claimedUse=context,semanticUseIndependentlyQualified=False))
    require(rows,"No numeric public source entries found")
    result=dict(schema="tm2020_public_physics_numeric_comparison_v1",exeSha256=SHA,
        sourceSha256=hashlib.sha256(path.read_bytes()).hexdigest(),sourceFilesVerified=len(manifest["files"]),
        entries=rows,matchedNumericValues=sum(r["claimedBitsMatch"] for r in rows),
        warning="A numeric byte match does not prove the documented physical interpretation or the active asset value.",
        valuesImportedIntoPhysics=False,completeExactSimulatorQualified=False)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print("PUBLIC VALUES",result["matchedNumericValues"],"/",len(rows),"typed byte matches; semantic qualification separate")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("exe","sources","output"):p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
