"""Original-code oracles for pose subdivision selection and mode-2 suspension.

Substeps: two original instruction slices, no copied/patched instructions.
Suspension: original function gates and force computation; stop before its
force-application call. This does NOT qualify that call or the entire scheduler.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
from physics_emulator import PhysicsEmulator
from reverse_physics import ROOT,SHA
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_RBP,UC_X86_REG_RBX,UC_X86_REG_RCX,UC_X86_REG_RDX,
    UC_X86_REG_RDI,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_R13,UC_X86_REG_R15,
    UC_X86_REG_XMM6,UC_X86_REG_XMM7,UC_X86_REG_XMM8,UC_X86_REG_XMM9,UC_X86_REG_XMM10,UC_X86_REG_RSP)
WIRE=struct.Struct('<5f3I11f4I')
assert WIRE.size==92


def run(exe,fixture,out,cases=20000):
    if not 1<=cases<=100000:raise ValueError('Invalid case limit')
    emulator=PhysicsEmulator(exe,[(0x803114,0x8031ac),(0x803274,0x803309),(0x844090,0x84412b)])
    mu=emulator.mu;m=emulator.memory;state=m;frame=m+0xe000;scalar=m+0x2000
    vehicle=m+0x3000;tuning=m+0x6000;model_ref=m+0x8000;model=m+0x9000
    call=emulator.base+0x844121
    def stop_before_call(uc,_address,_size,_data):uc.emu_stop()
    mu.hook_add(UC_HOOK_CODE,stop_before_call,begin=call,end=call)
    rng=random.Random(20261023);inputs=[];expected=bytearray();active_count=0;categories={'full':0,'minimum':0,'interior':0}
    def xmm(reg,value):mu.reg_write(reg,struct.unpack('<I',struct.pack('<f',value))[0])
    for n in range(cases):
        velocity=[rng.uniform(-200,200) for _ in range(3)];limit=10**rng.uniform(-4,1);dt=[.01,.001,.1,0,1][n%5]
        if n%17==0:velocity=[0,0,0]
        if n%19==0:limit=0
        stiffness=rng.uniform(0,2500);damping=rng.uniform(0,200);rest=rng.uniform(.1,1)
        lengths=[rng.uniform(0,1) for _ in range(4)];speeds=[rng.uniform(-10,10) for _ in range(4)]
        contacts=[int(rng.random()>.2) for _ in range(4)]
        wire=WIRE.pack(*velocity,limit,dt,n%4,n%2,n%4,stiffness,damping,rest,*lengths,*speeds,*contacts)
        values=WIRE.unpack(wire);inputs.append(wire);dt=values[4]
        mu.mem_write(state+0x40,wire[:12]);mu.mem_write(scalar,wire[12:16]);emulator.reset_stack()
        for reg,value in [(UC_X86_REG_RBX,state),(UC_X86_REG_RBP,frame),(UC_X86_REG_RCX,scalar),(UC_X86_REG_RDI,scalar),(UC_X86_REG_R13,0),(UC_X86_REG_R15,0)]:mu.reg_write(reg,value)
        xmm(UC_X86_REG_XMM8,.1);xmm(UC_X86_REG_XMM10,1);xmm(UC_X86_REG_XMM9,dt)
        if emulator.run(0x803114,0x8031ac)!=emulator.base+0x8031ac:raise RuntimeError('First substep slice escaped')
        fraction=struct.pack('<I',mu.reg_read(UC_X86_REG_XMM7)&0xffffffff)
        xmm(UC_X86_REG_XMM6,dt)
        if emulator.run(0x803274,0x803309)!=emulator.base+0x803309:raise RuntimeError('Remainder slice escaped')
        second=struct.pack('<I',mu.reg_read(UC_X86_REG_XMM7)&0xffffffff)
        if fraction!=second:raise AssertionError('First/remainder selectors disagree')
        selected_dt=struct.unpack('<f',fraction)[0]
        minimum=struct.unpack('<f',struct.pack('<f',struct.unpack('<f',struct.pack('<f',.1))[0]*dt))[0]
        categories['full' if selected_dt==dt else ('minimum' if selected_dt==minimum else 'interior')]+=1
        # Run original suspension control flow; active cases stop at its call.
        mode,all_contacts,selected=values[5:8]
        mu.mem_write(vehicle+0x88,struct.pack('<Q',tuning));mu.mem_write(vehicle+0x171c,struct.pack('<I',all_contacts))
        mu.mem_write(tuning+0x238,struct.pack('<I3f',mode,*values[8:11]))
        for k in range(4):
            wheel=vehicle+0x1780+k*0xb8
            mu.mem_write(wheel,struct.pack('<2f',values[11+k],values[15+k]));mu.mem_write(wheel+0x34,struct.pack('<I',contacts[k]))
        mu.mem_write(model_ref,struct.pack('<Q',model));emulator.reset_stack()
        for reg,value in [(UC_X86_REG_RCX,m+0xa000),(UC_X86_REG_RDX,vehicle),(UC_X86_REG_R8,model_ref),(UC_X86_REG_R9,vehicle+0x1780+selected*0xb8)]:mu.reg_write(reg,value)
        end=emulator.run(0x844090)
        if end not in (emulator.sentinel,call):raise RuntimeError('Suspension escaped instruction budget')
        active=int(end==call);active_count+=active
        force=mu.mem_read(mu.reg_read(UC_X86_REG_RSP)+0x34,4) if active else struct.pack('<f',123.)
        expected+=fraction+struct.pack('<I',active)+force
    out.mkdir(parents=True,exist_ok=True);source=out/'selection-input.bin';target=out/'selection-ported.bin'
    source.write_bytes(struct.pack('<I',cases)+b''.join(inputs));subprocess.run([str(fixture),str(source),str(target)],check=True)
    actual=target.read_bytes()
    if actual!=expected:
        i=next(i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b)
        raise AssertionError(f'Selection/suspension mismatch case={i//12} byte={i%12} expected={expected[i]} actual={actual[i]}')
    if not 0<active_count<cases or not all(categories.values()):raise AssertionError('Branch coverage missing')
    report={'schema':'tm2020_selection_suspension_oracle_v1','sha256':SHA,'cases':cases,'bitExact':True,
        'substepSlices':['0x803114..0x8031ac','0x803274..0x803309'],'substepCategories':categories,
        'suspensionProcedure':'0x844090','suspensionStopBeforeCall':'0x844121','activeSuspensionCases':active_count,
        'originalCodeModified':False,'fullForceApplicationExecuted':False,'completeSchedulerRecovered':False,
        'originalGateBranchesExecuted':True,'gameProcessAccessed':False,'completeVehiclePhysics':False,
        'expectedOutputSha256':hashlib.sha256(expected).hexdigest()}
    (out/'selection-suspension-oracle.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS SELECTION_SUSPENSION_ORACLE',cases,'bit_exact=true active',active_count,'substep_categories',categories)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    ap.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_selection_fixture.exe')
    ap.add_argument('--out',type=Path,default=ROOT/'local/recon/selection-oracle');ap.add_argument('--cases',type=int,default=20000)
    a=ap.parse_args();run(a.exe,a.fixture,a.out,a.cases)
