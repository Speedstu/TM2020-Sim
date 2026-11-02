#!/usr/bin/env python3
"""Verify bundled controller bytes and map identity without game files or NumPy."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]


def check():
    directory = ROOT / 'models/fall-2026-01'
    manifest = json.loads((directory / 'manifest.json').read_text())
    checked = []
    for item in manifest['artifacts']:
        path = directory / item['file']
        raw = path.read_bytes()
        if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError(f"Model checksum or size differs: {item['id']}")
        if raw[:8] != b'TMHYB001':
            raise ValueError('Model magic differs')
        version, n, nx, nh, uid_len, sha_len = struct.unpack_from('<6I', raw, 8)
        if version != item['assetSchemaVersion'] or nx != 12 or nh != 32 or not 100 <= n <= 10000:
            raise ValueError('Unexpected controller schema')
        extra = {1: 0, 7: 32}.get(version)
        if extra is None or len(raw) != 32 + uid_len + sha_len + (6 + 449 + extra) * 8 + n * 25 * 4 + 8:
            raise ValueError('Unexpected controller length')
        uid = raw[32:32 + uid_len].decode()
        sha = raw[32 + uid_len:32 + uid_len + sha_len].decode()
        if uid != manifest['mapUid'] or sha != manifest['mapSha256']:
            raise ValueError('Model and manifest map identity differ')
        checksum = 14695981039346656037
        for byte in raw[:-8]:
            checksum = ((checksum ^ byte) * 1099511628211) & ((1 << 64) - 1)
        if checksum != struct.unpack_from('<Q', raw, len(raw) - 8)[0]:
            raise ValueError('Internal controller checksum differs')
        checked.append(item['id'])
    return checked


if __name__ == '__main__':
    print(json.dumps({'verifiedChampions': check(), 'gameAssetsRequired': False}, indent=2))
