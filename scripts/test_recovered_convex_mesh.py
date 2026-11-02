"""Original complete convex/mesh handler versus owned C++ geometry pipeline."""
import argparse
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from pe_unwind import PeCode
from physics_emulator import PhysicsEmulator,ROOT,SHA
from test_recovered_convex_collision import shape,rotation
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_RAX,UC_X86_REG_GS_BASE


def run(exe,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid convex mesh count')
    code=PeCode(exe);roots=[0x1b4410,0x1b4260,0x1844e0,0x183bd0,0x11d8d0,0x11daa0,0x11dac0,0x1cae40,0x1cad10,0x1cab20,
        0x1cb980,0x1cbcb0,0x1cbef0,0x1cc200,0x1cca10,0x19ed30,0x1cc3e0,0x1c9080,0x1a01b0]
    ranges=[(r.begin,r.end) for root in roots for r in code.index.groups[root]]
    ranges += [(0x11da80,0x11da97),(0x1cc390,0x1cc3d5),(0x197890,0x1978b2),(0x1521930,0x1521945),
        (0x1175b0,0x1176ee),(0x1b4160,0x1b4260),(0x144630,0x1446ce),(0x185f70,0x1860b4),(0x1522620,0x152266e)]
    e=PhysicsEmulator(exe,ranges);mu=e.mu;teb=0x300000000;mu.mem_map(teb,0x4000)
    mu.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));mu.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000));mu.mem_write(teb+0x2010,b'\x01');mu.mem_write(teb+0x10,struct.pack('<Q',e.stack));mu.reg_write(UC_X86_REG_GS_BASE,teb)
    scratch=e.memory+0x10000;scratch_end=e.memory+0x20000;arena=teb+0x2160
    a=e.memory+0x1000;mesh=e.memory+0x3000;ia=e.memory+0x6000;ib=e.memory+0x6100;query=e.memory+0x6200;output=e.memory+0x6300;contacts=e.memory+0x22000;bounds=e.memory+0x7f00
    mu.mem_map(e.memory+0x20000,0x40000)
    vertices=mesh+0x100;triangles=mesh+0x200;nodes=mesh+0x300
    points=[(-2,0,-2),(-2,0,2),(2,0,2),(2,0,-2),(-2,0,-2),(2,0,-2),(2,3,-2)]
    mu.mem_write(vertices,struct.pack('<21f',*(x for p in points for x in p)))
    raw_triangles=b''.join(struct.pack('<4f3I2H',*normal,plane,*indices,material,0) for normal,plane,indices,material in [((0,1,0),0,(0,1,2),11),((0,1,0),0,(0,2,3),12),((0,0,1),2,(4,5,6),13)])
    mu.mem_write(triangles,raw_triangles)
    tree=[((0,1.5,0),(2,1.5,2),10),((0,0,0),(2,0,2),6),((0,0,0),(2,0,2),1),((0,0,0),(2,0,2),3),((0,1.5,-2),(2,1.5,0),5)]
    mu.mem_write(nodes,b''.join(struct.pack('<6fI',*(center+half),tag) for center,half,tag in tree))
    mu.mem_write(mesh+0x20,struct.pack('<QII',vertices,7,7));mu.mem_write(mesh+0x40,struct.pack('<QII',triangles,3,3))
    hits={};witnesses=[0,0,0];last_axis=[0]
    def hit(_mu,address,_size,_data):hits[address-e.base]=hits.get(address-e.base,0)+1
    def axis_entry(_mu,_address,_size,_data):last_axis[0]=mu.reg_read(UC_X86_REG_R9)
    def axis_exit(_mu,_address,_size,_data):
        if mu.reg_read(UC_X86_REG_RAX):witnesses[mu.mem_read(last_axis[0]+16,1)[0]]+=1
    for root in roots:mu.hook_add(UC_HOOK_CODE,hit,begin=e.base+root,end=e.base+root)
    mu.hook_add(UC_HOOK_CODE,axis_entry,begin=e.base+0x1cae40,end=e.base+0x1cae40)
    mu.hook_add(UC_HOOK_CODE,axis_exit,begin=e.base+0x1b481a,end=e.base+0x1b481a)
    def original(material,boolean=False,gate=False,budget=200000):
        mu.mem_write(arena,struct.pack('<4QI',scratch,scratch_end,scratch,scratch_end,0))
        mu.mem_write(output,struct.pack('<Q4I',contacts,0,0,1024,0));mu.mem_write(query,struct.pack('<IIQII',0,0,0 if boolean else output,int(gate),0))
        e.reset_stack();mu.mem_write(e.rsp+0x28,struct.pack('<3Q',ib,0,query))
        for register,value in [(UC_X86_REG_RCX,a),(UC_X86_REG_RDX,bounds),(UC_X86_REG_R8,material),(UC_X86_REG_R9,ia)]:mu.reg_write(register,value)
        if e.run(0x1b4410,budget=budget)!=e.sentinel:raise RuntimeError('Whole convex mesh handler exceeded budget')
        hit_flag,_,_,early,_=struct.unpack('<IIQII',mu.mem_read(query,24));size=struct.unpack('<I',mu.mem_read(output+8,4))[0]
        if struct.unpack('<Q',mu.mem_read(arena+0x10,8))[0]!=scratch:raise AssertionError('Original convex mesh scratch not rewound')
        if size>1024:raise AssertionError('Native convex mesh contact capacity exceeded')
        return bool(hit_flag),early,size,bytes(mu.mem_read(contacts,size*88))
    rng=random.Random(2026102315);inputs=[];expected=bytearray();total_contacts=0;overlaps=0
    for n in range(count):
        identity=[1,0,0,0,1,0,0,0,1];ra,rm=rotation(rng),rotation(rng);ta=[rng.uniform(-3,3),rng.uniform(-1.5,2),rng.uniform(-3,3)];tm=[rng.uniform(-1,1) for _ in range(3)];half=[rng.uniform(.1,1) for _ in range(3)]
        if n%3==0:ra=identity[:];rm=identity[:];tm=[0,0,0]
        if n%11==0:ra=identity[:];rm=identity[:];tm=[0,0,0];ta=[0,.5,0];half=[1,1,1]
        if n%13==0:ra=identity[:];rm=identity[:];tm=[0,0,0];ta=[0,1,0];half=[1,1,1]
        if n%17==0:ra=identity[:];rm=identity[:];tm=[0,0,0];ta=[0,-.5,0];half=[1,1,1]
        material=rng.randrange(65536);row=struct.pack('<27fHH',*(ra+ta+rm+tm+half),material,0);inputs.append(row);v=struct.unpack('<27fHH',row)
        shape(mu,a,v[24:27]);mu.mem_write(ia,struct.pack('<Q12f',a,*v[:12]));mu.mem_write(ib,struct.pack('<Q12f',mesh,*v[12:24]));mu.mem_write(bounds,struct.pack('<6f',0,0,0,*v[24:27]));mu.mem_write(mesh+0x50,struct.pack('<QII',nodes,0 if n%37==0 else 5,5))
        overlap,_,size,raw=original(material);expected+=struct.pack('<II',overlap,size)
        for j in range(size):
            record=raw[j*88:(j+1)*88]
            if struct.unpack_from('<2Q',record)!=(ia,ib) or struct.unpack_from('<I',record,84)[0]&3:raise AssertionError('Defined native convex mesh ownership/flags differ')
            expected+=record[16:52]+record[80:84]
        overlaps+=int(overlap);total_contacts+=size
        if n%29==0:
            boolean,early,number,_=original(material,boolean=True)
            if boolean!=overlap or number or early!=int(overlap):raise AssertionError('Native convex mesh boolean differs')
        if n%31==0:
            gated,_,number,_=original(material,gate=True)
            if gated!=overlap or number:raise AssertionError('Native convex mesh emission gate differs')
        if n and n%1000==0:print('ORIGINAL_CONVEX_MESH_PROGRESS',n,'contacts',total_contacts,flush=True)
    out.mkdir(parents=True,exist_ok=True);inp=out/'convex-mesh-input.bin';result=out/'convex-mesh-ported.bin';inp.write_bytes(struct.pack('<I',count)+b''.join(inputs))
    subprocess.run([str(fixture),str(inp),str(result)],check=True);actual=result.read_bytes()
    if actual!=expected:
        position=0
        for n in range(count):
            overlap,size=struct.unpack_from('<II',expected,position);length=8+size*40
            if actual[position:position+length]!=expected[position:position+length]:
                left=expected[position:position+length];right=actual[position:position+length];at=next((i for i,(x,y) in enumerate(zip(left,right)) if x!=y),min(len(left),len(right)))
                raise AssertionError(f'Convex mesh mismatch case={n} byte={at} expected_header={struct.unpack_from("<II",expected,position)} actual_header={struct.unpack_from("<II",actual,position)}')
            position+=length
        raise AssertionError('Convex mesh output length differs')
    if count>=1000 and not all(witnesses):raise AssertionError('Convex mesh witness branch not covered')
    # More than 128 SAT overlaps exercise the original fixed candidate array,
    # including its cache insertion paths and preservation of native emission.
    cap_triangles=e.memory+0x8000;cap_nodes=e.memory+0xa000
    mu.mem_write(cap_triangles,b''.join(struct.pack('<4f3I2H',0,1,0,0,0,1,2,j,0) for j in range(129)))
    mu.mem_write(cap_nodes,b''.join(struct.pack('<6fI',0,0,0,2,0,2,(j<<1)|1) for j in range(129)))
    mu.mem_write(mesh+0x40,struct.pack('<QII',cap_triangles,129,129));mu.mem_write(mesh+0x50,struct.pack('<QII',cap_nodes,129,129))
    identity=[1,0,0,0,1,0,0,0,1];shape(mu,a,(1,1,1));mu.mem_write(ia,struct.pack('<Q12f',a,*(identity+[0,.5,0])));mu.mem_write(ib,struct.pack('<Q12f',mesh,*(identity+[0,0,0])));mu.mem_write(bounds,struct.pack('<6f',0,0,0,1,1,1))
    cap_hit,_,cap_count,cap_raw=original(7,budget=2000000);cap_expected=bytearray(struct.pack('<II',cap_hit,cap_count));cap_ids=[]
    for j in range(cap_count):
        record=cap_raw[j*88:(j+1)*88];cap_expected+=record[16:52]+record[80:84];cap_ids.append(struct.unpack_from('<H',record,82)[0])
    if set(cap_ids)!=set(range(128)):raise AssertionError('Original candidate saturation did not retain first 128 triangle IDs')
    cap_input=out/'convex-mesh-cap-input.bin';cap_output=out/'convex-mesh-cap-ported.bin'
    cap_input.write_bytes(struct.pack('<I27fHH',1,*(identity+[0,.5,0]+identity+[0,0,0]+[1,1,1]),7,1))
    subprocess.run([str(fixture),str(cap_input),str(cap_output)],check=True)
    if cap_output.read_bytes()!=cap_expected:raise AssertionError('Native 128-triangle saturation differs from port')
    report={'schema':'tm2020_convex_mesh_oracle_v1','sha256':SHA,'cases':count,'operations':1,'bitExactDefinedOutputs':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4','entryRva':'0x1b4410','overlapCases':overlaps,'contactPointsCompared':total_contacts,
        'witnessBranchExecutions':witnesses,'undefinedContactFieldsCompared':False,'syntheticTlsAlreadyInitialized':True,'precommittedScratchArena':True,
        'originalFrameCleanupVerified':True,'booleanAndEmissionGatesQualified':True,'fixture':'independent box, two shared-edge floor triangles and wall; arbitrary 3D transforms',
        'candidateCapSaturationQualified':True,'saturationInputOverlaps':129,'retainedSaturationTriangleIds':128,'saturationContactPointsCompared':cap_count,
        'nativeAllocationQualified':False,'nearParallelUndefinedClipBranchQualified':False,
        'executedEntries':{hex(k):v for k,v in sorted(hits.items())},'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),'gameProcessAccessed':False,'completePhysics':False}
    (out/'recovered-convex-mesh-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS ORIGINAL_CONVEX_MESH cases={count} contacts={total_contacts} defined_outputs_bit_exact=true full_physics=false')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_convex_mesh_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/convex-mesh-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
