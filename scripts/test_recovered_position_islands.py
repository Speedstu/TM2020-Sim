"""Original eight-pass position island loop, inside the SHA-pinned step.

This explicitly bounded loop starts at 0x8033b2 and stops at 0x80359a. The
surrounding physics step is not claimed. All called original routines execute.
"""
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
from unicorn.x86_const import UC_X86_REG_RBP,UC_X86_REG_RSP,UC_X86_REG_GS_BASE,UC_X86_REG_RIP


def run(exe,fixture,out,count):
    if not 1<=count<=100000:raise ValueError('Invalid position island case count')
    code=PeCode(exe);roots=[0x7f6110,0x7f61d0,0x7f63f0,0x7f6590,0x7f6a50,0x1955c0,0x8603b0,0x860980,0x85e4f0,0x85e7d0,0x192c70,0x1886d0,0x195c010,0x195d240]
    ranges=[(r.begin,r.end) for root in roots for r in code.index.groups[root]]+[(0x8033b2,0x80359a),(0x1175b0,0x117763)]
    e=PhysicsEmulator(exe,ranges);m=e.mu;m.mem_protect(e.base+0x1ebc000,0x1000,UC_PROT_READ|UC_PROT_WRITE)
    teb=0x300000000;m.mem_map(teb,0x4000);m.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));m.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000));m.reg_write(UC_X86_REG_GS_BASE,teb)
    header=e.memory+0x1000;states=e.memory;coeff=e.memory+0x500;rbp=e.stack+0xc000;rsp=e.stack+0xa000
    fields=[(0x100,40),(0x80,40),(0x110,60),(0x70,60),(0x90,36),(0,36),(0xf0,44),(0x60,40)]
    sequence=[0x7f6a50,0x7f6a50,0x7f6590,0x7f6590,0x7f63f0,0x7f63f0,0x8603b0,0x860980];watched=set(sequence);hits={};trace=[]
    def hit(_mu,address,_size,_data):
        rva=address-e.base;hits[rva]=hits.get(rva,0)+1
        if rva in watched:trace.append(rva)
    for root in roots+[0x8033b2,0x117690,0x1175b0,0x1176a0]:m.hook_add(UC_HOOK_CODE,hit,begin=e.base+root,end=e.base+root)
    rng=random.Random(2026102323);inputs=[];expected=bytearray();active={};total_iterations=0
    def f(v):return struct.pack('<'+'f'*len(v),*v)
    def vector(scale=1):return [rng.uniform(-scale,scale) for _ in range(3)]
    def quaternion():
        q=[rng.uniform(-1,1) for _ in range(4)];norm=math.sqrt(sum(x*x for x in q));return [x/norm for x in q]
    def direction():
        v=vector();norm=math.sqrt(sum(x*x for x in v));return [x/norm for x in v]
    for n in range(count):
        initial=bytearray()
        for _ in range(3):initial+=f([1,0,0,0,1,0,0,0,1]+vector(.2)+quaternion()+vector()+vector())
        coefficients=f([rng.uniform(.03,.15) for _ in range(12)]);parameters=f([rng.uniform(-.001,.001),rng.uniform(.001,.005),rng.uniform(.001,.01)])
        iterations=(n//4)%5;number=n%4;row=bytearray(initial+coefficients+parameters+struct.pack('<2I',iterations,number))
        m.mem_write(states,bytes(initial));m.mem_write(coeff,coefficients);m.mem_write(header,struct.pack('<2I',number,0)+bytes(0x140*3));buffers=[]
        for island in range(number):
            for field,(offset,stride) in enumerate(fields):
                amount=0 if n%13==0 else (n+island+field)%3;records=[]
                for j in range(amount):
                    a=j%3;b=a if n%19==0 else (j+1)%3
                    if field<2:
                        records.append(struct.pack('<2I',0xffffffff if n%31==0 else a,0)+f(direction())+bytes(4)+f(quaternion()))
                    elif field<4:
                        records.append(struct.pack('<2I',a,0xffffffff if field==3 else b)+f(vector(.2)+vector(.2)+[rng.uniform(-.05,.05)]+vector(.2)+direction()))
                    elif field<6:
                        records.append(struct.pack('<2I',a,0xffffffff if field==5 else b)+f([rng.uniform(0,.3)]+vector(.2)+direction()))
                    elif field==6:records.append(struct.pack('<2I',a,b)+f(vector(.2)+vector(.2)+direction()))
                    else:records.append(struct.pack('<I',a)+f(vector(.2)+vector(.2)+direction()))
                raw=b''.join(records);address=e.memory+0x4000+island*0x3000+field*0x400
                if len(raw)!=amount*stride:raise AssertionError('Position island native record stride changed')
                row+=struct.pack('<I',amount)+raw;m.mem_write(address,raw or bytes(4));m.mem_write(header+8+island*0x140+offset,struct.pack('<Q2I',address,amount,0));buffers.append((address,raw));active[offset]=active.get(offset,0)+int(bool(amount and iterations))
        m.mem_write(rbp+0x40,struct.pack('<Q',header));m.mem_write(rbp+0x408,struct.pack('<2Q',states,coeff));m.mem_write(rbp-0x40,bytes(8));m.mem_write(e.base+0x1ebcd1c,struct.pack('<I',iterations));m.mem_write(e.base+0x1ebcd50,parameters)
        e.reset_stack();m.reg_write(UC_X86_REG_RBP,rbp);m.reg_write(UC_X86_REG_RSP,rsp);trace.clear()
        try:finished=e.run(0x8033b2,stop=0x80359a,budget=1000000)
        except Exception as error:raise RuntimeError(f'Original position loop case={n} RIP={m.reg_read(UC_X86_REG_RIP)-e.base:#x}: {error}') from error
        if finished!=e.base+0x80359a:raise RuntimeError('Original bounded position loop exceeded instruction budget')
        if trace!=sequence*(number*iterations):raise AssertionError('Original position pass order changed')
        for address,raw in buffers:
            if bytes(m.mem_read(address,len(raw)))!=raw:raise AssertionError('Original position routine modified prepared constraints')
        expected+=m.mem_read(states,264);inputs.append(row);total_iterations+=iterations
        if n and n%1000==0:print('ORIGINAL_POSITION_ISLAND_PROGRESS',n,flush=True)
    out.mkdir(parents=True,exist_ok=True);inp=out/'position-island-input.bin';result=out/'position-island-ported.bin';inp.write_bytes(struct.pack('<I',count)+b''.join(inputs));subprocess.run([str(fixture),str(inp),str(result)],check=True)
    actual=result.read_bytes()
    if actual!=expected:
        offset=next((j for j,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)));raise AssertionError(f'Position island mismatch case={offset//264} byte={offset%264} expected_bytes={len(expected)} actual_bytes={len(actual)}')
    if count>=1000 and not set(roots).issubset(hits):raise AssertionError('Position island helper coverage incomplete')
    report={'schema':'tm2020_position_island_oracle_v1','sha256':SHA,'cases':count,'operations':1,'bitExact':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4','boundedInstructionSlice':True,
        'startRva':'0x8033b2','stopRva':'0x80359a','completeOuterPhysicsStepQualified':False,
        'allEightPassesQualified':True,'schedulingTraceVerifiedEveryCase':True,'preparedConstraintsUnmodified':True,
        'iterationCountsTested':[0,1,2,3,4],'islandCountsTested':[0,1,2,3],'totalIterations':total_iterations,
        'nativePositionSpanOffsets':{hex(offset):active.get(offset,0) for offset,_ in fields},
        'scalarTrigDispatchFlag':0,'maximumContactAngularCorrection':1.57079625,
        'executedEntries':{hex(k):v for k,v in sorted(hits.items())},'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),'gameProcessAccessed':False,'completePhysics':False}
    (out/'recovered-position-island-oracle.json').write_text(json.dumps(report,indent=2)+'\n');print(f'PASS ORIGINAL_POSITION_ISLANDS cases={count} all_eight_passes=true bit_exact=true bounded_loop=true')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_position_island_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/position-island-oracle');p.add_argument('--cases',type=int,default=20000)
    a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases)
