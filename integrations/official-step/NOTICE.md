# Continuous official-engine adapter, research 0.36

`step_shim.cpp` and the Python adapter use the original Linux dedicated server
as a local physics backend. They do not implement Nadeo's physics. No Nadeo
binary or Packs belong in a source distribution. The server hash and tested
instruction signatures are build-specific. Only the private process mappings
are instrumented; files in the server installation are not changed.

The validator ownership offsets, input-reader call graph and pinned ghost
codec come from Christopher Chedeau's MIT-licensed `vjeux/trackmania-tas`,
revision `036a65ba6aaef87b4579b8ee5a770729341dc572`, already retained by the
0.35 work. `tape.rs` calls `fk::tape::Tape` from that checkout. It does not
introduce another implementation of the GBX input codec. The existing local
0.35 compatibility patches remain separate. The new shim does not depend on
the fork shim or the GPL Gearbox implementation.

The original-call instruction bytes are checked before installing three
in-memory INT3 instrumentation points. The handler emulates the intercepted
`mov`, `call` and `mov` and preserves the saved register/flag context. The
input decoder and subsequent complete physics execute in the original
continuous parent process. There is no fork checkpoint or fitted clock.

MIT License

Copyright (c) 2026 Christopher Chedeau

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
