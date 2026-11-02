"""Read-only investigation of AsyncState parent hypotheses, never an owner claim.

Checks process creation and executable SHA. Reads only bounded candidate
structures; does not scan/dump arbitrary memory or write to the game.
"""
import argparse
import ctypes
from ctypes import wintypes as w
import hashlib
import json
from pathlib import Path
import struct
import time

ROOT = Path(__file__).resolve().parents[1]


def probe(cache: Path):
    lines = cache.read_text().splitlines()
    if lines[0] != 'TM2020_VISUAL_CACHE_V1' or not 3 <= int(lines[4]) <= 64 or len(lines) != 5 + int(lines[4]):
        raise ValueError('Invalid disposable visual cache')
    pid, created, sha = int(lines[1]), int(lines[2]), lines[3]
    reflection = json.loads((ROOT / 'local/recon/reflection-current-build.json').read_text())
    if sha != reflection['exeSha256']:
        raise ValueError('Reflection/cache build mismatch')
    scene = next(c for c in reflection['classes'] if c['name'] == 'CSceneVehicleVis')
    offset = next(p['offset'] for p in scene['properties'] if p['name'] == 'AsyncState')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    kernel.ReadProcessMemory.restype = w.BOOL
    kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
    handle = kernel.OpenProcess(0x1010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        stamps = [w.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in stamps]):
            raise ctypes.WinError(ctypes.get_last_error())
        if stamps[0].dwHighDateTime << 32 | stamps[0].dwLowDateTime != created:
            raise ValueError('Stale process creation timestamp')
        image = ctypes.create_unicode_buffer(32768); length = w.DWORD(len(image))
        if not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        executable = Path(image.value)
        if executable.name.lower() != 'trackmania.exe' or hashlib.sha256(executable.read_bytes()).hexdigest() != sha:
            raise ValueError('Target executable identity mismatch')

        def read(address, size):
            output = ctypes.create_string_buffer(size); got = ctypes.c_size_t()
            if not kernel.ReadProcessMemory(handle, address, output, size, ctypes.byref(got)) or got.value != size:
                return None
            return output.raw

        first = []
        for text in lines[5:]:
            position = int(text, 16)
            if not 0x10000 + 0x50 + offset < position < 0x00007FFFFFF00000:
                raise ValueError('Noncanonical candidate')
            state = position - 0x50
            raw = read(state, 0x360); parent = read(state - offset, 64)
            if not raw or not parent or struct.unpack_from('<I', raw)[0] != 0x02000006:
                continue
            first.append((state, raw, parent))
        time.sleep(.2)
        candidates = []
        for state, raw, parent in first:
            current = read(state, 0x360)
            before = struct.unpack_from('<I', raw, 12)[0]
            after = struct.unpack_from('<I', current, 12)[0] if current else None
            candidates.append({
                'state': hex(state), 'hypothetical_parent': hex(state - offset),
                'parent_first_words': [hex(q) for q in struct.unpack('<8Q', parent)],
                'position': struct.unpack_from('<3f', raw, 0x50), 'clock_before': before, 'clock_after': after,
                'race_start_before': struct.unpack_from('<i',raw,0x1b4)[0],
                'race_start_after': struct.unpack_from('<i',current,0x1b4)[0] if current else None,
                'input_before': struct.unpack_from('<3f',raw,0x10),
                'clock_advanced': after is not None and 0 < ((after - before) & 0xffffffff) < 0x80000000,
            })
        return {
            'schema': 'tm2020_visual_parent_hypotheses_v1', 'pid': pid, 'creation_filetime': created,
            'exe_sha256': sha, 'read_only_access_mask': '0x1010',
            'reflected_async_state_offset': offset, 'registered_scene_extent': scene['registeredSize'],
            'candidates': candidates, 'authoritative_physics_owner_verified': False,
            'stable_across_restart_verified': False,
            'warning': 'Subtracting a reflected offset is only an inline-layout hypothesis. Headers, slot types, ownership and input correlation remain unproved. Buffered frozen states must not become SDK roots.',
        }
    finally:
        kernel.CloseHandle(handle)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('cache', type=Path); parser.add_argument('report', type=Path)
    args = parser.parse_args(); result = probe(args.cache)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print('READ_ONLY_PARENT_HYPOTHESES', len(result['candidates']), 'advancing',
          sum(c['clock_advanced'] for c in result['candidates']), 'owner_verified=false')
