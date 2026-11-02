"""Prepare a separate offline Linux build without changing recovered physics.

The transferred sources target Rust 1.99 and depend on uncached GUI codecs.
This headless build uses the host's safe LZO decoder, JSON catalog caches,
cached dirs/zip versions and omits visual exporters. Physics source is copied
unchanged from the pinned upstream; every portability edit is inventoried.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = 'e0583ee55168e950a65a645778e591bd26b6a0f2'


def main():
    bundled = ROOT/'third_party/gearbox'
    if bundled.is_dir():
        report=json.loads((bundled/'portability.json').read_text())
        if report['upstreamRevision'] != UPSTREAM:
            raise ValueError('Bundled Gearbox revision differs')
        print('Bundled Linux Gearbox source:', bundled)
        return
    source = ROOT/'cache/gearbox-upstream-e0583ee'
    destination = ROOT/'cache/gearbox-linux-0.37'
    revision = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if revision != UPSTREAM:
        raise ValueError('Unexpected upstream revision')
    if destination.exists():
        report=json.loads((destination/'portability.json').read_text())
        if report['upstreamRevision']!=UPSTREAM:
            raise ValueError('Prepared checkout has another revision')
        for relative,entry in report['portabilityEdits'].items():
            actual=hashlib.sha256((destination/relative).read_text().encode()).hexdigest()
            if actual!=entry['afterSha256']:raise ValueError('Unexpected portability source edit: '+relative)
        for p in (source/'packages/engine/src').rglob('*.rs'):
            if p.read_bytes()!=(destination/p.relative_to(source)).read_bytes():
                raise ValueError('Prepared physics differs from the pinned source')
        print('VERIFIED EXISTING PREPARATION',destination)
        return
    destination.mkdir()
    shutil.copytree(source/'packages',destination/'packages')
    shutil.copy2(source/'LICENSE',destination/'LICENSE')
    manifest = (source/'Cargo.toml').read_text()
    start = manifest.index('members = [')
    end = manifest.index(']',start)+1
    packages = ['engine','gbx','net','packs','run','search','trace','world']
    manifest = manifest[:start]+'members = ['+', '.join('"packages/'+p+'"' for p in packages)+']'+manifest[end:]
    manifest = manifest.replace('rust-version = "1.99"','rust-version = "1.98"')
    manifest += '\n[patch.crates-io]\nlzokay-native = { path = "../../integrations/fast-training/lzo" }\n'
    (destination/'Cargo.toml').write_text(manifest)
    edits = {}
    def edit(relative, transform):
        p=destination/relative
        before=p.read_text()
        after=transform(before)
        if before==after:raise ValueError('Portability edit did not match: '+relative)
        p.write_text(after)
        edits[relative]=dict(beforeSha256=hashlib.sha256(before.encode()).hexdigest(),
                            afterSha256=hashlib.sha256(after.encode()).hexdigest())
    edit('packages/gbx/Cargo.toml',lambda s:s.replace('version = "9",','version = "8.6",'))
    edit('packages/gbx/src/map/embedded.rs',lambda s:s.replace('file.name()?','file.name()'))
    def packs(s):
        s=s.replace('postcard = { version = "1", features = ["use-std"] }\n','')
        s=s.replace('dirs = "7"','dirs = "6"')
        s='\n'.join(line for line in s.splitlines() if not line.startswith(('image =','image_dds =')))+'\n'
        return s
    edit('packages/packs/Cargo.toml',packs)
    edit('packages/packs/src/lib.rs',lambda s:s.replace('pub mod visual;','// Visual exporters excluded from this headless build.'))
    edit('packages/packs/src/catalog.rs',lambda s:s.replace('postcard::from_bytes','serde_json::from_slice').replace('postcard::to_stdvec','serde_json::to_vec'))
    engine_files=list((source/'packages/engine/src').rglob('*.rs'))
    for p in engine_files:
        if p.read_bytes()!=(destination/p.relative_to(source)).read_bytes():
            raise ValueError('Physics source was changed')
    report=dict(schema='tm2020_linux_headless_portability_v1',upstreamRevision=UPSTREAM,
                engineSourceFilesUnchanged=len(engine_files),portabilityEdits=edits)
    (destination/'portability.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PREPARED',destination,'unchanged physics files',len(engine_files))


if __name__=='__main__':main()
