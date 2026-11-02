"""Whole original contact-patch grouping and geometry-to-depth conversion."""
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
from unicorn import UC_HOOK_CODE,UC_PROT_READ,UC_PROT_WRITE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_GS_BASE,UC_X86_REG_RIP


def run(exe,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid patch case count')
    code=PeCode(exe);roots=[0x804a10,0x805490,0x805f70,0x13a5a50,0x11d8d0,0x11daa0,0x7bf0d0,0x7d7cb0]
    ranges=[(r.begin,r.end) for root in roots for r in code.index.groups[root]]+[(0x11da80,0x11da97),(0x514110,0x514114),(0x4eff20,0x4eff4a),(0x4df599,0x4dfbb8),(0x1521930,0x1521945)]
    e=PhysicsEmulator(exe,ranges);m=e.mu;m.mem_map(e.memory+0x20000,0xe0000)
    for page in [0x1fa9000,0x1e70000,0x20cb000]:m.mem_protect(e.base+page,0x1000,UC_PROT_READ|UC_PROT_WRITE)
    e.reset_stack()
    if e.run(0x4df599,stop=0x4dfbb8,budget=1000)!=e.base+0x4dfbb8:raise RuntimeError('Original material initialization failed')
    teb=0x300000000;m.mem_map(teb,0x4000);m.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));m.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000));m.mem_write(teb+0x2010,b'\x01');m.mem_write(teb+0x2014,struct.pack('<i',0x7fffffff));m.reg_write(UC_X86_REG_GS_BASE,teb)
    base=e.memory;main=base+0x1000;node=base+0x2000;raw_contacts=base+0x10000;span=base+0xe000;record_buffer=base+0x70000;pool=base+0x30000;scratch=base+0x90000;arena=teb+0x2160
    sa,da,va,ca=base+0x3000,base+0x4000,base+0x5000,base+0x6000;sb,db,vb,cb=base+0x8000,base+0x9000,base+0xa000,base+0xb000
    for shape,data,vehicle,config in [(sa,da,va,ca),(sb,db,vb,cb)]:m.mem_write(shape+0x38,struct.pack('<Q',data));m.mem_write(data+8,struct.pack('<Q',vehicle));m.mem_write(vehicle+0x88,struct.pack('<Q',config))
    hits={}
    def hit(_mu,address,_size,_data):hits[address-e.base]=hits.get(address-e.base,0)+1
    for root in roots:m.hook_add(UC_HOOK_CODE,hit,begin=e.base+root,end=e.base+root)
    rng=random.Random(2026102319);inputs=[];expected=bytearray();total_points=total_patches=multichunk=0
    normals=[(1,0,0),(0,1,0),(0,0,1),(-1,0,0),(math.cos(.02),math.sin(.02),0),(math.cos(.06),math.sin(.06),0),(.999,0,0)]
    for n in range(count):
        runtime=0x30abc000;classes=[0x0a020000,runtime,0x0a0aa000,0x0a030000];ka,kb=classes[(n//4)%4],classes[n%4];variant_a,variant_b=[5,9,13][(n//16)%3],[5,9,13][(n//48)%3];category_a,category_b=(n//144)%2,(n//288)%2
        parameters=[rng.uniform(0,1) for _ in range(5)];objects=[ka,variant_a,category_a,kb,variant_b,category_b,runtime]
        number=n%64
        if n%97==0:number=[255,256,511][(n//97)%3]
        head=struct.pack('<7I5fI',*objects,*parameters,number);parameters=struct.unpack('<7I5fI',head)[7:12];row=bytearray(head);original_contacts=bytearray()
        for j in range(number):
            normal=normals[((j//3)+(j%5==0))%len(normals)];ma,mb=(j//5)%3,(j//7)%4
            if n%13==0:normal=(0,1,0);ma=mb=1
            if n%17==0:normal=(0,1,0);ma=j%2;mb=1
            material_a=ma|(rng.randrange(256)<<8);material_b=mb|(rng.randrange(256)<<8)
            penetration=[rng.uniform(-1,1) for _ in range(3)];point=[rng.uniform(-10,10) for _ in range(3)]
            if n%19==0:penetration=[0,-0.,0]
            packed=struct.pack('<9f2H',*(penetration+list(normal)+point),material_a,material_b);row+=packed
            original_contacts+=struct.pack('<2Q',sa,sb)+packed[:36]+bytes(28)+packed[36:]+bytes(4)
        if len(original_contacts)!=number*88:raise AssertionError('Original contact schema changed')
        m.mem_write(raw_contacts,bytes(original_contacts) or bytes(4));m.mem_write(span,struct.pack('<Q2I',raw_contacts,number,number))
        m.mem_write(main,bytes(0x60));m.mem_write(main+0x20,struct.pack('<Q2I',record_buffer,0,1024));m.mem_write(main+0x30,struct.pack('<IIQQ',0x40000,1,node,node));m.mem_write(node,struct.pack('<QQIIQ',0,pool,0,0,0x40000));m.mem_write(arena,struct.pack('<4QI',scratch,scratch+0x10000,scratch,scratch+0x10000,0))
        m.mem_write(e.base+0x20cba88,struct.pack('<II',0,runtime));m.mem_write(e.base+0x1e70e10,struct.pack('<5f',*parameters))
        for data,config,klass,variant,category in [(da,ca,ka,variant_a,category_a),(db,cb,kb,variant_b,category_b)]:m.mem_write(data,struct.pack('<I',klass));m.mem_write(data+0x10,bytes([category,0]));m.mem_write(config+0x1790,struct.pack('<I',variant))
        e.reset_stack();m.mem_write(e.rsp+0x28,struct.pack('<Q',span))
        for register,value in [(UC_X86_REG_RCX,main),(UC_X86_REG_RDX,1<<32),(UC_X86_REG_R8,da),(UC_X86_REG_R9,db)]:m.reg_write(register,value)
        try:finished=e.run(0x804a10,budget=2000000)
        except Exception as error:raise RuntimeError(f'Original contact patch execution case={n} RIP={m.reg_read(UC_X86_REG_RIP)-e.base:#x}: {error}') from error
        if finished!=e.sentinel:raise RuntimeError('Original complete contact patch processor exceeded budget')
        if struct.unpack('<Q',m.mem_read(arena+0x10,8))[0]!=scratch:raise AssertionError('Original contact scratch not rewound')
        records=struct.unpack('<I',m.mem_read(main+0x28,4))[0];patches=[];points=0
        for r in range(records):
            raw=bytes(m.mem_read(record_buffer+48*r,48));ids,object_a,object_b,groups,positions=struct.unpack_from('<5Q',raw)
            if (ids,object_a,object_b)!=(1<<32,da,db):raise AssertionError('Original patch ownership metadata differs')
            number_points,group_count,first_chunk=struct.unpack_from('<3B',raw,40)
            if first_chunk!=int(r==0):raise AssertionError('Original patch first-chunk flag differs')
            for g in range(group_count):
                group=bytes(m.mem_read(groups+g*24,24));start,size=struct.unpack_from('<2B',group,20);points+=size
                patches.append(group[:20]+struct.pack('<II',size,first_chunk)+bytes(m.mem_read(positions+start*16,size*16)))
            if sum(struct.unpack_from('<I',p,20)[0] for p in patches[-group_count:])!=number_points:raise AssertionError('Original patch point count inconsistent')
        if points!=number:raise AssertionError('Original patch processor dropped geometry points')
        expected+=struct.pack('<I',len(patches))+b''.join(patches);inputs.append(row);total_points+=points;total_patches+=len(patches);multichunk+=records>1
        if n and n%1000==0:print('ORIGINAL_PATCH_PROGRESS',n,'points',total_points,flush=True)
    out.mkdir(parents=True,exist_ok=True);inp=out/'patch-input.bin';result=out/'patch-ported.bin';inp.write_bytes(struct.pack('<I',count)+b''.join(inputs));subprocess.run([str(fixture),str(inp),str(result)],check=True)
    actual=result.read_bytes()
    if actual!=expected:
        offset=next((j for j,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))
        position=0
        for n in range(count):
            start=position;groups=struct.unpack_from('<I',expected,position)[0];position+=4
            for _ in range(groups):size=struct.unpack_from('<I',expected,position+20)[0];position+=28+size*16
            if position>offset:break
        raise AssertionError(f'Contact patches differ case={n} output_byte={offset} case_byte={offset-start} expected_bytes={len(expected)} actual_bytes={len(actual)}')
    report={'schema':'tm2020_contact_patch_oracle_v1','sha256':SHA,'cases':count,'operations':1,'bitExactDefinedOutputs':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4','entryRva':'0x804a10',
        'contactPointsCompared':total_points,'patchesCompared':total_patches,'multiChunkCases':multichunk,'maximumContactsPerChunk':255,
        'allOriginalMaterialResponseCallsExecute':True,'originalScratchCleanupVerified':True,'precommittedNativeBlockAllocator':True,'nativeHeapGrowthQualified':False,
        'normalGroupingThreshold':.9990000128746033,'separationIsPenetrationVectorLength':True,'nativeLinkedRunPointOrderPreserved':True,
        'executedEntries':{hex(k):v for k,v in sorted(hits.items())},'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),'gameProcessAccessed':False,'completePhysics':False}
    (out/'recovered-patch-oracle.json').write_text(json.dumps(report,indent=2)+'\n');print(f'PASS ORIGINAL_CONTACT_PATCHES cases={count} points={total_points} patches={total_patches} defined_outputs_bit_exact=true')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_patch_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/patch-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
