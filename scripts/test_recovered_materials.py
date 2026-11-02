"""Execute original material initialization and complete response routines."""
import argparse
import hashlib
import json
import random
import struct
import subprocess
from pathlib import Path
from physics_emulator import PhysicsEmulator,ROOT,SHA
from unicorn import UC_HOOK_CODE,UC_PROT_READ,UC_PROT_WRITE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_RAX,UC_X86_REG_XMM0,UC_X86_REG_GS_BASE


def run(exe,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid material case count')
    e=PhysicsEmulator(exe,[(0x4df599,0x4dfbb8),(0x4eff20,0x4eff4a),(0x7bf0d0,0x7bf299),(0x7d7cb0,0x7d7d15)])
    mu=e.mu
    for page in [0x1fa9000,0x1e70000,0x20cb000]:mu.mem_protect(e.base+page,0x1000,UC_PROT_READ|UC_PROT_WRITE)
    e.reset_stack()
    if e.run(0x4df599,stop=0x4dfbb8,budget=1000)!=e.base+0x4dfbb8:raise RuntimeError('Material initializer slice did not finish')
    defaults=bytes(mu.mem_read(e.base+0x1fa9a70,640))
    teb=0x300000000;mu.mem_map(teb,0x4000);mu.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));mu.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000))
    mu.mem_write(teb+0x2014,struct.pack('<i',0x7fffffff));mu.reg_write(UC_X86_REG_GS_BASE,teb)
    base=e.memory;shape_a=base+0x1000;data_a=base+0x2000;vehicle_a=base+0x3000;config_a=base+0x4000
    shape_b=base+0x8000;data_b=base+0x9000;vehicle_b=base+0xa000;config_b=base+0xb000
    for shape,data,vehicle,config in [(shape_a,data_a,vehicle_a,config_a),(shape_b,data_b,vehicle_b,config_b)]:
        mu.mem_write(shape+0x38,struct.pack('<Q',data));mu.mem_write(data+8,struct.pack('<Q',vehicle));mu.mem_write(vehicle+0x88,struct.pack('<Q',config))
    hits={}
    def hit(_mu,address,_size,_data):hits[address-e.base]=hits.get(address-e.base,0)+1
    branches=[0x7bf1cd,0x7bf20e,0x7bf21d,0x7bf237,0x7bf245,0x7bf258,0x7bf262]
    for rva in branches:mu.hook_add(UC_HOOK_CODE,hit,begin=e.base+rva,end=e.base+rva)
    rng=random.Random(2026102312);inputs=[];expected=bytearray()
    for n in range(count):
        a,b=rng.uniform(-2,2),rng.uniform(-2,2)
        if n%7==0:a,b=[(0.,0.),(-0.,0.),(0.,-0.),(-0.,-0.),(0.,.5),(-.5,0.),(.5,-0.)][(n//7)%7]
        runtime=0x30abc000
        classes=[0x0a020000,runtime,0x0a0aa000,0x0a030000]
        ca,cb=classes[(n//4)%4],classes[n%4];va,vb=[5,9,13][(n//16)%3],[5,9,13][(n//48)%3]
        ma,mb=rng.randrange(80)|(rng.randrange(256)<<8),rng.randrange(80)|(rng.randrange(256)<<8)
        ka,kb,parameters=(n//144)%2,(n//288)%2,[rng.uniform(0,1) for _ in range(5)]
        row=struct.pack('<2f9I5f',a,b,ca,cb,runtime,va,vb,ma,mb,ka,kb,*parameters);inputs.append(row)
        # Re-read binary32 fixture values, not Python binary64 samples.
        values=struct.unpack('<2f9I5f',row);a,b=values[:2];parameters=values[11:]
        mu.mem_write(base+0x100,struct.pack('<2f',0,a));mu.mem_write(base+0x108,struct.pack('<2f',0,b));e.reset_stack()
        mu.reg_write(UC_X86_REG_RCX,base+0x100);mu.reg_write(UC_X86_REG_RDX,base+0x108)
        if e.run(0x4eff20,budget=100)!=e.sentinel:raise RuntimeError('Restitution combine did not return')
        expected+=struct.pack('<I',mu.reg_read(UC_X86_REG_XMM0)&0xffffffff)
        mu.mem_write(e.base+0x20cba88,struct.pack('<II',0,runtime))
        mu.mem_write(e.base+0x1e70e10,struct.pack('<5f',*parameters))
        for data,config,klass,variant,category in [(data_a,config_a,ca,va,ka),(data_b,config_b,cb,vb,kb)]:
            mu.mem_write(data,struct.pack('<I',klass));mu.mem_write(data+0x10,bytes([category]));mu.mem_write(config+0x1790,struct.pack('<I',variant))
        mu.mem_write(base,struct.pack('<2Q',shape_a,shape_b));mu.mem_write(base+0x50,struct.pack('<2H',ma,mb));e.reset_stack();mu.reg_write(UC_X86_REG_RCX,base)
        if e.run(0x7bf0d0,budget=1000)!=e.sentinel:raise RuntimeError('Complete material response did not return')
        expected+=struct.pack('<Q',mu.reg_read(UC_X86_REG_RAX))
    if count>=1000 and not set(branches).issubset(hits):raise AssertionError('A material response branch was not covered')
    out.mkdir(parents=True,exist_ok=True);inp=out/'material-input.bin';result=out/'material-ported.bin';table=out/'material-defaults-ported.bin'
    inp.write_bytes(struct.pack('<I',count)+b''.join(inputs));subprocess.run([str(fixture),str(inp),str(result),str(table)],check=True)
    if table.read_bytes()!=defaults:raise AssertionError('Material constructor differs from original 80-entry table')
    actual=result.read_bytes()
    if actual!=expected:
        if len(actual)!=len(expected):raise AssertionError('Material output size differs')
        at=next(i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b)
        raise AssertionError(f'Material output differs case={at//12} byte={at%12}')
    report={'schema':'tm2020_material_oracle_v1','sha256':SHA,'cases':count,'operations':2,'bitExact':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4',
        'initializerStartRva':'0x4df599','initializerStopRva':'0x4dfbb8','defaultMaterialEntries':80,'defaultTableBitExact':True,
        'effectiveRaceMaterialsVerified':False,'runtimeClassIdSuppliedExplicitly':True,'staticInitializationAlreadyComplete':True,
        'executedResponseBranches':{hex(k):v for k,v in sorted(hits.items())},
        'defaultTableSha256':hashlib.sha256(defaults).hexdigest(),'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),
        'constructorValues':[{'id':i,'impactFriction':struct.unpack_from('<f',defaults,8*i)[0],'restitution':struct.unpack_from('<f',defaults,8*i+4)[0]} for i in range(80)],
        'gameProcessAccessed':False,'completeTirePhysics':False,'completePhysics':False}
    (out/'recovered-material-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS ORIGINAL_MATERIAL_RESPONSE cases_each={count} defaults=80 bit_exact=true full_tire_physics=false')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_material_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/material-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
