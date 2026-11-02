"""Retain commit-pinned public research text; never execute downloaded content."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path,PurePosixPath
from urllib.request import Request,urlopen

from force_worker_fixture import require


def main(args):
    root=args.folder.resolve();root.mkdir(parents=True,exist_ok=True)
    records=[]
    catalogs=json.loads((root/"repositories.json").read_text())+json.loads((root/"additional-repositories.json").read_text())
    for repo in catalogs:
        name=repo["repository"]
        tree=json.loads((root/(name.replace("/","-")+"-tree.json")).read_text())
        require(not tree.get("truncated"),"Public repository tree is incomplete")
        for entry in tree["tree"]:
            path=entry["path"]
            if entry["type"]!="blob":continue
            selected=path in ("README.md","LICENSE","LICENSE.txt")
            if name=="BigBang1112/gbx-net":
                selected |= path.startswith("Src/GBX.NET/Engines/Plug/") and any(
                    part in path for part in ("CPlugVehicleCarPhyTuning.","CPlugVehicleCarPhyShape.",
                    "CPlugVehicleMaterial.","CPlugVehiclePhyModel.","CPlugVehiclePhyTuning."))
            elif name=="Kelvination/TM2020":
                selected |= path in ("docs/plan/07-physics-constants.md","docs/plan/09-tuning-data-extraction.md",
                    "docs/plan/10-tuning-loading-analysis.md","docs/re/01-binary-overview.md",
                    "docs/re/10-physics-deep-dive.md","docs/re/14-tmnf-crossref.md",
                    "docs/re/18-validation-review.md","docs/re/class_hierarchy.json")
            elif name=="tensorfish/tmnf-c":selected |= path in ("docs/LOCAL_ASSETS.md","docs/VALIDATION.md","src/physics.h","src/vehicle_model6.h")
            elif name=="Teero888/tmuf_physics":selected |= path in ("docs/status.md","src/common/tuning_schema.h")
            if selected:
                relative=PurePosixPath(path)
                require(not relative.is_absolute() and ".." not in relative.parts and entry.get("size",0)<=5*1024**2,
                    "Unexpected source path/size")
                records.append(dict(repository=name,commit=repo["commit"],path=path,gitBlobSha1=entry["sha"]))

    # Resolve containment only after creating shared parents sequentially on Windows.
    for record in records:
        destination=root/"sources"/record["repository"].replace("/","-")/record["path"]
        destination.parent.mkdir(parents=True,exist_ok=True)
        require(destination.resolve().is_relative_to(root),"Source escaped research folder")

    def fetch(record):
        url="https://raw.githubusercontent.com/"+record["repository"]+"/"+record["commit"]+"/"+record["path"]
        request=Request(url,headers={"User-Agent":"TM2020-RE-public-evidence"})
        with urlopen(request,timeout=30) as response:raw=response.read(5*1024**2+1)
        require(len(raw)<=5*1024**2,"Public file size bound")
        git=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        require(git==record["gitBlobSha1"],"Public text differs from the pinned Git tree")
        raw.decode("utf-8-sig")
        destination=root/"sources"/record["repository"].replace("/","-")/record["path"]
        require(destination.resolve().is_relative_to(root),"Source escaped research folder: "+str(destination.resolve())+" versus "+str(root))
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():require(destination.read_bytes()==raw,"Never overwrite different retained evidence")
        else:destination.write_bytes(raw)
        return dict(**record,url=url,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            localPath=destination.relative_to(root).as_posix(),executed=False,
            currentGameOffsetsOrValuesQualified=False)

    with ThreadPoolExecutor(max_workers=4) as pool:files=list(pool.map(fetch,records))
    report=dict(schema="tm2020_public_physics_source_evidence_v1",files=files,
        executableFilesDownloaded=False,downloadedContentExecuted=False,
        currentGameValuesImported=False,completeSimulatorQualified=False)
    (root/"source-manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PUBLIC RESEARCH TEXT VERIFIED",len(files),"files; exact commits and Git blob hashes; no execution")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--folder",type=Path,required=True)
    main(p.parse_args())
