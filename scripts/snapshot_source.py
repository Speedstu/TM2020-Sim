"""Archive only reproducible project sources, not game assets or installed packages."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED,ZipFile
ROOT=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--output",type=Path,default=ROOT/"backups"/"trackmania2020-re-source-0.33.0.zip")
DEST=p.parse_args().output.resolve()
if DEST.exists() or DEST.with_suffix(".sha256").exists():
    raise ValueError("Source snapshot never overwrites retained archives: "+str(DEST))
DEST.parent.mkdir(parents=True,exist_ok=True)
files=[]
for folder in ("src","scripts","sdk","native","openplanet","config","docs","rust","integrations"):
    for file in (ROOT/folder).rglob("*"):
        if file.is_file() and file.suffix.lower() not in {".exe",".dll",".lib",".a",".o",".so",".pdb",".gbx",".pak",".tmstep",".tmppo"} and not any(p in {"obj","bin","build","build-linux","consumer-build","__pycache__",".git","cache","target"} for p in file.relative_to(ROOT).parts):
            files.append(file)
for name in ("README.md",".gitignore","NuGet.Config","CODEX_HANDOFF_CONVERSATION.txt"):
    p=ROOT/name
    if p.is_file():files.append(p)
with ZipFile(DEST,"x",ZIP_DEFLATED,compresslevel=7) as z:
    for file in sorted(set(files)):
        z.write(file,str(file.relative_to(ROOT)).replace("\\","/"))
    manifest=[dict(path=file.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()) for file in sorted(set(files))]
    z.writestr("source-manifest.json",json.dumps(manifest,indent=2)+"\n")
with ZipFile(DEST) as z:
    if z.testzip() is not None:raise ValueError("Source archive CRC failed")
    for row in manifest:
        if hashlib.sha256(z.read(row["path"])).hexdigest()!=row["sha256"]:raise ValueError("Source archive content differs")
sha=hashlib.sha256(DEST.read_bytes()).hexdigest()
(DEST.with_suffix(".sha256")).write_text(f"{sha}  {DEST.name}\n",encoding="ascii")
print("SAVED",DEST,"files",len(files),"bytes",DEST.stat().st_size,"sha256",sha)
