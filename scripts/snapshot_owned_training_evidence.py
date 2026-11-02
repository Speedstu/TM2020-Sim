"""Archive audited 0.31 sources/reports and the installed 0.26 SDK separately."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

from audit_owned_training import main as audit,CAPTURES
from force_worker_fixture import require
from pinned_build import ROOT,SHA


def pack(output,files,scope):
    require(not output.exists(),"Evidence archive never overwrites a retained release")
    records=[]
    with ZipFile(output,"x",ZIP_DEFLATED,compresslevel=7) as archive:
        for name,path in sorted(files):
            raw=path.read_bytes();archive.writestr(name,raw)
            records.append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        archive.writestr("evidence-manifest.json",json.dumps(dict(schema="tm2020_owned_training_evidence_v1",
            executableSha256=SHA,**scope,artifacts=records),indent=2)+"\n")
    with ZipFile(output) as archive:
        require(archive.testzip() is None and len(archive.namelist())==len(records)+1,"Archive CRC/count differs")
        for record in records:require(hashlib.sha256(archive.read(record["path"])).hexdigest()==record["sha256"],"Archive member digest differs")
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".sha256").write_text(digest+"  "+output.name+"\n")
    print("SAVED",output,"artifacts="+str(len(records)),"sha256="+digest)


def main():
    audit();recon=ROOT/"local/recon"
    names={"README.md","CODEX_HANDOFF_CONVERSATION.txt","native/CMakeLists.txt",
        "docs/PHYSICS_0_31_GUARDED_TRAINING.md","docs/PHYSICS_0_30_OWNED_SCENE.md",
        "native/src/owned_unicorn_guard.cpp","native/src/trainer_abi.cpp","native/src/policy_abi.cpp",
        "native/src/rl.cpp","native/src/training_checkpoint.cpp","native/src/rollout_audit.cpp",
        "native/include/tm2020/trainer.h","native/include/tm2020/policy.h","native/include/tm2020/rl.hpp",
        "native/tests/trainer_abi_test.cpp","native/tests/consumer/main.cpp","native/tests/consumer/CMakeLists.txt",
        "local/framework-capabilities.json"}
    scripts=("owned_native_guard","owned_step_machine","owned_ppo","train_owned_scene","evaluate_owned_ppo",
        "serve_owned_step","replay_original_step","compile_original_step_fixture","original_step_fixture",
        "force_worker_fixture","pinned_build","pe_unwind","capture_original_step","reverse_physics",
        "capture_owned_training_frontier","merge_original_step_inputs","extend_original_step_constants",
        "test_owned_native_guard","test_owned_step_machine","test_owned_step_protocol",
        "audit_owned_training","audit_owned_ppo_rollout","verify_owned_training_sdk",
        "update_owned_training_capabilities","snapshot_owned_training_evidence",
        "explore_owned_controls","reverse_owned_frontiers")
    names.update("scripts/"+s+".py" for s in scripts)
    names.add("scripts/run-owned-training-checks.ps1")
    reports=("owned-training-milestone-audit.json","owned-training-installed-sdk.json","owned-training-sdk-checks.log",
        "owned-training-final-reference.json","owned-native-guard-adversarial.json","owned-native-guard-interactive.json",
        "owned-native-guard-initialization-interactive.json","owned-native-guard-protocol.json",
        "owned-ppo-canonical-v5-evaluation.json","owned-ppo-canonical-v5-physics-audit.json",
        "owned-ppo-canonical-v5-resume-physics-audit.json","owned-action-frontier-instructions.json",
        "owned-rest-control-frontier-initial.json","owned-rest-control-frontier-expanded.json","owned-rest-control-frontier-final.json",
        "rest-history-input-union.json","rest-history-training-canonical.json",
        "rest-history-training-canonical-v2.json","rest-history-training-canonical-v3.json",
        "rest-history-training-canonical-v4.json","rest-history-training-canonical-v5.json")
    names.update("local/recon/"+n for n in reports)
    for folder in CAPTURES+["rest-history-training-canonical-v5"]:
        for path in (recon/folder).glob("*.json"):names.add(path.relative_to(ROOT).as_posix())
        capture=recon/(folder+".json")
        if capture.exists():names.add(capture.relative_to(ROOT).as_posix())
    for name in ("owned-ppo-rest-history-canonical-v5","owned-ppo-rest-history-canonical-v5-resume"):
        for path in (recon/name).rglob("*"):
            if path.is_file() and path.suffix in (".json",".csv",".tmppo",".checkpoint"):
                names.add(path.relative_to(ROOT).as_posix())
    allowed={".md",".txt",".cpp",".hpp",".h",".py",".ps1",".json",".log",".csv",".tmppo",".checkpoint"}
    files=[]
    for name in names:
        path=ROOT/name
        require(path.is_file() and (path.name=="CMakeLists.txt" or path.suffix in allowed),"Missing/unexpected artifact: "+name)
        files.append((name,path))
    backups=ROOT/"backups";backups.mkdir(exist_ok=True)
    common=dict(completeExactSimulatorQualified=False,generalRlQualified=False,
                originalGameOrOsImagesIncluded=False,privateSnapshotArchivesIncluded=False,
                rawExecutableCodePagesIncluded=False)
    pack(backups/"trackmania2020-re-guarded-training-0.31.0.zip",files,
         dict(**common,kind="research_sources_and_evidence",boundedOriginalCodePpoDecisions=360))
    sdk=ROOT/"dist/sdk-windows-x64"
    sdkfiles=[]
    for path in sdk.rglob("*"):
        if path.is_file():
            require(path.suffix.lower() in {".h",".hpp",".dll",".exe",".a",".cmake",".lib",".rs",".toml",".lock"},"Unexpected installed SDK file")
            sdkfiles.append((path.relative_to(sdk).as_posix(),path))
    pack(backups/"trackmania2020-sdk-windows-x64-0.26.0.zip",sdkfiles,
         dict(**common,kind="installed_native_sdk",sdkVersion="0.26.0",cppToolchain="MinGW GCC 15.2",nativeTrainerAbiVersion=1,
              rustInferenceBindingVersion="0.25.0",rustTrainerBindingIncluded=False))


if __name__=="__main__":main()
