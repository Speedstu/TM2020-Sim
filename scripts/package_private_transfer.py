"""Archive the entire workspace for a private second-PC transfer (ZIP64)."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import time
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent.parent
CHUNK = 1024 * 1024

def link_target(path, metadata):
    tag = getattr(metadata, 'st_reparse_tag', 0)
    if os.name == 'nt' and tag == 0xA000001D:
        # WSL symlinks are LX reparse points. Windows os.readlink does not
        # decode them, and following them would fail or duplicate large trees.
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        api.DeviceIoControl.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.CreateFileW(str(path), 0, 7, None, 3, 0x02200000, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            buffer, count = ctypes.create_string_buffer(16384), wintypes.DWORD()
            if not api.DeviceIoControl(handle, 0x900A8, None, 0, buffer, len(buffer), ctypes.byref(count), None):
                raise ctypes.WinError(ctypes.get_last_error())
            raw = buffer.raw[:count.value]
            actual_tag, size = struct.unpack_from('<IH', raw)
            if actual_tag != tag or size < 4 or 8 + size > len(raw):
                raise ValueError('Malformed LX symlink reparse point')
            return raw[12:8 + size].decode('utf-8')
        finally:
            api.CloseHandle(handle)
    if stat.S_ISLNK(metadata.st_mode) or tag in (0xA0000003, 0xA000000C):
        return os.readlink(path)
    return None

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    output = a.output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Transfer archive must be outside the project')
    if output.exists() or output.with_suffix('.sha256').exists():
        raise ValueError('Never overwrite a transfer archive')
    output.parent.mkdir(parents=True, exist_ok=True)
    files, links = [], []
    isjunction = getattr(os.path, 'isjunction', lambda value: False)
    for base, dirs, names in os.walk(ROOT, followlinks=False):
        for name in list(dirs):
            path = Path(base) / name
            target = link_target(path, path.lstat())
            if target is not None:
                links.append(dict(path=path.relative_to(ROOT).as_posix(), target=target, directory=True))
                dirs.remove(name)
        for name in names:
            path = Path(base) / name
            metadata = path.lstat()
            target = link_target(path, metadata)
            if target is not None:
                links.append(dict(path=path.relative_to(ROOT).as_posix(), target=target, directory=False))
            elif stat.S_ISREG(metadata.st_mode):
                files.append(path)
            else:
                raise ValueError('Unsupported non-regular file: ' + str(path))
    files.sort()
    total = sum(path.stat().st_size for path in files)
    print(f'PACKING {len(files)} files, {total} bytes, {len(links)} links', flush=True)
    manifest, written, last_report = [], 0, time.monotonic()
    with ZipFile(output, 'x', compression=ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for path in files:
            before = path.stat()
            name = ROOT.name + '/' + path.relative_to(ROOT).as_posix()
            info = ZipInfo.from_file(path, name)
            info.compress_type = ZIP_DEFLATED
            info._compresslevel = 1
            digest = hashlib.sha256()
            with path.open('rb') as src, archive.open(info, 'w', force_zip64=True) as dst:
                while part := src.read(CHUNK):
                    digest.update(part)
                    dst.write(part)
                    written += len(part)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError('Source changed during transfer snapshot: ' + str(path))
            manifest.append(dict(path=name, size=before.st_size, sha256=digest.hexdigest()))
            if time.monotonic() - last_report >= 20:
                print(f'PACKED {written}/{total} bytes ({written * 100 / total:.1f}%)', flush=True)
                last_report = time.monotonic()
        archive.writestr(ROOT.name + '/TRANSFER_FILE_MANIFEST.json', json.dumps(manifest, indent=2))
        archive.writestr(ROOT.name + '/TRANSFER_LINKS.json', json.dumps(links, indent=2))
    print('VERIFYING every archived file against SHA-256 manifest', flush=True)
    with ZipFile(output) as archive:
        for row in manifest:
            digest = hashlib.sha256()
            with archive.open(row['path']) as src:
                while part := src.read(CHUNK):
                    digest.update(part)
            if digest.hexdigest() != row['sha256']:
                raise RuntimeError('Transfer member verification failed: ' + row['path'])
    digest = hashlib.sha256()
    with output.open('rb') as src:
        while part := src.read(CHUNK):
            digest.update(part)
    output.with_suffix('.sha256').write_text(f'{digest.hexdigest()}  {output.name}\n', encoding='ascii')
    print(f'PASS PRIVATE_TRANSFER {output} bytes={output.stat().st_size} files={len(manifest)} sha256={digest.hexdigest()}', flush=True)

if __name__ == '__main__':
    main()
