"""Package the bounded static world-tick reverse evidence, never game memory."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from reverse_physics import ROOT, SHA


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    recon = ROOT / "local/recon/ghidra-world"
    output = recon / "decompiled"
    manifest_path = recon / "manifest.json"
    report_path = output / "decompile-report.tsv"
    schedule_path = ROOT / "local/recon/scene-tick-schedule-evidence.json"
    ghidra_manifest = json.loads(manifest_path.read_text())
    schedule = json.loads(schedule_path.read_text())
    report_lines = report_path.read_text().splitlines()
    sources = sorted(output.glob("*.c"))
    if (
        ghidra_manifest.get("schema") != "tm2020_ghidra_physics_manifest_v1"
        or ghidra_manifest.get("sha256") != SHA
        or ghidra_manifest.get("functions") != 190
        or ghidra_manifest.get("automaticWholeGameAnalysisRequested") is not False
        or len(sources) != 190
        or len(report_lines) != 191
        or any(line.split("\t")[2] != "true" for line in report_lines[1:])
    ):
        raise ValueError("Incomplete or unpinned world-tick Ghidra evidence")
    if (
        schedule.get("executableSha256") != SHA
        or schedule.get("scheduler") != "fixed_integer_millisecond_catch_up"
        or schedule.get("childUpdateCallbackRva") != "0x722d90"
        or schedule.get("childUpdateCallbackExactLeafBytes") is not True
        or schedule.get("authoritativePhysicsTickBindingVerified") is not False
    ):
        raise ValueError("World-tick instruction evidence or scope changed")

    files = [manifest_path, recon / "physics-functions.tsv", report_path, schedule_path]
    files.extend(sources)
    files.extend(
        ROOT / relative
        for relative in (
            "docs/WORLD_TICK_0_26.md",
            "scripts/reverse_world_tick.py",
            "scripts/prepare_ghidra_physics.py",
            "scripts/run-ghidra-physics.ps1",
            "scripts/snapshot_world_tick_evidence.py",
        )
    )
    if any(not path.is_file() for path in files):
        raise FileNotFoundError("A world-tick evidence artifact is missing")
    entries = []
    destination = ROOT / "backups/trackmania2020-re-world-tick-0.26.0.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED, compresslevel=7) as archive:
        for path in sorted(set(files)):
            if path.suffix.lower() in {".exe", ".dll", ".tmstep", ".tmforce"}:
                raise ValueError(f"Unexpected executable or private fixture: {path}")
            if (
                path.is_relative_to(ROOT / "local")
                and path.suffix.lower() != ".c"
                and path != schedule_path
                and path
                not in {manifest_path, recon / "physics-functions.tsv", report_path}
            ):
                raise ValueError(f"Unexpected local artifact: {path}")
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
                    "schema": "tm2020_world_tick_evidence_archive_v1",
                    "executableSha256": SHA,
                    "sourceGameMemoryIncluded": False,
                    "artifacts": entries,
                },
                indent=2,
            )
            + "\n",
        )
    archive_digest = digest(destination)
    destination.with_suffix(".sha256").write_text(
        f"{archive_digest}  {destination.name}\n"
    )
    print(
        f"SAVED {destination} functions={len(sources)} artifacts={len(entries)} "
        f"bytes={destination.stat().st_size} sha256={archive_digest}"
    )


if __name__ == "__main__":
    main()
