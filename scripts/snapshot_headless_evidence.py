"""Archive bounded reports and our learned artifacts; exclude proprietary assets/code."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

from force_worker_fixture import require
from pinned_build import ROOT


def main(args):
    require(not args.output.exists() and not args.output.with_suffix(".sha256").exists(),"Never overwrite retained archives")
    proof=json.loads(args.audit.read_text());require(proof["schema"]=="tm2020_headless_milestone_audit_v1","Unknown milestone audit")
    files={args.audit.resolve(),(ROOT/"local/framework-capabilities.json").resolve()}
    for relative,digest in proof["evidence"].items():
        path=(ROOT/relative).resolve(strict=True)
        require(path.is_relative_to(ROOT) and hashlib.sha256(path.read_bytes()).hexdigest()==digest,"Evidence changed after audit")
        files.add(path)
    for directory in ("headless-ppo-v3","headless-ppo-resume-v2","headless-bc-v1"):
        files.update(path.resolve() for path in (ROOT/"local/recon"/directory).rglob("*") if path.is_file()
            and path.suffix in (".json",".csv",".tmppo",".checkpoint"))
    files.update(path.resolve() for path in (ROOT/"integrations/gearbox-host").rglob("*") if path.is_file()
        and "target" not in path.parts and ".git" not in path.parts)
    files.update((ROOT/"docs"/name).resolve() for name in ("PHYSICS_0_32_OUTER_SCENE.md","PHYSICS_0_33_HEADLESS_BACKEND.md"))
    for path in files:
        require(path.is_relative_to(ROOT) and path.suffix.lower() not in (".gbx",".exe",".dll",".pak",".tmstep")
            and ".private." not in path.name,"Proprietary/local-only artifact denied")
    manifest=dict(schema="tm2020_headless_evidence_archive_v1",milestoneAuditSha256=hashlib.sha256(args.audit.read_bytes()).hexdigest(),
        containsGameAssets=False,containsGameExecutableOrInstructionBytes=False,containsExternalEngineBinaries=False,
        completeExactSimulatorQualified=False,generalPolicyQualified=False,
        artifacts=[dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for path in sorted(files)])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(args.output,"x",ZIP_DEFLATED,compresslevel=7) as archive:
        for path in sorted(files):archive.write(path,path.relative_to(ROOT).as_posix())
        archive.writestr("manifest.json",json.dumps(manifest,indent=2)+"\n")
    digest=hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(".sha256").write_text(digest+"  "+args.output.name+"\n")
    with ZipFile(args.output) as archive:
        require(archive.testzip() is None,"Archive CRC failure")
        for row in manifest["artifacts"]:
            require(hashlib.sha256(archive.read(row["path"])).hexdigest()==row["sha256"],"Archive content differs")
    print("SEALED HEADLESS EVIDENCE",len(files),"artifacts",args.output.stat().st_size,"bytes",digest)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("audit","output"):p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
