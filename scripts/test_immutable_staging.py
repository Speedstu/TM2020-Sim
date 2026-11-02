"""Regression: staging a loaded DLL must preserve its mapped inode and bytes."""
import mmap
from pathlib import Path
import tempfile
from proton_sdk import copy_immutable

with tempfile.TemporaryDirectory() as directory:
    p=Path(directory);source=p/'source.dll';target=p/'loaded-hash.dll';source.write_bytes(b'MZ'+bytes(range(256))*32)
    copy_immutable(source,target)
    with target.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as image:
        before=target.stat();data=image[:]
        copy_immutable(source,target)
        assert target.stat().st_ino==before.st_ino and target.stat().st_mtime_ns==before.st_mtime_ns
        assert image[:]==data
        source.write_bytes(b'MZ'+b'changed'*1024)
        try:copy_immutable(source,target);raise AssertionError('Loaded image replaced')
        except RuntimeError:pass
        assert image[:]==data and target.read_bytes()==data
        copy_immutable(source,p/'new-hash.dll');assert (p/'new-hash.dll').read_bytes()==source.read_bytes()
print('PASS immutable staging: loaded inode/mtime/bytes preserved; changed content needs a new name')
