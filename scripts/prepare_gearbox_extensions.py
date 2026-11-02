"""Apply reviewed physics additions to a separate, pinned upstream checkout."""
import hashlib
import json
from pathlib import Path
import subprocess

from force_worker_fixture import require
from pinned_build import ROOT
from headless_engine import UPSTREAM


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(["git",*map(str,args)],text=True).strip()


def main():
    original=ROOT/"cache/gearbox-upstream-e0583ee";destination=ROOT/"cache/gearbox-extensions-0.34-v2"
    if not original.exists():
        git("clone","--no-checkout","https://github.com/Mergemat/gearbox",original)
        git("-C",original,"checkout","--detach",UPSTREAM)
    require(git("-C",original,"rev-parse","HEAD")==UPSTREAM and not git("-C",original,"status","--porcelain"),"Original upstream checkout must remain unchanged")
    if not destination.exists():
        git("clone","--shared","--no-checkout",original,destination)
        git("-C",destination,"checkout","--detach",UPSTREAM)
    require(git("-C",destination,"rev-parse","HEAD")==UPSTREAM,"Unknown extension checkout base")
    inputs=ROOT/"integrations/gearbox-extensions";files={}
    for relative in ("packages/engine/src/collision/narrow/mod.rs","packages/engine/src/collision/mod.rs","packages/engine/src/collision/raycast.rs"):
        files[relative]=(original/relative).read_text()
    relative="packages/engine/src/collision/narrow/mod.rs";text=files[relative]
    require(text.count("pub mod sphere;")==1 and text.count("match (geometry.shape(a.shape), geometry.shape(b.shape)) {")==1,"Unknown narrowphase source")
    text=text.replace("pub mod sphere;","pub mod sphere;\npub mod sphere_pair;")
    text=text.replace("match (geometry.shape(a.shape), geometry.shape(b.shape)) {",
        "match (geometry.shape(a.shape), geometry.shape(b.shape)) {\n        (Shape::Sphere(sa), Shape::Sphere(sb)) => sphere_pair::contacts(sa, a_ref, a, sb, b_ref, b, out),")
    files[relative]=text
    relative="packages/engine/src/collision/mod.rs"
    files[relative]+="\n// Explicit original-instruction-qualified query entries.\npub use raycast::{triangle as ray_triangle, mesh as ray_mesh};\n"
    relative="packages/engine/src/collision/raycast.rs";text=files[relative]
    start=text.index("    if two_sided {\n");end=text.index("    if fraction > max {",start)
    require('todo!("two-sided ray vs triangle")' in text[start:end],"Unknown ray branch")
    files[relative]=text[:start]+(inputs/"ray_prefix.rs").read_text()+text[end:]
    files["packages/engine/src/collision/narrow/sphere_pair.rs"]=(inputs/"sphere_pair.rs").read_text()
    changes=[]
    for relative,text in files.items():
        path=destination/relative;raw=text.replace("\r\n","\n").encode()
        if path.exists():
            previous=path.read_bytes();base=original/relative
            require(previous==raw or (base.is_file() and previous==base.read_bytes()),"Refuse to overwrite unknown extension edits: "+relative)
        if not path.exists() or path.read_bytes()!=raw:path.write_bytes(raw)
        changes.append(dict(path=relative,originalSha256=sha(original/relative) if (original/relative).exists() else None,extendedSha256=sha(path)))
    changed={line.split(maxsplit=1)[1] for line in git("-C",destination,"status","--porcelain","--untracked-files=all").splitlines()}
    require(changed==set(files),"Unexpected additional edits in extension checkout")
    proof=dict(schema="tm2020_reviewed_engine_extensions_v1",upstreamRevision=UPSTREAM,changedFiles=changes,
        originalEntryRvas=["0x1af350","0x18ba80","0x18ca50","0x1a17f0"],
        completeExactSimulatorQualified=False)
    digest=hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    proof["physicsExtensionSha256"]=digest
    manifest=ROOT/"local/recon/gearbox-extensions-0.34-source-v2.json"
    if manifest.exists():require(json.loads(manifest.read_text())==proof,"Extension manifest already describes other sources")
    else:manifest.write_text(json.dumps(proof,indent=2)+"\n")
    main_source=(ROOT/"integrations/gearbox-host/src/main.rs").read_text()
    needle='"coldMapLoadedFromInstalledAssets":true,"completeExactPhysicsQualified":false'
    require(main_source.count(needle)==1,"Unexpected base host identity code")
    main_source=main_source.replace(needle,'"coldMapLoadedFromInstalledAssets":true,"completeExactPhysicsQualified":false,\n        "physicsExtensionSha256":"'+digest+'"')
    needle='let mut seed=2026u32;'
    require(main_source.count(needle)==1,"Unknown host argument initialization")
    main_source=main_source.replace(needle,needle+'let mut car_override=None;')
    needle='"--seed" => seed=value.parse()?,''\n'
    require(main_source.count(needle)==1,"Unknown host argument parser")
    main_source=main_source.replace(needle,needle+'''            "--car" => car_override=Some(match value.as_str(){
                "CarSport"=>gearbox_world::car::Car::Stadium,"CarSnow"=>gearbox_world::car::Car::Snow,
                "CarRally"=>gearbox_world::car::Car::Rally,"CarDesert"=>gearbox_world::car::Car::Desert,
                _=>bail!("unsupported explicit car"),
            }),
''')
    main_source=main_source.replace('seed:Some(seed),car:None','seed:Some(seed),car:car_override')
    main_source=main_source.replace('"backendLicense":"GPL-3.0-or-later",','"backendLicense":"GPL-3.0-or-later","initialCarOverride":car_override.map(|car|car.pack_name()),')
    main_source=main_source.replace('"assetBodyMass":model.body.mass,','"assetBodyMass":model.body.mass,"assetForceModelKind":model.assets.tuning.model_kind,')
    generated=ROOT/"cache/gearbox-extension-host-main.rs";raw=main_source.replace("\r\n","\n").encode()
    if not generated.exists() or generated.read_bytes()!=raw:generated.write_bytes(raw)
    print("PREPARED PHYSICS EXTENSIONS",digest,"original checkout unchanged")


if __name__=="__main__":main()
