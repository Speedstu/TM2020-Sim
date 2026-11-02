"""Archive pinned vehicle-control field evidence without game binaries."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from reverse_physics import ROOT, SHA


def main():
    ghidra = ROOT / "local/recon/ghidra-controls"
    source = ghidra / "decompiled"
    ghidra_manifest = json.loads((ghidra / "manifest.json").read_text())
    report = json.loads(
        (ROOT / "local/recon/vehicle-control-fields-evidence.json").read_text()
    )
    names = tuple(sorted(path.name for path in source.glob("*.c")))
    decomp_report = (source / "decompile-report.tsv").read_text().splitlines()
    if (
        ghidra_manifest.get("sha256") != SHA
        or ghidra_manifest.get("functions") != 115
        or len(names) != 115
        or len(decomp_report) != 116
        or any(line.split("\t")[2] != "true" for line in decomp_report[1:])
        or report.get("executableSha256") != SHA
        or report.get("rawControlEventMappingVerified") is not False
        or report.get("offsetsAreGlobalUntypedFields") is not False
        or {"0x98", "0x9c", "0xa0", "0x1430"} != set(report.get("fields", {}))
        or [item["rva"] for item in report.get("steeringUpdateCallers", [])]
        != ["0x869e8d", "0x86b0f6", "0x86bd10", "0x852110"]
        or report.get("wheelSpinUpdateCallSite", {}).get("rva") != "0x8415b2"
        or report.get("candidateScalarWriterDisposition", {}).get("callerRva")
        != "0x829950"
        or report.get("candidateBodyRecordWriterDisposition", {}).get("callerRvas")
        != ["0x80f5f0", "0x81a820"]
        or report.get("inputStateDataflow", {}).get("physicsUpdaterRva")
        != "0x83de60"
        or report.get("inputStateDataflow", {}).get("higherLevelSnapshotRoute", {}).get("callInstructionRva")
        != "0x7cfda8"
        or report.get("inputStateDataflow", {}).get("higherLevelSnapshotRoute", {}).get("classification")
        != "per-vehicle simulation-state snapshot construction; this route does not identify the raw input event source"
        or report.get("inputStateDataflow", {}).get("recordBindingRoute", {}).get("callInstructionRva")
        != "0x7cfd4e"
        or report.get("inputStateDataflow", {}).get("recordBindingRoute", {}).get("classification")
        != "generic typed-record lookup and 0x878-byte state copy; raw controller provenance is unverified"
        or report.get("inputStateDataflow", {}).get("recordBindingRoute", {}).get("copyToPhysicsControlRecord", {}).get("callInstructionRva")
        != "0x7cfe71"
        or report.get("reviewedLeafInstructions", {}).get("0x83dc30", {}).get("assembly")
        != "movsx eax, word ptr [rcx + 0x4e8]"
        or report.get("reviewedLeafInstructions", {}).get("0x83dd78", {}).get("assembly")
        != "movss xmm0, dword ptr [rcx + 0xf4]"
    ):
        raise ValueError("Vehicle-control evidence is incomplete or unpinned")
    files = [
        ghidra / "manifest.json",
        ghidra / "physics-functions.tsv",
        source / "decompile-report.tsv",
        *(source / name for name in names),
        ROOT / "local/recon/vehicle-control-fields-evidence.json",
        ROOT / "docs/VEHICLE_CONTROL_FIELDS_0_28.md",
        ROOT / "native/include/tm2020/recovered_wheel.hpp",
        ROOT / "scripts/reverse_vehicle_control_fields.py",
        ROOT / "scripts/snapshot_vehicle_control_evidence.py",
        ROOT / "scripts/prepare_ghidra_physics.py",
        ROOT / "scripts/run-ghidra-physics.ps1",
    ]
    if any(not path.is_file() for path in files):
        raise FileNotFoundError("A vehicle-control archive member is missing")
    destination = ROOT / "backups/trackmania2020-re-vehicle-controls-0.28.0.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sorted(set(files)):
            if path.suffix.lower() in {".exe", ".dll", ".tmstep", ".tmforce"}:
                raise ValueError(f"Unexpected executable or private fixture: {path}")
            name = str(path.relative_to(ROOT)).replace("\\", "/")
            data = path.read_bytes()
            entries.append(
                {
                    "path": name,
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            archive.writestr(name, data)
        archive.writestr(
            "evidence-manifest.json",
            json.dumps(
                {
                    "schema": "tm2020_vehicle_control_evidence_archive_v1",
                    "executableSha256": SHA,
                    "rawControlEventMappingVerified": False,
                    "artifacts": entries,
                },
                indent=2,
            )
            + "\n",
        )
    archive_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".sha256").write_text(
        f"{archive_hash}  {destination.name}\n"
    )
    print(
        f"SAVED {destination} decompiled={len(names)} artifacts={len(entries)} "
        f"bytes={destination.stat().st_size} sha256={archive_hash}"
    )


if __name__ == "__main__":
    main()
