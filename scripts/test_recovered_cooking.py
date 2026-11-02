"""Compare the complete original mesh cooker with C++, without allocation.

Preallocated output buffers, synthetic null-profiler TLS; execute every original
instruction in the selected path, including resize and profiling helpers.
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
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_GS_BASE


def run(exe,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid cooking case count')
    e=PhysicsEmulator(exe,[(0x1adb10,0x1ae355),(0x1b7150,0x1b7185),(0x1175b0,0x1176ee)])
    mu=e.mu;teb=0x300000000;mu.mem_map(teb,0x4000)
    mu.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));mu.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000));mu.reg_write(UC_X86_REG_GS_BASE,teb)
    mesh=e.memory;vertices=mesh+0x1000;triangles=mesh+0x2000;cooked=mesh+0x3000
    hits={}
    def hit(_mu,address,_size,_data):hits[address-e.base]=hits.get(address-e.base,0)+1
    for at in [0x1adb10,0x1b7150,0x117690,0x1175b0,0x1176a0,0x1adbf0,0x1ae18e,0x1add15,0x1add00]:
        mu.hook_add(UC_HOOK_CODE,hit,begin=e.base+at,end=e.base+at)
    rng=random.Random(2026102307);cases=[];expected=bytearray()
    for n in range(count):
        points=[[rng.uniform(-10,10) for _ in range(3)] for _ in range(9)]
        if n%11==0:points[1]=points[0][:]
        if n%13==0:points=[[x*1e-7 for x in p] for p in points]
        if n%17==0:points=[[x*1e-3 for x in p] for p in points]
        if n%19==0:points=[[0.,-0.,0.] for _ in points]
        vertex_bytes=struct.pack('<27f',*(v for p in points for v in p));raw=bytearray()
        for j in range(9):
            ids=[rng.randrange(9) for _ in range(3)]
            if j==0:ids=[0,1,2]
            raw+=struct.pack('<3I2H',*ids,rng.randrange(65536),rng.randrange(65536))
        size=n%10;cases.append(vertex_bytes+raw+struct.pack('<I',size))
        obj=bytearray(0x60);struct.pack_into('<Q',obj,0x20,vertices);struct.pack_into('<Q2I',obj,0x30,triangles,size,9)
        struct.pack_into('<Q2I',obj,0x40,cooked,0,9);mu.mem_write(mesh,bytes(obj));mu.mem_write(vertices,vertex_bytes);mu.mem_write(triangles,bytes(raw));mu.mem_write(cooked,bytes(9*32))
        e.reset_stack();mu.reg_write(UC_X86_REG_RCX,mesh)
        if e.run(0x1adb10,budget=20000)!=e.sentinel:raise RuntimeError('Original cooker exceeded instruction budget')
        if struct.unpack('<I',mu.mem_read(mesh+0x48,4))[0]!=size:raise AssertionError('Original cooked count differs')
        expected+=mu.mem_read(cooked,9*32)
    out.mkdir(parents=True,exist_ok=True);inp=out/'cook-input.bin';result=out/'cook-ported.bin'
    inp.write_bytes(struct.pack('<I',count)+b''.join(cases));subprocess.run([str(fixture),str(inp),str(result)],check=True)
    actual=result.read_bytes()
    if actual!=expected:
        if len(actual)!=len(expected):raise AssertionError('Cooking fixture output size differs')
        at=next(i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b);start=at&~3
        raise AssertionError(f'Cooking mismatch case={at//288} byte={at%288} expected={struct.unpack_from("<f",expected,start)[0]} actual={struct.unpack_from("<f",actual,start)[0]}')
    if not {0x1adb10,0x1b7150,0x117690,0x1175b0,0x1176a0,0x1adbf0,0x1ae18e,0x1add15,0x1add00}.issubset(hits):raise AssertionError('Cooking branch coverage missing')
    report={'schema':'tm2020_mesh_cooking_oracle_v1','sha256':SHA,'cases':count,'bitExact':True,'originalCodeModified':False,
        'functionsSkipped':False,'emulator':'Unicorn 2.1.4','sufficientOutputCapacity':True,'allocationPathQualified':False,
        'syntheticTlsProfilerDisabled':True,'nativeUnrolledAndRemainderBranchesCovered':True,
        'executedEntries':{hex(k):v for k,v in sorted(hits.items())},'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),
        'gameProcessAccessed':False,'gameAssetsDecoded':False,'completePhysics':False}
    (out/'recovered-cooking-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS ORIGINAL_MESH_COOKER cases='+str(count),'bit_exact=true unmodified_code=true')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_cook_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/cooking-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
