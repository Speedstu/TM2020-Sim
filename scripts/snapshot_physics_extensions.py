"""Archive bounded extension evidence without game assets or instruction bytes."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from force_worker_fixture import require
from pinned_build import ROOT


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve()
    require(not output.exists() and not output.with_suffix('.sha256').exists(),'Never overwrite retained archives')
    audit=ROOT/'local/recon/physics-extensions-milestone-0.34-v2.json'
    proof=json.loads(audit.read_text());require(proof['schema']=='tm2020_geometry_extensions_milestone_v1','Unknown audit')
    run=ROOT/'local/recon/physics-extension-final-v2';files={audit,ROOT/'docs/PHYSICS_0_34_GEOMETRY_EXTENSIONS.md'}
    for name in ('geometry-original','wake-original','active-slot-original'):
        files.update(p for p in (run/name).iterdir() if p.is_file() and p.suffix in ('.cases','.json'))
    for relative in ('native-tests.xml','rust-oracle.json','cold/report.json','cars/report.json','gym/report.json','identity/report.json'):
        files.add(run/relative)
    files.update(p for p in (ROOT/'integrations/gearbox-extensions').iterdir() if p.is_file())
    files.add(ROOT/'local/recon/geometry-sdk-0.34-v2/report.json')
    files.add(ROOT/'local/recon/extended-game-replays-v2/report.json')
    numeric={item['path']:item['sha256'] for item in proof['numericOracleFiles']}
    for file in files:
        path=file.resolve(strict=True);require(path.is_relative_to(ROOT),'Artifact outside project')
        require(path.suffix.lower() not in ('.gbx','.exe','.dll','.pak','.tmstep'),'Private binary or asset denied')
        relative=path.relative_to(ROOT).as_posix()
        if relative in numeric:require(digest(path)==numeric[relative],'Numeric oracle evidence changed')
        if relative in proof['evidence']:require(digest(path)==proof['evidence'][relative],'Audited evidence changed')
    rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=digest(p)) for p in sorted(files)]
    manifest=dict(schema='tm2020_physics_extensions_evidence_archive_v1',auditSha256=digest(audit),
        containsGameAssets=False,containsGameExecutableOrInstructionBytes=False,
        completeExactSimulatorQualified=False,artifacts=rows)
    output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'x',ZIP_DEFLATED,compresslevel=7) as archive:
        for p in sorted(files):archive.write(p,p.relative_to(ROOT).as_posix())
        archive.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
    with ZipFile(output) as archive:
        require(archive.testzip() is None,'Archive CRC failed')
        for row in rows:require(hashlib.sha256(archive.read(row['path'])).hexdigest()==row['sha256'],'Archive content changed')
    value=digest(output);output.with_suffix('.sha256').write_text(value+'  '+output.name+'\n',encoding='ascii')
    print('SAVED EXTENSION EVIDENCE',len(rows),'artifacts',output.stat().st_size,'bytes',value)


if __name__=='__main__':main()
