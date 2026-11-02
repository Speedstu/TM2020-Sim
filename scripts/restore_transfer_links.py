"""Restore internal workspace links after extracting the private transfer ZIP."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIXES = ('H:/Projects/Trackmania2020-RE/', '/mnt/h/Projects/Trackmania2020-RE/')

def main():
    links = json.loads((ROOT / 'TRANSFER_LINKS.json').read_text())
    restored, external = 0, []
    for row in links:
        relative = Path(row['path'])
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Unsafe archived link path')
        path = ROOT / relative
        target = row['target'].removeprefix('\\\\?\\').replace('\\', '/')
        internal = next((target[len(prefix):] for prefix in PREFIXES if target.lower().startswith(prefix.lower())), None)
        if internal is not None:
            dest = ROOT / internal
        elif not Path(target).is_absolute() and ':' not in target:
            dest = (path.parent / target).resolve()
        else:
            external.append(row['path'])
            continue
        resolved = dest.resolve()
        if resolved != ROOT and ROOT not in resolved.parents:
            external.append(row['path'])
            continue
        if path.exists() or path.is_symlink():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(os.path.relpath(dest, path.parent), target_is_directory=dest.is_dir() or row['directory'])
        restored += 1
    print('RESTORED', restored, 'internal links; external links left for installed dependencies:', len(external))
    for name in external:
        print('EXTERNAL', name)

if __name__ == '__main__':
    main()
