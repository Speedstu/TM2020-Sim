"""Seal the 0.35 numeric reports without server binaries, maps or ghosts."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    'local/recon/official-server-0.35-human-oracle.json',
    'local/recon/official-server-fork-check-0.35-v1.json',
    'local/recon/sphere-ray-original-0.35-v1/report.json',
    'local/recon/sphere-ray-original-0.35-v1/rust-report.json',
    'local/recon/sphere-ray-original-0.35-v1/ray-sphere.cases',
    'local/recon/sphere-ray-four-car-0.35-v1/report.json',
    'local/recon/gearbox-extensions-0.35-source.json',
    'local/recon/geometry-sdk-0.35-v1/report.json',
    'local/recon/official-validator-trace-0.35-v1/report.json',
    'local/recon/official-validator-trace-0.35-v1/trajectory-0.csv',
    'local/recon/official-validator-trace-0.35-v1/trajectory-1.csv',
)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'backups/trackmania2020-re-official-oracle-0.35.0.zip')
    output = p.parse_args().output.resolve()
    if output.exists() or output.with_suffix('.sha256').exists():
        raise ValueError('Evidence archive already exists')
    paths = [ROOT / name for name in FILES]
    if not all(path.is_file() for path in paths):
        raise FileNotFoundError('Missing one or more 0.35 evidence files')
    if any(path.suffix.lower() in {'.gbx', '.exe', '.dll', '.pak'} for path in paths):
        raise ValueError('Game assets and binaries cannot be archived')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = [{'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest()}
                for name in FILES]
    with ZipFile(output, 'x', ZIP_DEFLATED, compresslevel=7) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
        archive.writestr('evidence-manifest.json', json.dumps(manifest, indent=2) + '\n')
    with ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Evidence archive CRC failed')
        for row in manifest:
            if hashlib.sha256(archive.read(row['path'])).hexdigest() != row['sha256']:
                raise RuntimeError('Archived evidence hash mismatch')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256').write_text(f'{digest}  {output.name}\n', encoding='ascii')
    print('SAVED', output, 'sha256', digest)

if __name__ == '__main__':
    main()
