"""Causal short-horizon training task on the continuous official engine.

Observation: relative XYZ/100, quaternion WXYZ, velocity XYZ/100, last applied
steer/gas/brake. The reference file's controls never enter the observation.
Reward: displacement along initial forward direction, in metres. This task
does not reward checkpoint completion and is not a general race objective.
"""
import hashlib
import math
import struct

from official_engine import OfficialEngine

SCHEMA = 'tm2020_official_preinput13_v1|actions=ghost_binary_pedals_i8_steer_v1'
OBSERVATIONS = 13


def quantize(action):
    if len(action) != 3 or not all(math.isfinite(v) and -1 <= v <= 1 for v in action):
        raise ValueError('Expected three bounded policy actions')
    # Policy order follows the existing PPO adapter: gas, brake, steer.
    steer = max(-127, min(127, round(action[2] * 127)))
    return (struct.unpack('<f', struct.pack('<f', steer / 127))[0],
            float(action[0] >= 0), float(action[1] >= 0))


def encode(state, origin, previous):
    return ([(a-b)/100 for a, b in zip(state['position'], origin)] +
            list(state['quaternionWxyz']) +
            [v/100 for v in state['linearVelocity']] + list(previous))


class OfficialTraining:
    def __init__(self, server, track, ghost, shim, horizon=503, repeat=5):
        if not 1 <= horizon <= 100_000 or not 1 <= repeat <= 100:
            raise ValueError('Invalid bounded training horizon')
        self.engine = OfficialEngine(server, track, ghost, shim)
        self.horizon, self.repeat = horizon, repeat
        self.done = True

    def reset(self):
        state = self.engine.reset()
        while state['raceMs'] < 0:
            state = self.engine.step()
            if state is None:
                raise RuntimeError('Original validation ended during countdown')
        if state['raceMs'] != 0:
            raise RuntimeError('A clean race-zero boundary is required')
        # The supplied file bounds validation. Do not invent controls beyond it.
        if state['inputIndex'] + self.horizon >= state['tapeCount']:
            raise ValueError('Training horizon exceeds source input tape')
        self.origin = state['position'][:]
        w, x, y, z = state['quaternionWxyz']
        self.axis = [2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)]
        self.previous = (0.0, 0.0, 0.0)
        self.ticks, self.done = 0, False
        return encode(state, self.origin, self.previous)

    def step(self, action):
        if self.done:
            raise RuntimeError('Training episode requires reset')
        controls = quantize(action)
        before = self.engine.state
        ticks = min(self.repeat, self.horizon-self.ticks)
        digest = hashlib.sha256()
        for _ in range(ticks):
            state = self.engine.step(controls)
            if state is None:
                self.done = True
                # No fabricated successor: cancel this PPO decision on error.
                raise RuntimeError('Original validation ended before the bounded task horizon')
            digest.update(bytes.fromhex(state['rawHex'])[-40:])
        self.ticks += ticks
        self.previous = controls
        self.done = self.ticks == self.horizon
        reward = sum((a-b)*direction for a, b, direction in
                     zip(state['position'], before['position'], self.axis))
        observation = encode(state, self.origin, self.previous)
        info = dict(beforeRaceMs=before['raceMs'], afterRaceMs=state['raceMs'],
                    controls=list(controls), advancedTicks=ticks,
                    traceSha256=digest.hexdigest(),
                    beforeStateBits=before['rawHex'][-80:], afterStateBits=state['rawHex'][-80:])
        return observation, reward, False, self.done, info

    def close(self): self.engine.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()
