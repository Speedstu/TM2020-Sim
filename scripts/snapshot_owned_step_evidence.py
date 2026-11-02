"""Archive audited research sources/reports; exclude snapshots and original images."""
import hashlib
import json
from types import SimpleNamespace
from zipfile import ZipFile,ZIP_DEFLATED
from pinned_build import ROOT,SHA
from force_worker_fixture import require
from audit_owned_step_continuation import audit
from audit_owned_input_coverage import main as audit_input_coverage
from audit_preserved_velocity_steps import main as audit_preserved_velocity


def main():
    recon=ROOT/"local/recon"
    audit(SimpleNamespace(report=recon/"owned-step-continuation-audit.json"))
    audit_input_coverage()
    audit_preserved_velocity()
    for name,cases in (("vehicle-substep-selector-oracle.json",20000),
                       ("vehicle-substep-motion-oracle.json",20000),
                       ("vehicle-substep-selector-observed-oracle.json",20500)):
        oracle=json.loads((recon/name).read_text())
        require(oracle["executableSha256"]==SHA and oracle["bitExact"] is True
                and oracle["cases"]==cases and oracle["completeSceneSchedulerQualified"] is False
                and oracle["portableSourceSha256"]==hashlib.sha256((ROOT/"native/src/recovered_step.cpp").read_bytes()).hexdigest()
                and oracle["portableHeaderSha256"]==hashlib.sha256((ROOT/"native/include/tm2020/recovered_step.hpp").read_bytes()).hexdigest(),
                "Substep arithmetic oracle is stale or incomplete: "+name)
        if cases==20500:
            require(oracle["observedSelectorFramesCompared"]==500
                    and oracle["observedSceneIntervalsCompared"] is True
                    and oracle["observedReplayReportSha256"]==hashlib.sha256((recon/"original-step-offline-source424-rest-500.json").read_bytes()).hexdigest(),
                    "Observed substep oracle does not cover the 500-tick source episode")
    result=json.loads((recon/"owned-step-continuation-audit.json").read_text())
    require(result["completeStandaloneSimulatorQualified"] is False
            and result["originalSourceVehicleContactPathExercised"] is True,"Unexpected research scope")
    names=["README.md","native/CMakeLists.txt","native/src/manager_discovery.cpp",
        "native/src/original_step_native.cpp","native/include/tm2020/read_only_live.hpp",
        "native/src/recovered_activation.cpp","native/include/tm2020/recovered_activation.hpp",
        "native/src/recovered_step.cpp","native/include/tm2020/recovered_step.hpp",
        "native/tests/vehicle_substep_probe.cpp","native/tests/vehicle_substep_test.cpp",
        "native/tests/vehicle_motion_probe.cpp","scripts/oracle_vehicle_motion.py",
        "native/tests/consumer/main.cpp","native/tests/consumer/CMakeLists.txt",
        "local/recon/owned-scene-installed-sdk.json",
        "scripts/audit_preserved_velocity_steps.py","local/recon/preserved-source-velocity-audit.json",
        "scripts/run-preserved-velocity-checks.ps1",
        "scripts/oracle_vehicle_substeps.py","scripts/run-vehicle-substep-checks.ps1",
        "local/recon/vehicle-substep-selector-oracle.json",
        "local/recon/vehicle-substep-motion-oracle.json",
        "local/recon/vehicle-substep-selector-observed-oracle.json",
        "local/recon/original-step-offline-source424-rest-selector.json",
        "scripts/capture_original_step.py","scripts/compile_original_step_fixture.py",
        "scripts/original_step_fixture.py","scripts/force_worker_fixture.py","scripts/pe_unwind.py",
        "scripts/reverse_physics.py","scripts/pinned_build.py","scripts/replay_original_step.py",
        "scripts/owned_step_machine.py","scripts/serve_owned_step.py",
        "scripts/merge_original_step_inputs.py","scripts/test_merge_original_step_inputs.py",
        "scripts/capture_owned_action_inputs.py","scripts/audit_owned_action_grid.py",
        "scripts/audit_owned_input_coverage.py","scripts/run-owned-input-checks.ps1",
        "scripts/inspect_owned_input_gaps.py","local/recon/owned-source-input-gap-instructions.json",
        "scripts/test_owned_step_machine.py","scripts/test_owned_step_protocol.py",
        "scripts/test_original_step_fixture.py","scripts/test_original_step_native_controls.py",
        "scripts/audit_original_step_control_response.py","scripts/audit_owned_step_continuation.py",
        "scripts/reverse_wheel_contact_pipeline.py","scripts/run-owned-step-checks.ps1",
        "scripts/run-ghidra-physics.ps1","scripts/prepare_ghidra_physics.py",
        "scripts/ghidra/TM2020Physics.java","scripts/snapshot_owned_step_evidence.py",
        "docs/PHYSICS_0_30_OWNED_SCENE.md","docs/PHYSICS_0_29_CONTROL_GUARD.md",
        "local/framework-capabilities.json","local/recon/owned-step-continuation-audit.json",
        "local/recon/owned-interactive-step-qualification.json","local/recon/owned-step-json-protocol.json",
        "local/recon/native-pipeline-reset-rejection.json","local/recon/native-control-reset-rejection.json",
        "local/recon/wheel-contact-pipeline-evidence.json","local/recon/pedal-control-response-v6.json",
        "local/recon/control-parameters-v6-pedals.json","local/recon/physics-binding-21688-solo-v3.json",
        "local/recon/mixed-controls-300.json","local/recon/pedal-pulse-schedule.json",
        "local/recon/pedal-baseline-schedule.json"]
    for suffix in ("v6-pedals","v6-pedal-baseline","v6-mixed-300","postcontact-pedals",
                   "vehiclescene-pedals","posesync-pedals","querycycle-pedals",
                   "sourceactivation-pedals","sourceactivation-mixed-300",
                   "source424-pedals","source424-mixed-300","source424-input-union",
                   "source424-rest-throttle","source424-rest-500"):
        for pattern in ("original-step-capture-{}.json","original-step-offline-{}.json"):
            path=recon/pattern.format(suffix)
            if path.is_file():names.append(path.relative_to(ROOT).as_posix())
        folder=recon/("main-step-fixtures-"+suffix)
        if folder.exists():
            names.extend(path.relative_to(ROOT).as_posix() for path in folder.glob("*.json"))
    for name in ("physics-binding-424-solo-v2.json","source424-action-inputs.json",
                 "source424-observed-input-union.json","owned-source424-interactive.json",
                 "owned-source424-protocol.json","owned-source424-action-grid.json",
                 "owned-input-coverage-audit.json","native-source424-input-rejection.json"):
        names.append("local/recon/"+name)
    for folder in (recon/"source424-action-inputs",recon/"owned-source424-action-grid"):
        names.extend(path.relative_to(ROOT).as_posix() for path in folder.rglob("*.json"))
    names.append("local/recon/original-step-wheel-diagnostics-v6-mixed-300.json")
    for version in ("v3","v4","v5","v6","v7-p1","v7-p2"):
        names.append("local/recon/reset-compat-"+version+".json")
    ghidra=recon/"ghidra-wheelpipeline"
    manifest=json.loads((ghidra/"manifest.json").read_text())
    rows=(ghidra/"decompiled/decompile-report.tsv").read_text().splitlines()[1:]
    sources=list((ghidra/"decompiled").glob("*.c"))
    require(manifest["sha256"]==SHA and manifest["functions"]==len(rows)==len(sources)
            and all(row.split("\t")[2]=="true" for row in rows),"Incomplete wheel-pipeline decompilation")
    names.extend(path.relative_to(ROOT).as_posix() for path in
        [ghidra/"manifest.json",ghidra/"physics-functions.tsv",ghidra/"decompiled/decompile-report.tsv",*sources])
    output=ROOT/"backups/trackmania2020-re-owned-scene-0.30.0.zip"
    output.parent.mkdir(parents=True,exist_ok=True)
    files=[]
    for name in sorted(set(names)):
        path=ROOT/name
        require(path.is_file() and (path.name=="CMakeLists.txt" or path.suffix.lower() in {".md",".cpp",".hpp",".c",".py",".ps1",".java",".json",".tsv"}),
                "Missing or unexpected artifact: "+name)
        files.append((name,path.read_bytes()))
    records=[dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for name,raw in files]
    with ZipFile(output,"w",ZIP_DEFLATED,compresslevel=7) as archive:
        for name,raw in files:archive.writestr(name,raw)
        archive.writestr("evidence-manifest.json",json.dumps(dict(
            schema="tm2020_owned_scene_evidence_v1",executableSha256=SHA,
            sourceIntegrationBranchExercised=True,completeStandaloneSimulatorQualified=False,
            fullTrackmaniaHeadlessRLReady=False,privateNumericSnapshotArchivesIncluded=False,
            originalExecutableImagesIncluded=False,rawExecutableCodePagesIncluded=False,
            selectedInstructionEvidenceIncluded=True,decompilerResearchSourcesIncluded=True,
            artifacts=records),indent=2)+"\n")
    with ZipFile(output) as archive:
        require(archive.testzip() is None and len(archive.namelist())==len(records)+1,
                "Evidence archive integrity failed")
        for record in records:
            require(hashlib.sha256(archive.read(record["path"])).hexdigest()==record["sha256"],
                    "Evidence archive digest differs")
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".sha256").write_text(digest+"  "+output.name+"\n")
    print("SAVED",output,"artifacts="+str(len(records)),"sha256="+digest)


if __name__=="__main__":main()
