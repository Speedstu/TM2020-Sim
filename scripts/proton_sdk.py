#!/usr/bin/env python3
"""Run the local Windows SDK in the *running game's* Flatpak/Proton instance.

Files must first be staged into C:\\tm2020-sdk: Flatpak cannot see the project.
Only selected runtime environment variables are copied; no account data.
"""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import hashlib
import tempfile


def copy_immutable(source,destination):
    """Do not truncate/replace a file Wine may have mapped as a live image."""
    source=Path(source).resolve(strict=True);destination=Path(destination)
    digest=hashlib.sha256(source.read_bytes()).digest()
    def check():
        if hashlib.sha256(destination.read_bytes()).digest()!=digest:
            raise RuntimeError(f'Refusing to replace a possibly loaded file: {destination}; use a new content-hash name')
    if destination.exists():check();return destination
    with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.stage-',delete=False) as temporary:tmp=Path(temporary.name)
    try:
        shutil.copy2(source,tmp)
        try:os.link(tmp,destination)
        except FileExistsError:check()
    finally:tmp.unlink(missing_ok=True)
    return destination


def running_game():
    matches = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            first = args[0].decode(errors='replace').replace('\\', '/').rsplit('/', 1)[-1].lower()
            if first != 'trackmania.exe':
                continue
            env = dict(x.decode(errors='surrogateescape').split('=', 1)
                       for x in (proc / 'environ').read_bytes().split(b'\0') if b'=' in x)
            if 'WINEPREFIX' in env:
                matches.append((int(proc.name), env))
        except (OSError, ValueError):
            pass
    if len(matches) != 1:
        raise RuntimeError(f'Expected one running Trackmania.exe, found {len(matches)}')
    return matches[0]


def runtime():
    pid, env = running_game()
    instances = subprocess.check_output(['flatpak', 'ps', '--columns=instance,pid'], text=True)
    instance = None
    # Match the game's mount namespace, including the nested Steam runtime.
    namespace = os.readlink(f'/proc/{pid}/ns/mnt')
    ancestors = set()
    parent = pid
    while parent > 1:
        ancestors.add(parent)
        try:
            status = Path(f'/proc/{parent}/status').read_text()
            parent = int(next(x.split()[1] for x in status.splitlines() if x.startswith('PPid:')))
        except (OSError, StopIteration):
            break
    for line in instances.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].isdigit():
            continue
        try:
            if int(fields[1]) in ancestors or os.readlink(f'/proc/{fields[1]}/ns/mnt') == namespace:
                instance = fields[0]
                break
        except OSError:
            pass
    if not instance:
        raise RuntimeError('Running game Flatpak instance was not found')
    prefix = Path(env['WINEPREFIX'])
    process_root = Path('/proc') / str(pid) / 'root'
    def executable_exists(path):
        path=Path(path)
        return path.is_absolute() and (path.is_file() or (process_root / str(path).lstrip('/')).is_file())
    # Ubisoft launched inside Flatpak exports paths valid in its mount namespace,
    # which may not exist at the same pathname on the host.
    loader=Path(env.get('WINELOADER',''))
    wine=loader if loader.name in ('wine','wine64') and executable_exists(loader) else None
    if wine is None:
        wine = next((Path(x) / 'wine' for x in env.get('PATH', '').split(':')
                     if 'Proton' in x and executable_exists(Path(x) / 'wine')), None)
    if wine is None:
        # Proton exports its library path even when bin is omitted from PATH.
        for part in env.get('LD_LIBRARY_PATH', '').split(':'):
            if '/files/lib/' in part:
                candidate = Path(part.split('/files/lib/')[0]) / 'files/bin/wine'
                if executable_exists(candidate):
                    wine = candidate
                    break
    if wine is None:
        raise RuntimeError('Cannot locate the running Proton wine binary')
    host_prefix=prefix if (prefix/'drive_c').is_dir() else process_root/str(prefix).lstrip('/')
    stage = host_prefix / 'drive_c/tm2020-sdk'
    stage.mkdir(exist_ok=True)
    selected = [f'{k}={env[k]}' for k in
                ('WINEPREFIX', 'WINEFSYNC', 'WINEESYNC', 'WINELOADERNOEXEC',
                 'DISPLAY', 'XAUTHORITY', 'LD_LIBRARY_PATH') if k in env]
    command = ['flatpak', 'enter', instance, 'env', *selected, 'WINEDEBUG=-all', str(wine)]
    return pid, stage, command


def stage_file(source, name=None):
    _, directory, _ = runtime()
    source = Path(source).resolve(strict=True)
    target = directory / (name or source.name)
    if source != target:copy_immutable(source,target)
    return 'C:\\tm2020-sdk\\' + target.name


def run(arguments, timeout=60):
    _, _, command = runtime()
    return subprocess.run(command + list(arguments), timeout=timeout, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('info')
    s = sub.add_parser('stage'); s.add_argument('files', nargs='+')
    r = sub.add_parser('run'); r.add_argument('arguments', nargs=argparse.REMAINDER)
    a = p.parse_args()
    if a.action == 'info':
        pid, directory, command = runtime()
        print(json.dumps({'hostPid': pid, 'stage': str(directory), 'wine': command[-1]}, indent=2))
    elif a.action == 'stage':
        for file in a.files:
            print(stage_file(file))
    else:
        run(a.arguments, timeout=260)


if __name__ == '__main__':
    main()
