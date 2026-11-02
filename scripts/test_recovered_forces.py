"""Compare C++ force integration with the unmodified original x64 procedure.

Unicorn emulates the pinned code, including original profiling functions with
a synthetic TLS slot containing a null profiler. No function is patched/skipped.
No game startup, imports, OS calls, game process or game memory writes occur.
https://www.unicorn-engine.org/docs/tutorial.html
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/physics-python'))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_64,UC_PROT_READ,UC_PROT_EXEC,UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_RSP,UC_X86_REG_RIP,UC_X86_REG_RCX,UC_X86_REG_RDX,
    UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_GS_BASE,UC_X86_REG_MXCSR)
import pefile
import unicorn
from reverse_physics import SHA

WIRE=struct.Struct('<32fI3fI3fI3f')
assert WIRE.size==176


def run(executable,fixture,out,count=4096):
    if unicorn.__version__!='2.1.4':raise ValueError('Requalify a different Unicorn version before use')
    if count<4 or count>100000 or count%4:raise ValueError('Cases must be a multiple of four in 4..100000')
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown executable')
    pe=pefile.PE(str(executable),fast_load=True);base=pe.OPTIONAL_HEADER.ImageBase
    mu=Uc(UC_ARCH_X86,UC_MODE_64);size=(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095
    mu.mem_map(base,size)
    for section in pe.sections:mu.mem_write(base+section.VirtualAddress,section.get_data())
    # Read-only image; execution is enabled only for the reviewed procedures.
    mu.mem_protect(base,size,UC_PROT_READ)
    for start,end in [(0x7f89d0,0x7f8ce6),(0x7f5130,0x7f513b),(0x1175b0,0x1176ee)]:
        page=start&~4095;mu.mem_protect(base+page,((end+4095)&~4095)-page,UC_PROT_READ|UC_PROT_EXEC)
    memory=0x200000000;mu.mem_map(memory,0x10000)
    teb=0x300000000;mu.mem_map(teb,0x4000)
    mu.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000))
    mu.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000))
    # [first TLS block+0x1b8] remains null: original profiler's disabled branch.
    stack=0x400000000;mu.mem_map(stack,0x10000);rsp=stack+0x10000-0x108
    sentinel=0x500000000;mu.mem_map(sentinel,0x1000)
    coefficients=memory;dynamic=memory+0x1000;states=memory+0x2000
    sleeps=memory+0x3000;forces=memory+0x4000;models=memory+0x5000
    model_objects=memory+0x6000;gravity=memory+0x7000
    entries=set()
    def entry(_uc,address,_size,_data):entries.add(address-base)
    for entry_rva in (0x7f89d0,0x7f5130,0x117690,0x1175b0,0x1176a0,0x7f8b16,0x7f8b45,0x7f8c3f,0x7f8b94):
        mu.hook_add(UC_HOOK_CODE,entry,begin=base+entry_rva,end=base+entry_rva)
    rng=random.Random(20261021);cases=[];expected=bytearray()
    for first in range(0,count,4):
        attenuate=(first//4)%2;threshold=[.01,0,1.,.2][(first//8)%4];multiplier=[.9,1.,0.,.5][(first//16)%4]
        dt=[.01,.001,0.,1.][(first//4)%4];g=[rng.uniform(-20,20) for _ in range(3)]
        for j in range(4):
            n=first+j
            state=[1,0,0,0,1,0,0,0,1]+[rng.uniform(-2000,2000) for _ in range(3)]+[1,0,0,0]
            state += [rng.uniform(-1,1)*(0.001 if n%3 else 200) for _ in range(6)]
            if n%29==0:state[16:22]=[threshold,0,0,0,threshold,0]
            if n%31==0:state[16:22]=[0.,-0.,0.,-0.,0.,0.]
            accum=[rng.uniform(-10000,10000) for _ in range(6)]
            coeff=[rng.uniform(0,.1) for _ in range(4)]
            flags=2 if n%11==0 else 0;sleeping=n%7==0
            m,offset,scale=rng.uniform(0,2000),rng.uniform(-100,100),rng.uniform(0,2)
            # Round all fixture values once to binary32 before emulation.
            wire=WIRE.pack(*state,*accum,*coeff,flags,m,offset,scale,sleeping,*g,attenuate,threshold,multiplier,dt)
            values=WIRE.unpack(wire);cases.append(wire)
            mu.mem_write(coefficients+j*16,wire[112:128])
            item=bytearray(56);struct.pack_into('<I2f',item,4,flags,values[34],values[35])
            mu.mem_write(dynamic+j*56,bytes(item))
            mu.mem_write(states+j*88,wire[:88]);mu.mem_write(forces+j*24,wire[88:112])
            sleep=bytearray(8);struct.pack_into('<H',sleep,4,0xffff if sleeping else 0)
            mu.mem_write(sleeps+j*8,bytes(sleep))
            model=bytearray(80);struct.pack_into('<f',model,24,values[33])
            mu.mem_write(model_objects+j*80,bytes(model));mu.mem_write(models+j*8,struct.pack('<Q',model_objects+j*80))
        # Values: 0..21 state,22..27 accum,28..31 coeff,32 flags,
        # 33 model,34 offset,35 scale,36 sleeping,37..39 gravity,40 flag,
        # 41 threshold,42 attenuation,43 dt.
        mu.mem_write(gravity,struct.pack('<3f',*g))
        for rva,data in [(0x1ebccfc,struct.pack('<I',attenuate)),(0x1ebcd04,struct.pack('<f',threshold)),(0x1ebcd00,struct.pack('<f',multiplier))]:
            mu.mem_write(base+rva,data)
        mu.mem_write(rsp,struct.pack('<Q',sentinel))
        mu.mem_write(rsp+0x28,struct.pack('<4Qf',sleeps,forces,models,gravity,dt))
        for reg,value in [(UC_X86_REG_RSP,rsp),(UC_X86_REG_RCX,4),(UC_X86_REG_RDX,coefficients),
            (UC_X86_REG_R8,dynamic),(UC_X86_REG_R9,states),(UC_X86_REG_GS_BASE,teb),(UC_X86_REG_MXCSR,0x1f80)]:mu.reg_write(reg,value)
        mu.emu_start(base+0x7f89d0,sentinel,count=10000)
        if mu.reg_read(UC_X86_REG_RIP)!=sentinel:raise RuntimeError('Original procedure exceeded instruction budget')
        for j in range(4):expected+=mu.mem_read(states+j*88,88)+mu.mem_read(forces+j*24,24)
    out.mkdir(parents=True,exist_ok=True)
    inputs=out/'force-oracle-input.bin';outputs=out/'force-oracle-ported.bin'
    inputs.write_bytes(struct.pack('<I',count)+b''.join(cases))
    subprocess.run([str(fixture),str(inputs),str(outputs)],check=True)
    actual=outputs.read_bytes()
    if actual!=expected:
        i=next(i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b)
        raise AssertionError(f'Original force procedure mismatch case={i//112} byte={i%112} expected={expected[i]} actual={actual[i]}')
    required={0x7f89d0,0x7f5130,0x117690,0x1175b0,0x1176a0,0x7f8b16,0x7f8b45,0x7f8c3f,0x7f8b94}
    if not required.issubset(entries):raise AssertionError('Profiler/helper execution coverage missing')
    report={'schema':'tm2020_force_kernel_emulation_v1','sha256':SHA,'procedureRva':'0x7f89d0',
        'cases':count,'batchSize':4,'bitExact':True,'emulator':'Unicorn 2.1.4',
        'originalCodeModified':False,'functionsSkipped':False,'syntheticTlsProfilerDisabled':True,
        'executedEntries':[hex(x) for x in sorted(entries)],'gameProcessAccessed':False,
        'branches':['active','skipped flag bit 1','sleep id 0xffff','small velocity attenuation enabled/disabled'],
        'configuration':'explicit synthetic gravity, coefficients, flags, attenuation threshold and multiplier',
        'fullVehiclePhysics':False,'expectedOutputSha256':hashlib.sha256(expected).hexdigest()}
    (out/'recovered-force-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS ORIGINAL_FORCE_EMULATION cases={count} bit_exact=true unmodified_code=true full_vehicle_physics=false')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    ap.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_force_fixture.exe')
    ap.add_argument('--out',type=Path,default=ROOT/'local/recon/force-oracle')
    ap.add_argument('--cases',type=int,default=4096);args=ap.parse_args()
    run(args.exe,args.fixture,args.out,args.cases)
