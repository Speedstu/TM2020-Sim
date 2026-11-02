"""Add explicitly selected pinned .rdata constants to an owned sparse fixture."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from force_worker_fixture import require
from original_step_fixture import load_original_step_fixture, verify_original_step_images


def extend(args):
    require(not args.output.exists(), "Constant extension never overwrites a fixture")
    fixture=load_original_step_fixture(args.fixture)
    image=verify_original_step_images(fixture,(args.exe,args.ntdll,args.kernel32))[0]
    require(0<args.bytes<=64 and args.rva%4==0 and args.bytes%4==0,
            "Only a bounded explicit binary32 constant span is supported")
    require(any(s.Name.rstrip(b"\0")==b".rdata" and not s.Characteristics&0xa0000000
                and s.VirtualAddress<=args.rva and args.rva+args.bytes<=s.VirtualAddress+s.SizeOfRawData
                for s in image.sections), "Constant must be file-backed read-only nonexecutable .rdata")
    raw=image.get_data(args.rva,args.bytes)
    require(len(raw)==args.bytes,"Truncated constant")
    m=copy.deepcopy(fixture.metadata)
    extensions=m.setdefault("pinnedReadonlyConstantExtensions",[])
    require(len(extensions)<16,"Constant extension count bound")
    extensions.append(dict(module=0,rva=args.rva,bytes=args.bytes,
                           sha256=hashlib.sha256(raw).hexdigest(),
                           provenance="pinned file .rdata; not a live capture"))
    m["derivedConstantSourceFixtureSha256"]=fixture.sha256
    payloads={}
    for j,value in enumerate(raw):
        address=m["modules"][0]["base"]+args.rva+j
        page,offset=address&~4095,address&4095
        name=f"data/{page:016x}.bin"
        if name not in payloads:
            prior=fixture.pages.get(page)
            payloads[name]=bytearray(prior.mask+prior.initial+prior.expected) if prior else bytearray(12288)
        blob=payloads[name]
        if blob[offset]:
            require(blob[4096+offset]==blob[8192+offset]==value,
                    "Captured constant differs from pinned file")
        blob[offset]=1;blob[4096+offset]=value;blob[8192+offset]=value
    by_name={r["file"]:r for r in m["dataPages"]}
    for name,blob in payloads.items():
        if name not in by_name:
            by_name[name]=dict(file=name,address=int(Path(name).stem,16))
        by_name[name]["sha256"]=hashlib.sha256(blob).hexdigest()
    m["dataPages"]=sorted(by_name.values(),key=lambda r:r["address"])
    payloads["metadata.json"]=(json.dumps(m,indent=2)+"\n").encode()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(args.fixture) as source,ZipFile(args.output,"x",ZIP_DEFLATED) as destination:
        for item in source.infolist():
            destination.writestr(item.filename,payloads.pop(item.filename,source.read(item.filename)))
        for name,blob in payloads.items():destination.writestr(name,blob)
    verified=load_original_step_fixture(args.output)
    verify_original_step_images(verified,(args.exe,args.ntdll,args.kernel32))
    print("PASS PINNED_CONSTANT_EXTENSION",hex(args.rva),"bytes="+str(args.bytes),"live_reads=false")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--exe",type=Path,required=True)
    p.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    p.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    p.add_argument("--rva",type=lambda v:int(v,0),required=True)
    p.add_argument("--bytes",type=int,required=True)
    extend(p.parse_args())
