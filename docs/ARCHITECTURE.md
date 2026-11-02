# Trackmania 2020 reverse-engineering strategy

## Existing implementation status
- Read-only game identity and pack inventory: code present
- GBX map/replay parser CLI: code present; verify compilation on this machine
- Vehicle instrumentation: not implemented
- Offline physics reconstruction: not implemented
- Accurate collision extraction: not implemented
- Batched simulator/training: not implemented

## Roadmap
1. Gather legal/local test maps; collect Map.Gbx, Ghost.Gbx and Replay.Gbx metadata.
2. Compile the GBX.NET adapter and export block lists and coordinates as JSON.
3. Build a geometric map representation from blocks/items and collision meshes. Never confuse block grid coordinates with collision triangles.
4. Build an offline instrumentation plugin and input logger, with fixed timestamps and test runs.
5. Identify input quantization, tick time, friction, steering and collision behavior by recording repeated controlled test cases.
6. Implement a deterministic C++/Rust vectorized simulator with state rewind, step, reset, observation/control API.
7. Differential test against real game on known and withheld surfaces/maps, score position/orientation/velocity/contact error per tick.
8. Add RL / planning only when simulator errors are measured and acceptable.

Boundaries: offline research; no anti-cheat bypass, DRM bypass, online competitive automation, or redistributed game archives.

Dependencies: .NET 9 installed; GBX.NET 2 under MIT; GBX.NET.LZO 2 uses GPL-3.0 obligations. Build caches & temp explicitly on H:.
