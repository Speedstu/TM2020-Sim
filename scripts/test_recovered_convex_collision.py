"""Whole convex/convex handler, synthetic TLS/arena, no skipped instructions."""
import argparse
import hashlib
import json
import math
import random
import struct
import subprocess
from pathlib import Path
from pe_unwind import PeCode
from physics_emulator import PhysicsEmulator,ROOT,SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_GS_BASE,UC_X86_REG_RBP,UC_X86_REG_RAX

FACE_INDICES=[(0,4,6,2),(1,3,7,5),(0,1,5,4),(2,6,7,3),(0,2,3,1),(4,5,7,6)]
EDGES=[(0,1,0),(2,3,0),(4,5,0),(6,7,0),(0,2,1),(1,3,1),(4,6,1),(5,7,1),(0,4,2),(1,5,2),(2,6,2),(3,7,2)]


def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]


def rotation(rng):
    q=[rng.uniform(-1,1) for _ in range(4)];length=math.sqrt(sum(x*x for x in q));w,x,y,z=[v/length for v in q]
    return [1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y),2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x),2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]


def shape(mu,address,half):
    vertices=address+0x100;normals=address+0x200;faces=address+0x300;indices=address+0x500;edges=address+0x600
    mu.mem_write(vertices,struct.pack('<24f',*(half[k] if i&(1<<k) else -half[k] for i in range(8) for k in range(3))))
    mu.mem_write(normals,struct.pack('<9f',1,0,0,0,1,0,0,0,1))
    raw=bytearray(6*40)
    for i,face in enumerate(FACE_INDICES):
        mu.mem_write(indices+i*16,struct.pack('<4I',*face));struct.pack_into('<2IQII',raw,i*40+16,i//2,i%2,indices+i*16,4,0)
    mu.mem_write(faces,bytes(raw));mu.mem_write(edges,struct.pack('<36I',*(v for edge in EDGES for v in edge)))
    mu.mem_write(address,b''.join(struct.pack('<QII',p,n,0) for p,n in [(vertices,8),(normals,3),(normals,3),(faces,6),(edges,12)]))


def run(exe,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid convex count')
    code=PeCode(exe);roots=[0x19cec0,0x1844e0,0x19c430,0x19ee30,0x11d8d0,0x11daa0,0x11dac0,0x1cae40,0x1cad10,0x1cab20,
        0x1cb980,0x1cbcb0,0x1cbef0,0x1cc200,0x183bd0,0x1cca10,0x19ed30,0x1cc3e0,0x1c9080]
    ranges=[(r.begin,r.end) for root in roots for r in code.index.groups[root]]
    ranges += [(0x11da80,0x11da97),(0x1cc390,0x1cc3d5),(0x197890,0x1978b2),(0x1521930,0x1521945)]
    e=PhysicsEmulator(exe,ranges);mu=e.mu;teb=0x300000000;mu.mem_map(teb,0x4000)
    mu.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));mu.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000));mu.mem_write(teb+0x2010,b'\x01');mu.reg_write(UC_X86_REG_GS_BASE,teb)
    scratch=e.memory+0x10000;scratch_end=e.memory+0x20000;arena=teb+0x2160
    a=e.memory+0x1000;b=e.memory+0x3000;ia=e.memory+0x6000;ib=e.memory+0x6100;query=e.memory+0x6200;output=e.memory+0x6300;contacts=e.memory+0x6400
    hits={};witnesses=[0,0,0]
    def hit(_mu,address,_size,_data):hits[address-e.base]=hits.get(address-e.base,0)+1
    def witness(_mu,_address,_size,_data):
        if mu.reg_read(UC_X86_REG_RAX):witnesses[mu.mem_read(mu.reg_read(UC_X86_REG_RBP)-0x70,1)[0]]+=1
    mu.hook_add(UC_HOOK_CODE,witness,begin=e.base+0x19d001,end=e.base+0x19d001)
    for root in roots:mu.hook_add(UC_HOOK_CODE,hit,begin=e.base+root,end=e.base+root)
    def original(id_a,id_b,boolean=False,gate=False):
        mu.mem_write(arena,struct.pack('<4QI',scratch,scratch_end,scratch,scratch_end,0))
        mu.mem_write(output,struct.pack('<Q4I',contacts,0,0,32,0));mu.mem_write(query,struct.pack('<IIQII',0,0,0 if boolean else output,int(gate),0))
        e.reset_stack();mu.mem_write(e.rsp+0x28,struct.pack('<3Q',ia,ib,query))
        for register,value in [(UC_X86_REG_RCX,a),(UC_X86_REG_RDX,id_a),(UC_X86_REG_R8,b),(UC_X86_REG_R9,id_b)]:mu.reg_write(register,value)
        if e.run(0x19cec0,budget=100000)!=e.sentinel:raise RuntimeError('Complete convex handler exceeded instruction budget')
        hit_flag,_,_,early,_=struct.unpack('<IIQII',mu.mem_read(query,24));size=struct.unpack('<I',mu.mem_read(output+8,4))[0]
        if struct.unpack('<Q',mu.mem_read(arena+0x10,8))[0]!=scratch:raise AssertionError('Original scratch frames were not rewound')
        if size>32:raise AssertionError('Native contact capacity exceeded')
        return bool(hit_flag),early,size,bytes(mu.mem_read(contacts,size*88))
    rng=random.Random(2026102314);inputs=[];expected=bytearray();total_contacts=0;overlaps=0
    for n in range(count):
        identity=[1,0,0,0,1,0,0,0,1];ra,rb=rotation(rng),rotation(rng);ta=[rng.uniform(-2,2) for _ in range(3)];tb=[rng.uniform(-2,2) for _ in range(3)]
        ha=[rng.uniform(.2,1.5) for _ in range(3)];hb=[rng.uniform(.2,1.5) for _ in range(3)]
        if n%5==0:ra=identity[:];rb=identity[:]
        if n%11==0:ta=[0,0,0];tb=[1.5,0,0];ha=[1,1,1];hb=[1,1,1];ra=identity[:];rb=identity[:]
        if n%13==0:ta=[0,0,0];tb=[2,0,0];ha=[1,1,1];hb=[1,1,1];ra=identity[:];rb=identity[:]
        if n%17==0:tb=[ta[k]+10 for k in range(3)]
        if n%19==0:ra=identity[:];rb=identity[:];ta=[0,0,0];tb=[0,0,0]
        id_a,id_b=rng.randrange(65536),rng.randrange(65536)
        row=struct.pack('<30f2H',*(ra+ta+rb+tb+ha+hb),id_a,id_b);inputs.append(row);v=struct.unpack('<30f2H',row)
        shape(mu,a,v[24:27]);shape(mu,b,v[27:30]);mu.mem_write(ia,struct.pack('<Q12f',a,*v[:12]));mu.mem_write(ib,struct.pack('<Q12f',b,*v[12:24]))
        overlap,early,size,raw=original(id_a,id_b);expected+=struct.pack('<II',overlap,size)
        for j in range(size):
            record=raw[j*88:(j+1)*88]
            if struct.unpack_from('<2Q',record)!=(ia,ib) or struct.unpack_from('<I',record,84)[0]&3:raise AssertionError('Defined native convex contact ownership/flags differ')
            expected+=record[16:52]+record[80:84]
        total_contacts+=size;overlaps+=int(overlap)
        if n%29==0:
            boolean,early,number,_=original(id_a,id_b,boolean=True)
            if boolean!=overlap or number or early!=int(overlap):raise AssertionError('Native boolean query differs')
        if n%31==0:
            gated,_,number,_=original(id_a,id_b,gate=True)
            if gated!=overlap or number:raise AssertionError('Native contact emission gate differs')
        if n and n%1000==0:print('ORIGINAL_CONVEX_PROGRESS',n,'contacts',total_contacts,flush=True)
    out.mkdir(parents=True,exist_ok=True);inp=out/'convex-input.bin';result=out/'convex-ported.bin'
    inp.write_bytes(struct.pack('<I',count)+b''.join(inputs));subprocess.run([str(fixture),str(inp),str(result)],check=True);actual=result.read_bytes()
    if actual!=expected:
        position=0
        for n in range(count):
            overlap,size=struct.unpack_from('<II',expected,position);length=8+size*40
            if actual[position:position+length]!=expected[position:position+length]:
                left=expected[position:position+length];right=actual[position:position+length]
                at=next((i for i,(x,y) in enumerate(zip(left,right)) if x!=y),min(len(left),len(right)))
                raise AssertionError(f'Convex handler mismatch case={n} byte={at} expected_header={struct.unpack_from("<II",expected,position)} actual_header={struct.unpack_from("<II",actual,position)}')
            position+=length
        raise AssertionError('Convex output length differs')
    if count>=1000 and not all(witnesses):raise AssertionError('Convex witness branch not covered')
    report={'schema':'tm2020_convex_collision_oracle_v1','sha256':SHA,'cases':count,'operations':1,'bitExactDefinedOutputs':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4','entryRva':'0x19cec0',
        'overlapCases':overlaps,'contactPointsCompared':total_contacts,'witnessBranchExecutions':witnesses,
        'undefinedContactFieldsCompared':False,'syntheticTlsAlreadyInitialized':True,'precommittedScratchArena':True,
        'originalFrameCleanupVerified':True,'booleanAndEmissionGatesQualified':True,'convexPolyhedraFixture':'independent boxes with arbitrary 3D rigid transforms',
        'nativeAllocationQualified':False,'nearParallelUndefinedClipBranchQualified':False,
        'executedEntries':{hex(k):v for k,v in sorted(hits.items())},'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),
        'gameProcessAccessed':False,'completePhysics':False}
    (out/'recovered-convex-collision-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS ORIGINAL_CONVEX_COLLISION cases={count} contacts={total_contacts} defined_outputs_bit_exact=true full_physics=false')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_convex_collision_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/convex-collision-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
