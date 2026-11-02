"""Build a separate 0.35 fork with the original-instruction-checked sphere ray."""
import hashlib
import json
from pathlib import Path
import subprocess
from force_worker_fixture import require
from pinned_build import ROOT
from headless_engine import UPSTREAM


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True).strip()
def main():
    original=ROOT/'cache/gearbox-upstream-e0583ee';prior=ROOT/'cache/gearbox-extensions-0.34-v2'
    destination=ROOT/'cache/gearbox-extensions-0.35';assets=ROOT/'integrations/gearbox-extensions'
    require(git('-C',original,'rev-parse','HEAD')==UPSTREAM and not git('-C',original,'status','--porcelain'),'Original checkout changed')
    manifest=json.loads((ROOT/'local/recon/gearbox-extensions-0.34-source-v2.json').read_text())
    for item in manifest['changedFiles']:require(sha(prior/item['path'])==item['extendedSha256'],'Prior patch changed')
    if not destination.exists():
        git('clone','--shared','--no-checkout',original,destination)
        git('-C',destination,'checkout','--detach',UPSTREAM)
    require(git('-C',destination,'rev-parse','HEAD')==UPSTREAM,'Unknown new fork base')
    files={item['path']:(prior/item['path']).read_bytes() for item in manifest['changedFiles']}
    relative='packages/engine/src/collision/raycast.rs';text=files[relative].decode()
    require(text.count('use super::{CollisionWorld')==1 and text.count('Shape::Mesh(m) => mesh(')==1,'Unknown ray source')
    text='mod sphere_ray;\npub use sphere_ray::sphere as sphere_query;\n'+text
    text=text.replace('                Shape::Mesh(m) => mesh(',
        '                Shape::Sphere(s) => sphere_query(s, r, iso.pos, ray, Vec3::ZERO, filter, &mut hit),\n                Shape::Mesh(m) => mesh(')
    files[relative]=text.encode()
    files['packages/engine/src/collision/raycast/sphere_ray.rs']=(assets/'sphere_ray.rs').read_bytes()
    relative='packages/engine/src/collision/mod.rs';text=files[relative].decode()
    require(text.count('pub use raycast::{triangle as ray_triangle, mesh as ray_mesh};')==1,'Unknown exported ray entry')
    files[relative]=text.replace('pub use raycast::{triangle as ray_triangle, mesh as ray_mesh};',
        'pub use raycast::{triangle as ray_triangle, mesh as ray_mesh, sphere_query as ray_sphere};').encode()
    changes=[]
    for relative,raw in files.items():
        path=destination/relative;path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            base=original/relative
            require(path.read_bytes()==raw or (base.is_file() and path.read_bytes()==base.read_bytes()),'Unknown extension edit '+relative)
        if not path.exists() or path.read_bytes()!=raw:path.write_bytes(raw)
        base=original/relative
        changes.append(dict(path=relative,originalSha256=sha(base) if base.is_file() else None,extendedSha256=sha(path)))
    status={line.split(maxsplit=1)[1] for line in git('-C',destination,'status','--porcelain','--untracked-files=all').splitlines()}
    require(status==set(files),'Unexpected files in new fork')
    proof=dict(schema='tm2020_reviewed_engine_extensions_v2',upstreamRevision=UPSTREAM,
        priorExtensionSha256=manifest['physicsExtensionSha256'],changedFiles=changes,
        originalSphereRayRva='0x1a5580',originalSphereRayQuadraticRva='0x18f410',
        completeExactSimulatorQualified=False)
    digest=hashlib.sha256(json.dumps(proof,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    proof['physicsExtensionSha256']=digest
    location=ROOT/'local/recon/gearbox-extensions-0.35-source.json'
    if location.exists():require(json.loads(location.read_text())==proof,'Existing source identity changed')
    else:location.write_text(json.dumps(proof,indent=2)+'\n')
    previous=(ROOT/'cache/gearbox-extension-host-main.rs').read_text()
    require(previous.count(manifest['physicsExtensionSha256'])==1,'Unknown generated host')
    output=ROOT/'cache/gearbox-sphere-ray-host-main.rs'
    host=previous.replace(manifest['physicsExtensionSha256'],digest).encode()
    if not output.exists() or output.read_bytes()!=host:output.write_bytes(host)
    print('PREPARED SPHERE RAY',digest,'original clean')

if __name__=='__main__':main()
