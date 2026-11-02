"""Original triangle AABB loop, bounded before native allocation/tree calls.

Consumes the cooking oracle's same binary32 fixtures. Starts at the original
count test and stops before tree construction. No patched/skipped instructions
within that bounded operation; no complete mesh-constructor claim.
"""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from physics_emulator import PhysicsEmulator,ROOT,SHA
from unicorn.x86_const import UC_X86_REG_RSP,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_RBP,UC_X86_REG_RDI,UC_X86_REG_RSI


def run(exe,fixture,inputs,out):
    wire=inputs.read_bytes();count=struct.unpack_from('<I',wire)[0]
    if count!=20000 or len(wire)!=4+count*256:raise ValueError('Expected current 20,000-case cooking fixtures')
    e=PhysicsEmulator(exe,[(0x1ae3ba,0x1ae55a)]);mu=e.mu;vertices=e.memory;triangles=vertices+0x1000;bounds=vertices+0x2000;expected=bytearray()
    for n in range(count):
        row=wire[4+n*256:4+(n+1)*256];size=struct.unpack_from('<I',row,252)[0]
        mu.mem_write(vertices,row[:108]);mu.mem_write(triangles,row[108:252]);mu.mem_write(bounds,bytes(9*28));e.reset_stack()
        for reg,value in [(UC_X86_REG_RSP,e.rsp-8),(UC_X86_REG_R8,size),(UC_X86_REG_R9,bounds),(UC_X86_REG_RBP,triangles),(UC_X86_REG_RDI,vertices),(UC_X86_REG_RSI,0)]:mu.reg_write(reg,value)
        if e.run(0x1ae3ba,stop=0x1ae55a,budget=5000)!=e.base+0x1ae55a:raise RuntimeError('Original bounds slice exceeded budget')
        expected+=mu.mem_read(bounds,9*28)
    out.mkdir(parents=True,exist_ok=True);outputs=out/'bounds-ported.bin'
    subprocess.run([str(fixture),str(inputs),str(outputs),'bounds'],check=True);actual=outputs.read_bytes()
    if actual!=expected:
        if len(actual)!=len(expected):raise AssertionError('Triangle bounds output size differs')
        at=next(i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b)
        raise AssertionError(f'Triangle bounds mismatch case={at//252} byte={at%252} expected={expected[at]} actual={actual[at]}')
    report={'schema':'tm2020_triangle_bounds_oracle_v1','sha256':SHA,'cases':count,'bitExact':True,
        'startRva':'0x1ae3ba','stopRva':'0x1ae55a','originalCodeModified':False,'boundedOperation':True,
        'wholeMeshConstructorQualified':False,'inputFixtureSha256':hashlib.sha256(wire).hexdigest(),
        'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),'gameProcessAccessed':False,'completePhysics':False}
    (out/'recovered-bounds-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS ORIGINAL_TRIANGLE_BOUNDS cases=20000 bit_exact=true bounded_operation=true')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_cook_fixture.exe');p.add_argument('--inputs',type=Path,default=ROOT/'local/recon/cooking-oracle/cook-input.bin')
    p.add_argument('--out',type=Path,default=ROOT/'local/recon/bounds-oracle');a=p.parse_args();run(a.exe,a.fixture,a.inputs,a.out)
