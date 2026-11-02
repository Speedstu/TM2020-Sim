"""Execute the entire original island scheduler with joint/callback spans empty.

All original calls execute, including the ordinary empty joint helper paths;
no instruction replacement, hook-based returns or patched code is used.
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
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_R9,UC_X86_REG_GS_BASE


def run(executable,fixture,out,count,joints=False):
    if not 1<=count<=100000:raise ValueError('Invalid solver case count')
    e=PhysicsEmulator(executable,[(0x7f6ec0,0x7f730a),(0x1d5970,0x1d5a50),(0x1175b0,0x117763),
        (0x7f5090,0x7f6041),(0x7f67a0,0x7f6a46),(0x85eab0,0x85ecc2),(0x85fc50,0x8603ab)])
    m=e.mu;teb=0x300000000;m.mem_map(teb,0x4000)
    m.mem_write(teb+0x58,struct.pack('<Q',teb+0x1000));m.mem_write(teb+0x1000,struct.pack('<Q',teb+0x2000));m.reg_write(UC_X86_REG_GS_BASE,teb)
    states=e.memory;coeff=states+0x1000;config=states+0x1100;external=states+0x1200;island_span=states+0x1300;island_data=states+0x1400
    fields=[(0x10,40),(0x20,40),(0x40,64),(0x50,56),(0xa0,44),(0xb0,44),(0xd0,88),(0xe0,96)]
    if joints:fields.extend([(0x30,60),(0xc0,60),(0x120,60),(0x130,36)])
    traced={0x7f5860,0x7f5cb0,0x85ff00,0x8601a0,0x85ffd0,0x85fc50}
    if joints:traced.update({0x7f56d0,0x7f5f40,0x7f67a0})
    entries={};trace=[];wanted_trace=[]
    def hit(_mu,address,_size,_data):
        rva=address-e.base;entries[rva]=entries.get(rva,0)+1
        if rva in traced:trace.append(rva)
    for root in [0x7f6ec0,0x1d5970,0x117690,0x1175b0,0x1176a0,0x7f56d0,0x7f5f40,0x7f67a0,0x7f5860,0x7f5cb0,0x85ff00,0x8601a0,0x85ffd0,0x85fc50]:
        m.hook_add(UC_HOOK_CODE,hit,begin=e.base+root,end=e.base+root)
    rng=random.Random(2026102316);inputs=[];expected=bytearray();active={};total_iterations=0
    def f(v):return struct.pack('<'+'f'*len(v),*v)
    def v(scale=1):return [rng.uniform(-scale,scale) for _ in range(3)]
    def jacobian(dynamic,j,n):
        direction=v();angular=v(.1);weighted=v(.02);target=rng.uniform(-1,1);impulse=rng.uniform(0,1)
        a=j%3;b=a if n%19==0 else (a+1)%3
        if dynamic:return struct.pack('<2I',a,b)+f(direction+angular+v(.1)+weighted+v(.02)+[.1,.1,.08,target,impulse])
        return struct.pack('<I',a)+f(direction+angular+weighted+[.1,.08,target,impulse])
    for n in range(count):
        initial=b''.join(f([1,0,0,0,1,0,0,0,1]+v(2)+[1,0,0,0]+v(3)+v()) for _ in range(3))
        coefficients=f([rng.uniform(.01,.15) for _ in range(12)]);sf,df,it=[rng.randrange(10),rng.randrange(10),rng.randrange(8)];number=n%4
        row=bytearray(initial+coefficients+struct.pack('<4I',sf,df,it,number));m.mem_write(states,initial);m.mem_write(coeff,coefficients);m.mem_write(config,struct.pack('<3I',sf,df,it));m.mem_write(external,bytes(16));m.mem_write(island_data,bytes(0x140*3));m.mem_write(island_span,struct.pack('<Q2I',island_data,number,0))
        buffers=[]
        for island in range(number):
            arrays=[];amount=0 if n%11==0 else 1+(n+island)%3
            sn=[jacobian(False,j,n) for j in range(amount)];dn=[jacobian(True,j,n) for j in range(amount)]
            for field,(offset,stride) in enumerate(fields):
                records=[]
                for j in range(amount):
                    if field in {0,1,4,5}:
                        ids=[j%3] if field<2 else [j%3,j%3 if n%19==0 else (j+1)%3]
                        records.append(struct.pack('<'+'I'*len(ids),*ids)+f(v(2)+v()+[rng.uniform(-1,1),.05,rng.uniform(0,1)]))
                    elif field==2:records.append(sn[j]+struct.pack('<If',j,rng.uniform(0,1)))
                    elif field==3:records.append(sn[j])
                    elif field==6:records.append(dn[j])
                    elif field==7:records.append(dn[j]+struct.pack('<If',j,rng.uniform(0,1)))
                    elif field in {8,9}:
                        a=j%3;b=0xffffffff if (n+island)%7==0 else (j+1)%3
                        records.append(struct.pack('<2I',a,b)+f(v(2)+v(2)+v()+[rng.uniform(-1,1),0 if n%3==0 else .1,.05,rng.uniform(-1,1)]))
                    elif field==10:
                        a=j%3;b=(j+1)%3;axes=[1,0,0,0,1,0] if n%3==0 else v()+v()
                        records.append(struct.pack('<2I',a,b)+f(axes+[rng.uniform(.1,1) for _ in range(6)]+[rng.uniform(.1,2)]))
                    else:
                        a=0xffffffff if n%5==0 else j%3;b=0xffffffff if n%7==0 else (j+1)%3
                        records.append(struct.pack('<2I',a,b)+f(v()+[rng.uniform(-1,1),.1,.05,rng.uniform(-1,1)]))
                raw=b''.join(records);address=states+0x3000+island*0x3000+field*0x400
                if len(raw)!=amount*stride:raise AssertionError('Constraint fixture stride changed')
                row+=struct.pack('<I',amount)+raw;m.mem_write(address,raw or bytes(4));m.mem_write(island_data+island*0x140+offset,struct.pack('<Q2I',address,amount,0));buffers.append((address,len(raw)))
                active[offset]=active.get(offset,0)+int(bool(amount and it))
        trace.clear();wanted_trace.clear()
        for iteration in range(it):
            if iteration<df:wanted_trace.extend([0x7f5860,0x85ff00]*number)
            if iteration<sf:wanted_trace.extend([0x7f5cb0,0x8601a0]*number)
            if joints:
                wanted_trace.extend([0x7f67a0]*number);wanted_trace.extend([0x7f5f40]*number);wanted_trace.extend([0x7f56d0]*number);wanted_trace.extend([0x7f56d0,0x85ffd0]*number)
            else:wanted_trace.extend([0x85ffd0]*number)
            wanted_trace.extend([0x7f5860,0x85fc50]*number);wanted_trace.extend([0x7f5cb0]*number)
        e.reset_stack();m.mem_write(e.rsp+0x28,struct.pack('<Q',island_span))
        for reg,value in [(UC_X86_REG_RCX,states),(UC_X86_REG_RDX,coeff),(UC_X86_REG_R8,config),(UC_X86_REG_R9,external)]:m.reg_write(reg,value)
        if e.run(0x7f6ec0,budget=200000)!=e.sentinel:raise RuntimeError('Whole native constraint scheduler exceeded budget')
        if trace!=wanted_trace:raise AssertionError(f'Unexpected native contact scheduling case={n}')
        expected+=m.mem_read(states,264)
        for address,size in buffers:expected+=m.mem_read(address,size)
        inputs.append(row);total_iterations+=it
        if n and n%1000==0:print('ORIGINAL_SOLVER_PROGRESS',n,flush=True)
    out.mkdir(parents=True,exist_ok=True);inp=out/'solver-input.bin';result=out/'solver-ported.bin';inp.write_bytes(struct.pack('<I',count)+b''.join(inputs));subprocess.run([str(fixture),str(inp),str(result)]+(['--joints'] if joints else []),check=True)
    actual=result.read_bytes()
    if actual!=expected:
        offset=next((i for i,(a,b) in enumerate(zip(expected,actual)) if a!=b),min(len(expected),len(actual)))
        raise AssertionError(f'Contact scheduler mismatch output byte={offset}, expected bytes={len(expected)}, actual bytes={len(actual)}')
    report={'schema':'tm2020_contact_island_oracle_v1','sha256':SHA,'cases':count,'operations':1,'bitExact':True,
        'originalCodeModified':False,'functionsSkipped':False,'emulator':'Unicorn 2.1.4','entryRva':'0x7f6ec0',
        'schedulingTraceVerifiedEveryCase':True,'totalVelocityIterations':total_iterations,'islandCounts':[0,1,2,3],
        'jointSpansEmpty':not joints,'externalCallbackSpansEmpty':True,'generalJointVelocitySweepsQualified':joints,'maximumVelocityIterationsTested':7,
        'runtimeMaximumVelocityIterations':128,'syntheticTlsProfilerDisabled':True,'executedEntries':{hex(k):v for k,v in sorted(entries.items())},
        'activeNativeContactSpans':{hex(k):v for k,v in sorted(active.items())},'expectedOutputSha256':hashlib.sha256(expected).hexdigest(),
        'gameProcessAccessed':False,'completePhysics':False}
    (out/'recovered-solver-oracle.json').write_text(json.dumps(report,indent=2)+'\n');print(f'PASS ORIGINAL_ISLAND_SCHEDULER cases={count} bit_exact=true original_call_order=true general_joint_velocity_sweeps={joints}')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    p.add_argument('--fixture',type=Path,default=ROOT/'native/build/tm2020_solver_fixture.exe');p.add_argument('--out',type=Path,default=ROOT/'local/recon/solver-oracle');p.add_argument('--cases',type=int,default=20000)
    p.add_argument('--joints',action='store_true');a=p.parse_args();run(a.exe,a.fixture,a.out,a.cases,a.joints)
