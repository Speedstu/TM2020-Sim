"""Bundle the 0.29 research sources and bounded evidence, excluding private inputs."""
import hashlib
import json
from zipfile import ZipFile, ZIP_DEFLATED
from pinned_build import ROOT, SHA
from force_worker_fixture import require


def main():
    recon=ROOT/"local/recon"
    def read(name):return json.loads((recon/name).read_text())
    guard=read("control-guard-oracle.json")
    response=read("steering-command-response.json")
    old=read("steering-state-response.json")
    native=read("main-step-control-scenarios/steering-command-a0/native-result.json")
    rejected=read("native-control-rejection.json")
    require(guard["sha256"]==SHA and guard["bit_exact"] is True
            and guard["cases_per_operation"]==20000 and guard["operations"]==3
            and guard["whole_vehicle_bytes_checked"] is True,"Missing portable guard qualification")
    require(response["physicalActionResponseObserved"] is True
            and response["records"][0]["firstChangedTick"]==51
            and response["records"][0]["changedFrames"]==50
            and response["steeringOverrideOffset"]==0xa0
            and response["ticksCompared"]==100
            and response["fullSimulatorQualified"] is False
            and old["physicalActionResponseObserved"] is False,"Missing response distinction")
    require(native["sha256"]==SHA and native["typedFramesCompared"]==100
            and native["nativeFixtureVersion"]==6 and native["steeringOverrideOffset"]==0xa0
            and native["allTypedPhysicalFramesBitExact"] is True
            and native["completeMainProcedureReturnedEveryFrame"] is True
            and native["sourceFixtureSha256"]==response["scenarioFixtureSha256"]
            and native["fullHeadlessSimulatorQualified"] is False,"Missing native command qualification")
    require(rejected["allRejectedBeforeStep"] is True and len(rejected["cases"])==4,
            "Missing native input rejection checks")
    files=[ROOT/name for name in (
        "README.md","native/CMakeLists.txt",
        "native/include/tm2020/recovered_control_guard.hpp",
        "native/src/recovered_control_guard.cpp","native/tests/control_guard_oracle.cpp",
        "native/tests/control_guard_test.cpp","native/tests/owned_arithmetic_image.hpp",
        "native/src/original_step_native.cpp","scripts/run-control-guard-checks.ps1",
        "scripts/replay_original_step.py","scripts/compile_original_step_fixture.py",
        "scripts/original_step_fixture.py","scripts/test_original_step_fixture.py",
        "scripts/extend_original_step_constants.py","scripts/audit_original_step_control_response.py",
        "scripts/test_original_step_native_controls.py","scripts/reverse_vehicle_control_fields.py",
        "scripts/prepare_ghidra_physics.py","scripts/run-ghidra-physics.ps1",
        "scripts/ghidra/TM2020Physics.java","scripts/snapshot_control_guard_evidence.py",
        "docs/PHYSICS_0_29_CONTROL_GUARD.md","docs/PHYSICS_0_28_COUNTERFACTUAL.md",
        "docs/VEHICLE_CONTROL_FIELDS_0_28.md",
        "local/recon/control-guard-oracle.json","local/recon/steering-command-response.json",
        "local/recon/steering-state-response.json","local/recon/native-control-rejection.json",
        "local/recon/vehicle-control-fields-evidence.json",
        "local/recon/main-step-control-scenarios/steering-command-a0/native-input.json",
        "local/recon/main-step-control-scenarios/steering-command-a0/native-result.json",
        "local/recon/original-step-native-results-v5/compat-v3.json",
        "local/recon/main-step-control-scenarios/action-axis050/compat-v4.json",
        "local/recon/main-step-control-scenarios/variable-steering/compat-v5.json")]
    for folder,count in (("ghidra-controls",115),("ghidra-inputsource",56)):
        source=recon/folder
        manifest=json.loads((source/"manifest.json").read_text())
        lines=(source/"decompiled/decompile-report.tsv").read_text().splitlines()
        names=tuple((source/"decompiled").glob("*.c"))
        require(manifest["sha256"]==SHA and manifest["functions"]==count
                and len(names)==count and len(lines)==count+1
                and all(line.split("\t")[2]=="true" for line in lines[1:]),
                "Incomplete bounded decompilation")
        files.extend([source/"manifest.json",source/"physics-functions.tsv",
                      source/"decompiled/decompile-report.tsv",*names])
    failures=[]
    for filename in ("pedal-pulse-counterfactual.json","pedal-pulse-extended-counterfactual.json"):
        failure=read(filename)["fixtures"][0]
        require(failure["completed"] is False and failure["faultReasons"],
                "Pedal trial must retain its failure classification")
        failures.append(dict(report=filename,completed=False,
                             classification="uncaptured working-set data; no physical or native qualification"))
    destination=ROOT/"backups/trackmania2020-re-control-guard-0.29.0.zip"
    destination.parent.mkdir(parents=True,exist_ok=True)
    for path in files:
        require(path.is_file() and path.suffix.lower() in
                {".md",".txt",".hpp",".cpp",".c",".py",".ps1",".java",".json",".tsv"},
                "Unexpected or missing evidence artifact: "+path.relative_to(ROOT).as_posix())
    entries=[]
    with ZipFile(destination,"w",ZIP_DEFLATED,compresslevel=7) as archive:
        for path in sorted(set(files)):
            name=path.relative_to(ROOT).as_posix();raw=path.read_bytes()
            archive.writestr(name,raw)
            entries.append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        archive.writestr("evidence-manifest.json",json.dumps(dict(
            schema="tm2020_control_guard_evidence_v1",executableSha256=SHA,
            portableOperationsAdded=3,casesPerOperation=20000,
            boundedSteeringPhysicalResponseObserved=True,rawActionMappingQualified=False,
            completeStandaloneSimulatorQualified=False,privateNumericInputsIncluded=False,
            failedPedalTrials=failures,artifacts=entries),indent=2)+"\n")
    with ZipFile(destination) as archive:require(archive.testzip() is None,"Archive integrity failure")
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".sha256").write_text(f"{digest}  {destination.name}\n")
    print("SAVED",destination,"artifacts="+str(len(entries)),"sha256="+digest)


if __name__=="__main__":main()
