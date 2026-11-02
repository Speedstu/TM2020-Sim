"""Reuse retained arithmetic evidence only for byte-identical qualified libraries."""

import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from pinned_build import ROOT, SHA


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    release = json.loads(
        (ROOT / "local/release-0.24.0.json").read_text(encoding="utf-8-sig")
    )
    if not (
        release["recoveredArithmeticPhysicsOperations"] == 72
        and release["installedCppConsumerValidated"]
    ):
        raise ValueError("Prior installed release was not qualified")
    archives = {}
    for kind in ("source", "physics-evidence"):
        path = ROOT / "backups" / f"trackmania2020-re-{kind}-0.24.0.zip"
        value = digest(path)
        if value != path.with_suffix(".sha256").read_text().split()[0]:
            raise ValueError("Retained qualified archive checksum changed")
        archives[kind] = value
    library = ROOT / "native/build/libtm2020_sdk.a"
    installed = ROOT / "dist/sdk-windows-x64/lib/libtm2020_sdk.a"
    current = digest(library)
    # Preserve the release binding before a subsequent installation replaces it.
    binding_path = ROOT / "local/recon/qualified-kernel-library-0.24.0.json"
    if binding_path.exists():
        binding = json.loads(binding_path.read_text())
        if binding["qualifiedSourceArchiveSha256"] != archives["source"]:
            raise ValueError("Prior library/source binding changed")
    else:
        version = (
            ROOT / "dist/sdk-windows-x64/lib/cmake/tm2020/tm2020ConfigVersion.cmake"
        ).read_text()
        if "0.24.0" not in version or digest(installed) != current:
            raise ValueError(
                "Current library is not identical to the installed qualified 0.24 release"
            )
        binding = dict(
            schema="tm2020_qualified_library_binding_v1",
            qualifiedSourceArchiveSha256=archives["source"],
            librarySha256=current,
        )
        with binding_path.open("x") as target:
            json.dump(binding, target, indent=2)
            target.write("\n")
    if current != binding["librarySha256"]:
        raise ValueError(
            "Arithmetic/PPO SDK binary changed: rerun the original full differentials"
        )
    checked_sources = 0
    with ZipFile(ROOT / "backups/trackmania2020-re-source-0.24.0.zip") as source:
        for name in source.namelist():
            if (
                name.startswith(("native/src/", "native/include/"))
                or name.startswith("scripts/test_recovered_")
                or name == "scripts/pe_unwind.py"
            ):
                if source.read(name) != (ROOT / name).read_bytes():
                    raise ValueError("Qualified implementation changed: " + name)
                checked_sources += 1
    checked_reports = 0
    with ZipFile(
        ROOT / "backups/trackmania2020-re-physics-evidence-0.24.0.zip"
    ) as evidence:
        manifest = json.loads(evidence.read("evidence-manifest.json"))
        for entry in manifest["artifacts"]:
            name = entry["path"]
            if name.endswith(".json") and "oracle" in name:
                if digest(ROOT / name) != entry["sha256"]:
                    raise ValueError(
                        "Retained original-instruction proof changed: " + name
                    )
                checked_reports += 1
    if checked_sources < 80 or checked_reports < 25:
        raise ValueError("Incomplete qualified evidence inventory")
    report = dict(
        schema="tm2020_reused_qualified_physics_v1",
        sha256=SHA,
        reusedFromRelease="0.24.0",
        qualifiedLibrarySha256=current,
        archiveSha256=archives,
        identicalQualifiedSourceFiles=checked_sources,
        identicalOriginalInstructionReports=checked_reports,
        newOriginalKernelDifferentialsRun=False,
        note="The arithmetic/PPO library bytes and qualified sources/reports are unchanged; new backend checks run separately.",
    )
    (ROOT / "local/recon/reused-qualified-physics.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        "PASS REUSED QUALIFIED PHYSICS library_bit_identical=true sources=",
        checked_sources,
        "reports=",
        checked_reports,
    )


if __name__ == "__main__":
    main()
