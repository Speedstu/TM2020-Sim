"""Continuous original-server physics at decoded input boundaries (Linux x64).

This backend starts the pinned engine from a file, never from a fork snapshot.
Observations are the validator-owned car's pre-input state. Files supply map,
race setup and a bounded input horizon. Reset launches a fresh server process.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import select
import struct
import subprocess
import tempfile
import time

from run_official_server_oracle import SERVER_SHA, parse

FRAME = struct.Struct('<I5i13f')
ACTION = struct.Struct('<I3f')
MAGIC = 0x36304D54


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage(root, server, track, ghost):
    (root / 'UserData/Maps').mkdir(parents=True)
    (root / 'UserData/Replays').mkdir()
    for name in ('TrackmaniaServer', 'Packs'):
        (root / name).symlink_to(server / name)
    (root / 'UserData/Maps' / track.name).symlink_to(track)
    (root / 'UserData/Replays' / ghost.name).symlink_to(ghost)


def decode(raw):
    magic, engine, origin, offset, count, index, *values = FRAME.unpack(raw)
    if magic != MAGIC or count < 1 or index != max(-1, (engine-origin-offset)//10):
        raise RuntimeError('Unsupported original engine input boundary')
    if not all(map(math.isfinite, values)):
        raise RuntimeError('Nonfinite original engine state')
    if abs(sum(v*v for v in values[3:7])-1) > 0.001:
        raise RuntimeError('Original vehicle quaternion is not unit length')
    return dict(engineMs=engine, originMs=origin, startOffsetMs=offset, raceMs=engine-origin,
                tapeCount=count, inputIndex=index, controls=values[:3],
                quaternionWxyz=values[3:7], position=values[7:10],
                linearVelocity=values[10:13], rawHex=raw.hex())


def paths(server, track, ghost, shim):
    server, track, ghost, shim = (Path(p).resolve(strict=True) for p in
                                  (server, track, ghost, shim))
    if sha(server / 'TrackmaniaServer') != SERVER_SHA:
        raise ValueError('Unsupported official server hash')
    if not (server / 'Packs').is_dir():
        raise ValueError('Missing official server Packs')
    if not ghost.name.endswith(('.Ghost.Gbx', '.Replay.Gbx')):
        raise ValueError('The official validator requires a ghost/replay GBX name')
    return server, track, ghost, shim


class OfficialEngine:
    """One continuous validation; pass None to retain the file's next input.

    step(action) advances from the current pre-input boundary to the next one.
    action order is (steer, gas, brake), normalized like the engine. A file's
    other input channels and race setup remain in force. No arbitrary restore.
    """
    def __init__(self, server, track, ghost, shim, timeout=30):
        self.server, self.track, self.ghost, self.shim = paths(server, track, ghost, shim)
        self.timeout = timeout
        self.process = None
        self.temporary = None
        self.read_fd = self.write_fd = None
        self.stdout = self.stderr = None
        self.state = None
        self.done = True

    def reset(self):
        self.close()
        self.temporary = tempfile.TemporaryDirectory(prefix='tm2020-continuous-')
        root = Path(self.temporary.name)
        stage(root, self.server, self.track, self.ghost)
        self.stdout = (root / 'stdout.log').open('w+b')
        self.stderr = (root / 'stderr.log').open('w+b')
        child_read, self.write_fd = os.pipe()
        self.read_fd, child_write = os.pipe()
        env = os.environ.copy()
        env.update(LD_PRELOAD=str(self.shim), TM2020_STEP_OUT_FD=str(child_write),
                   TM2020_STEP_IN_FD=str(child_read))
        try:
            self.process = subprocess.Popen(['./TrackmaniaServer', '/nodaemon', '/validatepath=.'],
                cwd=root, env=env, pass_fds=(child_read, child_write),
                stdout=self.stdout, stderr=self.stderr, start_new_session=True)
        finally:
            os.close(child_read)
            os.close(child_write)
        self.done = False
        try:
            self.state = self._receive()
            if self.state is None:
                raise RuntimeError('Engine finished without an owned-car observation')
        except Exception:
            self.close()
            raise
        return self.state

    def _receive(self):
        data = bytearray()
        deadline = time.monotonic() + self.timeout
        while len(data) < FRAME.size:
            left = deadline - time.monotonic()
            if left <= 0 or not select.select([self.read_fd], [], [], left)[0]:
                self.close()
                raise TimeoutError('Official physics boundary timed out')
            part = os.read(self.read_fd, FRAME.size - len(data))
            if not part:
                self.done = True
                code = self.process.wait(timeout=self.timeout)
                if code or data:
                    self.stderr.seek(0)
                    raise RuntimeError(f'Official physics failed ({code}): ' +
                                       self.stderr.read().decode(errors='replace')[-4000:])
                return None
            data.extend(part)
        return decode(data)

    def step(self, action=None):
        if self.done or self.state is None:
            raise RuntimeError('reset is required before stepping')
        if action is None:
            payload = ACTION.pack(0, 0, 0, 0)
        else:
            if len(action) != 3 or not all(math.isfinite(x) for x in action):
                raise ValueError('Expected three finite normalized controls')
            steer, gas, brake = action
            if not (-1 <= steer <= 1 and 0 <= gas <= 1 and 0 <= brake <= 1):
                raise ValueError('Invalid normalized controls')
            if not 0 <= self.state['inputIndex'] < self.state['tapeCount']:
                raise ValueError('Cannot override outside decoded input horizon')
            payload = ACTION.pack(1, steer, gas, brake)
        os.write(self.write_fd, payload)
        previous = self.state
        successor = self._receive()
        if successor is not None and (successor['engineMs'] != previous['engineMs'] + 10 or
                any(successor[key] != previous[key] for key in ('originMs', 'startOffsetMs', 'tapeCount'))):
            self.done = True
            raise RuntimeError('Original input clock, tape index or race identity changed')
        self.state = successor
        return successor

    def result(self):
        if not self.done or self.process is None or self.process.poll() is None:
            raise RuntimeError('Validation has not completed')
        self.stdout.seek(0)
        return parse(self.stdout.read().decode())

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait()
            self.process = None
        for name in ('read_fd', 'write_fd'):
            fd = getattr(self, name, None)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)
        for name in ('stdout', 'stderr'):
            stream = getattr(self, name, None)
            if stream is not None:
                stream.close()
                setattr(self, name, None)
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None
        self.done, self.state = True, None

    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('server', 'map', 'ghost', 'shim', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    with OfficialEngine(a.server, a.map, a.ghost, a.shim) as engine:
        state = engine.reset()
        count = 0
        with (a.output / 'trace.jsonl').open('x') as stream:
            while state is not None:
                stream.write(json.dumps(state) + '\n')
                count += 1
                state = engine.step()
        result = engine.result()
        (a.output / 'report.json').write_text(json.dumps(dict(
            schema='tm2020_continuous_official_trace_v1', frames=count, results=result,
            serverSha256=SERVER_SHA, shimSha256=sha(a.shim), ghostSha256=sha(a.ghost),
            fromStart=True, forkUsed=False, completeIndependentSimulatorQualified=False), indent=2) + '\n')
        print('PASS CONTINUOUS_OFFICIAL_TRACE', count, 'frames', result)


if __name__ == '__main__': main()
