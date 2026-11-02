"""Run complete original position sweeps, including profiling and trig calls.

Synthetic TLS disables profiling through its ordinary null-profiler branch.
Original code is unmodified. Domain: scalar SSE2 trig dispatch and correction
norm <=1.57079625; other dispatch/reduction domains remain unqualified.
"""
import argparse
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from physics_emulator import PhysicsEmulator,ROOT,SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_GS_BASE,UC_X86_REG_RIP


def run(executable,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid position case count')
    e=PhysicsEmulator(executable,[(0x8603b0,0x860d55),(0x85e4f0,0x85eab0),
        (0x192c70,0x192ce0),(0x1886d0,0x188800),(0x195c010,0x195c2d9),
        (0x195d240,0x195d5cf),(0x1175b0,0x1176ee)])
    m=e.mu;teb=0x300000000;m.mem_map(teb,0x4000)
    m.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));m.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000))
    m.reg_write(UC_X86_REG_GS_BASE,teb)
    states=e.memory;coeff=states+0x1000;config=states+0x1100;dynamic=states+0x1200;fixed=states+0x1300;span=states+0x1400
    entries={}
    def hit(_mu,address,_size,_data):entries[address-e.base]=entries.get(address-e.base,0)+1
    for root in [0x8603b0,0x860980,0x85e4f0,0x85e7d0,0x192c70,0x195c010,0x195d240,
        0x117690,0x1175b0,0x1176a0,0x860627,0x860b63,0x195d2b9,0x195d2e0,0x195d310]:
        m.hook_add(UC_HOOK_CODE,hit,begin=e.base+root,end=e.base+root)
    rng=random.Random(2026102304);cases=[];expected=bytearray()
    def floats(values):return struct.pack('<'+'f'*len(values),*values)
    def vector(scale=1):return [rng.uniform(-scale,scale) for _ in range(3)]
    for n in range(count):
        state=bytearray()
        for j in range(3):
            # Include arbitrary finite matrices as well as exact orthogonal
            # matrices; the solver consumes the stored matrix without repair.
            rotation=[1,0,0,0,1,0,0,0,1] if n%3 else [rng.uniform(-1,1) for _ in range(9)]
            quaternion=[1,0,0,0] if n%5 else [rng.uniform(-1,1) for _ in range(4)]
            state+=floats(rotation+vector()+quaternion+vector(4)+vector(2))
        coefficients=floats([rng.uniform(.01,.2) for _ in range(12)])
        parameters=floats([rng.uniform(-.05,.05),rng.uniform(.001,.02),rng.uniform(0,.5)])
        dc=bytearray();sc=bytearray()
        for j in range(2):
            a=j;b=j if n%17==0 else j+1
            normal=vector();normal=[0,-0.,0] if n%23==0 else normal
            pa=vector();pb=vector()
            dc+=struct.pack('<2I',a,b)+floats(pa+pb+normal)
            sc+=struct.pack('<I',a)+floats(pa+pb+normal)
        batch_count=0 if n%29==0 else 2
        wire=bytes(state)+coefficients+parameters+dc+sc+struct.pack('<I',batch_count)
        if len(wire)!=496:raise AssertionError('Position wire schema changed')
        cases.append(wire);m.mem_write(coeff,coefficients);m.mem_write(config,bytes(20)+parameters)
        m.mem_write(dynamic,bytes(dc));m.mem_write(fixed,bytes(sc))
        for root,buffer in [(0x8603b0,dynamic),(0x860980,fixed)]:
            m.mem_write(states,bytes(state));m.mem_write(span,struct.pack('<Q2I',buffer,batch_count,0));e.reset_stack()
            m.mem_write(e.rsp+0x28,struct.pack('<Q',config))
            for reg,value in [(UC_X86_REG_RCX,coeff),(UC_X86_REG_RDX,states),(UC_X86_REG_R8,0),(UC_X86_REG_R9,span)]:m.reg_write(reg,value)
            if e.run(root,budget=20000)!=e.sentinel:raise RuntimeError('Position routine exceeded instruction budget')
            expected+=m.mem_read(states,264)
    out.mkdir(parents=True,exist_ok=True);inputs=out/'position-input.bin';outputs=out/'position-ported.bin'
    inputs.write_bytes(struct.pack('<I',count)+b''.join(cases));subprocess.run([str(fixture),str(inputs),str(outputs)],check=True)
    actual=outputs.read_bytes()
    if actual!=expected:
        if len(actual)!=len(expected):raise AssertionError('Position output length mismatch')
        off=next(i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b)
        begin=off&~3
        raise AssertionError(f'Position mismatch case={off//528} sweep={(off%528)//264} byte={off%264} expected={struct.unpack_from("<f",expected,begin)[0]} actual={struct.unpack_from("<f",actual,begin)[0]}')
    required={0x8603b0,0x860980,0x85e4f0,0x85e7d0,0x192c70,0x195c010,0x195d240,0x117690,0x1175b0,0x1176a0,0x860627,0x860b63}
    if not required.issubset(entries):raise AssertionError('Position execution coverage missing')
    report={'schema':'tm2020_position_oracle_v1','sha256':SHA,'casesPerSweep':count,'sweeps':2,'bitExact':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4','syntheticTlsProfilerDisabled':True,
        'mathDispatch':'scalar SSE2 flag 0','maximumCorrectionAngle':1.57079625,'allTrigDomainsRecovered':False,
        'executedEntries':{hex(k):v for k,v in sorted(entries.items())},'gameProcessAccessed':False,
        'completePhysics':False,'expectedOutputSha256':hashlib.sha256(expected).hexdigest()}
    (out/'recovered-position-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS ORIGINAL_POSITION_SWEEPS cases_each={count} bit_exact=true unmodified_code=true bounded_angle=true')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_position_fixture.exe')
    p.add_argument('--out',type=Path,default=ROOT/'local/recon/position-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
