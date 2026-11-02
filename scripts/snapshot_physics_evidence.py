"""Archive explicit local physics proof artifacts, never an executable/asset dump."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
files=[ROOT/p for p in (
    'local/recon/original-step-capture-v5.json','local/recon/original-step-offline-v5.json',
    'local/recon/original-step-qualification.json','local/recon/reused-qualified-physics.json',
    'local/recon/qualified-kernel-library-0.24.0.json',
    'local/physics-research-0.25.0.json','local/release-0.25.0.json','local/release-checks-0.25.0.log',
    'local/physics-installed-consumer-0.25.0.log',

    'local/recon/force-worker-capture-v5.json','local/recon/offline-force-worker-v5.json',
    'local/recon/force-worker-qualification.json','local/recon/main-step-code-boundary.json',
    'local/physics-research-0.24.0.json','local/release-0.24.0.json','local/release-checks-0.24.0.log',
    'local/physics-installed-consumer-0.24.0.log',
    'local/force-worker-final-0.24.0.log','local/force-fixture-final-bounds-build.log',
    'local/force-worker-final-install-0.24.0.log','local/ctest-0.24.0-restored.log',
    'local/recon/owned-live-main-step-preallocated-sse-v8.json','local/recon/owned-live-main-step-preallocated-v7.json',
    'local/recon/owned-live-main-step-instruction-guard-v9.json','local/recon/owned-live-main-step-with-ntdll-v11.json',
    'local/recon/owned-live-main-step-owned-thread-v12.json',

    'local/recon/steering-surface-evidence.json','local/recon/recovered-steering-surface-oracle.json',
    'local/recon/effective-vehicle-26616-v6.json','local/physics-research-0.22.0.json','local/release-0.22.0.json',
    'local/release-checks-0.22.0.log','local/physics-installed-consumer-0.22.0.log',
    'local/recon/activation-evidence.json','local/recon/recovered-activation-oracle.json','local/recon/step-timing-evidence.json',
    'local/recon/effective-vehicle-26616-v5.json','local/physics-research-0.21.0.json','local/release-0.21.0.json',
    'local/release-checks-0.21.0.log','local/physics-installed-consumer-0.21.0.log',
    'local/recon/recovered-step-parameter-oracle.json','local/recon/step-parameter-evidence.json','local/recon/force-context-evidence.json',
    'local/recon/effective-vehicle-26616-v4.json','local/physics-research-0.20.0.json','local/release-0.20.0.json',
    'local/release-checks-0.20.0.log','local/physics-installed-consumer-0.20.0.log',
    'local/physics-research-0.23.0.json','local/release-0.23.0.json','local/release-checks-0.23.0.log',
    'local/physics-installed-consumer-0.23.0.log','local/recon/effective-vehicle-26616-v7.json',
    'local/recon/surface-material-names.json','local/recon/captured-collision-replay-26616.json','local/recon/captured-geometry-qualification.json',
    'local/recon/live-meshes-26616-v2.jsonl','local/recon/live-meshes-26616-v2.log','local/recon/live-geometry-26616-v2.log',
    'local/recon/live-geometry-26616-v2/summary.json','local/recon/live-geometry-26616-v2/meshes.jsonl','local/recon/live-geometry-26616-v2/instances.jsonl',
    'local/recon/captured-ray-audit/qualification.json','local/recon/captured-ray-audit/rays.txt','local/recon/captured-ray-audit/native-output.jsonl',
    'local/collision-maps/ypPmohQofd72MyTsIsijKfrJH98-live-meshes.json',
    'local/physics-research-0.19.0.json','local/release-0.19.0.json','local/release-checks-0.19.0.log',
    'local/physics-installed-consumer-0.19.0.log','local/recon/recovered-position-fma-oracle.json',
    'local/recon/effective-vehicle-26616-v3.json','local/recon/effective-materials-26616.bin','local/recon/effective-materials-qualification.json',
    'local/recon/rigid-mesh-fma-trace.csv','local/recon/rigid-mesh-fma-demo.json',
    'local/recon/live-cpp-26616-v3.txt','local/recon/live-cpp-26616.csv','local/recon/live-26616-bootstrap.log',
    'local/physics-research-0.18.0.json','local/release-0.18.0.json','local/release-checks-0.18.0.log',
    'local/physics-installed-consumer-0.18.0.log','local/recon/recovered-resistance-oracle.json',
    'local/physics-research-0.17.0.json','local/release-0.17.0.json','local/release-checks-0.17.0.log',
    'local/physics-installed-consumer-0.17.0.log','local/recon/recovered-wheel-material-oracle.json',
    'local/physics-research-0.16.0.json','local/release-0.16.0.json','local/release-checks-0.16.0.log',
    'local/physics-installed-consumer-0.16.0.log',
    'local/recon/recovered-joint-position-oracle.json','local/recon/recovered-frame-oracle.json',
    'local/recon/position-island-oracle/recovered-position-island-oracle.json',
    'local/recon/position-island-oracle/position-island-input.bin','local/recon/position-island-oracle/position-island-ported.bin',
    'local/physics-research-0.15.0.json','local/release-0.15.0.json','local/release-checks-0.15.0.log',
    'local/physics-installed-consumer-0.15.0.log',
    'local/recon/mesh-convex-evidence.json','local/recon/vehicle-arithmetic-evidence.json','local/recon/geometry-vehicle-qualification.json',
    'local/recon/recovered-features-oracle.json',
    'local/recon/recovered-joints-oracle.json',
    'local/recon/recovered-vehicle-auxiliary-oracle.json',
    'local/recon/recovered-wheel-update-oracle.json','local/recon/recovered-wheel-spin-oracle.json',
    'local/recon/patch-oracle/recovered-patch-oracle.json','local/recon/patch-oracle/patch-input.bin','local/recon/patch-oracle/patch-ported.bin',
    'local/recon/rigid-mesh-demo.json','local/recon/rigid-mesh-trace.csv',
    'local/standalone-world-validation/report.json','local/standalone-world-validation/trace.csv',
    'local/recon/joint-solver-oracle/recovered-solver-oracle.json','local/recon/joint-solver-oracle/solver-input.bin','local/recon/joint-solver-oracle/solver-ported.bin',
    'local/recon/convex-collision-oracle/recovered-convex-collision-oracle.json',
    'local/recon/convex-collision-oracle/convex-input.bin','local/recon/convex-collision-oracle/convex-ported.bin',
    'local/recon/convex-mesh-oracle/recovered-convex-mesh-oracle.json',
    'local/recon/convex-mesh-oracle/convex-mesh-input.bin','local/recon/convex-mesh-oracle/convex-mesh-ported.bin',
    'local/recon/convex-mesh-oracle/convex-mesh-cap-input.bin','local/recon/convex-mesh-oracle/convex-mesh-cap-ported.bin',
    'local/recon/solver-oracle/recovered-solver-oracle.json','local/recon/solver-oracle/solver-input.bin','local/recon/solver-oracle/solver-ported.bin',
    'local/physics-research-0.11.0.json','local/release-0.11.0.json','local/release-checks-0.11.0.log',
    'local/physics-research-0.12.0.json','local/release-0.12.0.json','local/release-checks-0.12.0.log',
    'local/physics-installed-consumer-0.12.0.log',
    'local/physics-research-0.13.0.json','local/release-0.13.0.json','local/release-checks-0.13.0.log',
    'local/physics-installed-consumer-0.13.0.log',
    'local/physics-research-0.14.0.json','local/release-0.14.0.json','local/release-checks-0.14.0.log',
    'local/physics-installed-consumer-0.14.0.log',
    'local/recon/recovered-mesh-oracle.json','local/recon/recovered-tree-builder-oracle.json',
    'local/recon/recovered-convex-oracle.json','local/recon/recovered-polygon-oracle.json','local/recon/recovered-vehicle-kernel-oracle.json',
    'local/recon/cooking-oracle/recovered-cooking-oracle.json','local/recon/cooking-oracle/cook-input.bin','local/recon/cooking-oracle/cook-ported.bin',
    'local/recon/bounds-oracle/recovered-bounds-oracle.json','local/recon/bounds-oracle/bounds-ported.bin',
    'local/recon/material-oracle/recovered-material-oracle.json','local/recon/material-oracle/material-input.bin',
    'local/recon/material-oracle/material-ported.bin','local/recon/material-oracle/material-defaults-ported.bin',
    'local/recon/ghidra/manifest.json','local/recon/ghidra/physics-functions.tsv','local/recon/ghidra/decompiled/decompile-report.tsv',
    'local/recon/ghidra-contacts/manifest.json','local/recon/ghidra-contacts/physics-functions.tsv','local/recon/ghidra-contacts/decompiled/decompile-report.tsv',
    'local/ghidra-headless-contacts-current.log',
    'local/recon/ghidra-vehicle/manifest.json','local/recon/ghidra-vehicle/physics-functions.tsv','local/recon/ghidra-vehicle/decompiled/decompile-report.tsv',
    'local/ghidra-headless-vehicle-current.log',
    'local/ghidra-headless-physics-current.log','tools/ghidra-install.json',
    'local/physics-research-0.10.0.json','local/release-0.10.0.json','local/release-checks-0.10.0.log',
    'local/physics-installed-consumer-0.10.0.log',
    'local/recon/constraint-evidence.json','local/recon/collision-dispatch.json',
    'local/recon/recovered-jacobian-oracle.json','local/recon/recovered-contact-build-oracle.json',
    'local/recon/recovered-rotation-oracle.json','local/recon/recovered-sphere-oracle.json',
    'local/recon/position-oracle/recovered-position-oracle.json','local/recon/position-oracle/position-input.bin',
    'local/recon/position-oracle/position-ported.bin',
    'local/physics-research-0.9.0.json','local/release-0.9.0.json','local/release-checks-0.9.0.log',
    'local/release-final-0.9.0.log','local/recon/physics-relaunch-0.9.0.jpg',
    'local/physics-installed-consumer-0.9.0.log','local/recon/installed-kernel-smoke-0.9.0.json',
    'local/physics-debugger-final-tests-0.9.0.log','local/recon/debug-capture-qualification.json',
    'native/build/debugger-owned.jsonl','native/build/debugger-owned-abort.jsonl',
    'local/recon/game-atlas.sqlite','local/recon/game-atlas.json','local/recon/game-atlas-build.log',
    'local/recon/recovered-contact-oracle.json','local/recon/wheel-contact-pipeline.json','local/recon/wheel-qualification.json',
    'local/recon/selection-oracle/selection-suspension-oracle.json','local/recon/selection-oracle/selection-input.bin','local/recon/selection-oracle/selection-ported.bin',
    'local/recon/reflection-current-build.json','local/recon/reflected-member-types.json',
    'local/recon/physics/physics-procedure-graph.json','local/recon/recovered-kernel-oracle.json',
    'local/recon/recovered-kernel-benchmark.json','local/recon/force-oracle/recovered-force-oracle.json',
    'local/recon/force-oracle/force-oracle-input.bin','local/recon/force-oracle/force-oracle-ported.bin',
    'local/recon/physics-live-qualification.json','local/recon/physics-solo-after-probes.jpg',
    'local/recon/live-cpp-7620-v3.txt','native/build/Testing/Temporary/LastTest.log')]
for file in (ROOT/'local/recon').glob('rigid-*.candidates.txt'):
    prefix=Path(str(file).removesuffix('.candidates.txt'))
    for suffix in ('.candidates.txt','.csv','.manager-hypotheses.csv','.manager-sample.json','.wheels.csv','.failure.txt'):
        candidate=prefix.with_suffix(suffix)
        if candidate.exists():files.append(candidate)
for file in (ROOT/'local/recon').glob('force-phase-7620-v*'):
    if file.is_file() and file.suffix in {'.log','.jsonl'}:files.append(file)
files.extend((ROOT/'local/recon/original-step-native-results-v5').glob('*.json'))
files.extend((ROOT/'local/recon/force-worker-native-v5').glob('*.json'))
files.extend((ROOT/'local/recon/physics').glob('*-qualified.asm'))
files.extend((ROOT/'local/recon/ghidra/decompiled').glob('*.c'))
files.extend((ROOT/'local/recon/ghidra-contacts/decompiled').glob('*.c'))
files.extend((ROOT/'local/recon/ghidra-vehicle/decompiled').glob('*.c'))
missing=[str(p) for p in files if not p.is_file()]
if missing:raise FileNotFoundError(missing)
manifest=[]
for file in sorted(set(files)):
    data=file.read_bytes();manifest.append({'path':str(file.relative_to(ROOT)).replace('\\','/'),
        'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
destination=ROOT/'backups/trackmania2020-re-physics-evidence-0.25.0.zip';destination.parent.mkdir(parents=True,exist_ok=True)
with ZipFile(destination,'w',ZIP_DEFLATED,compresslevel=7) as archive:
    for entry in manifest:archive.write(ROOT/entry['path'],entry['path'])
    archive.writestr('evidence-manifest.json',json.dumps({'schema':'tm2020_physics_evidence_archive_v1','artifacts':manifest},indent=2)+'\n')
digest=hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix('.sha256').write_text(f'{digest}  {destination.name}\n')
print('SAVED',destination,'artifacts',len(manifest),'bytes',destination.stat().st_size,'sha256',digest)
