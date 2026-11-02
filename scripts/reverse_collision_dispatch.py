"""Recover the 20x20 collision table by executing its original initializer.

The table lives in zero-filled data, not in the disk's function pointer data.
Execute the constructor prefix and its registration helpers in synthetic memory,
stop before its unrelated tail call, then independently reconstruct all writes.
No game process, startup, imports, original-code patches, or OS calls.
"""
import hashlib
import json
import struct
from pathlib import Path
from physics_emulator import PhysicsEmulator,ROOT,SHA
from pe_unwind import PeCode
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE,UC_PROT_READ,UC_PROT_WRITE
from unicorn.x86_const import UC_X86_REG_RCX,UC_X86_REG_RDX,UC_X86_REG_R8,UC_X86_REG_RSP


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    e=PhysicsEmulator(exe,[(0x197d00,0x1985d0)]);code=PeCode(exe)
    table=0x1f9d230;names_table=0x1e6f0e0;data_begin=0x1f9d000;data_size=0x3000
    e.mu.mem_protect(e.base+data_begin,data_size,UC_PROT_READ|UC_PROT_WRITE)
    names=[]
    for index in range(20):
        pointer=struct.unpack('<Q',code.pe.get_data(names_table+index*8,8))[0]
        name=code.pe.get_string_at_rva(pointer-e.base).decode('ascii')
        if not name or len(name)>50:raise ValueError('Invalid shape name')
        names.append(name)
    if names[0]!='Sphere' or names[7]!='Mesh':raise ValueError('Unexpected type mapping')
    registrations=[];write_count=0
    text=next(s for s in code.pe.sections if s.Name.rstrip(b'\0')==b'.text')
    def register(mu,_address,_size,_data):
        a=mu.reg_read(UC_X86_REG_RCX);b=mu.reg_read(UC_X86_REG_RDX);target=mu.reg_read(UC_X86_REG_R8)-e.base
        if not 0<=a<20 or not 0<=b<20 or not text.VirtualAddress<=target<text.VirtualAddress+text.Misc_VirtualSize:
            raise ValueError(f'Unqualified collision registration {a}/{b}/{target:#x}')
        caller=struct.unpack('<Q',mu.mem_read(mu.reg_read(UC_X86_REG_RSP),8))[0]-e.base-5
        registrations.append({'typeA':a,'nameA':names[a],'typeB':b,'nameB':names[b],
            'handlerRva':hex(target),'callRva':hex(caller),'unwindRoot':hex(code.index.root(target)) if code.index.root(target) is not None else None})
    def write(_mu,_access,address,_size,_value,_data):
        nonlocal write_count
        if not e.base+data_begin<=address<e.base+data_begin+data_size:raise ValueError('Initializer write left reviewed data region')
        write_count+=1
    e.mu.hook_add(UC_HOOK_CODE,register,begin=e.base+0x197d00,end=e.base+0x197d00)
    e.mu.hook_add(UC_HOOK_MEM_WRITE,write,begin=e.base+data_begin,end=e.base+data_begin+data_size-1)
    e.reset_stack()
    if e.run(0x197d90,stop=0x1985cb,budget=30000)!=e.base+0x1985cb:raise RuntimeError('Collision constructor prefix did not reach its boundary')
    actual=[p-e.base for p in struct.unpack('<400Q',e.mu.mem_read(e.base+table,3200))]
    rebuilt=[0x197b80]*400
    for r in registrations:
        a,b=r['typeA'],r['typeB'];rebuilt[b*20+a]=0x197c40;rebuilt[a*20+b]=int(r['handlerRva'],16)
    if actual!=rebuilt:raise AssertionError('Executed table and independently rebuilt registrations differ')
    pairs=[]
    for a in range(20):
        for b in range(20):
            target=actual[a*20+b];kind='unsupported diagnostic' if target==0x197b80 else 'swap wrapper' if target==0x197c40 else 'direct'
            handler=actual[b*20+a] if kind=='swap wrapper' else target
            pairs.append({'typeA':a,'nameA':names[a],'typeB':b,'nameB':names[b],'entryRva':hex(target),
                'kind':kind,'handlerRva':hex(handler),'arithmeticPorted':handler in {0x1a17f0,0x1af710}})
    roots={0x7fc210:'static collision orchestrator',0x7fab70:'candidate-query and narrow-phase orchestration',
        0x2a2f30:'three candidate-source traversal calls',0x2a55e0:'20x20 shape-pair dispatch',
        0x2a8460:'contact dispatch and optional postprocessing',0x2a8170:'contact postprocessing; semantics unresolved',
        0x1d19c0:'NGJK::CollideConvexVsConvex',0x1a17f0:'sphere/sphere geometry arithmetic',
        0x4d8c10:'capacity growth for 88-byte array, NOT the narrow-phase backend'}
    procedures=[]
    for root,label in roots.items():
        ins=code.instructions(root);procedures.append({'rva':hex(root),'label':label,'instructions':len(ins),
            'calls':[{'rva':hex(i.address),'assembly':i.mnemonic+' '+i.op_str} for i in ins if i.mnemonic=='call']})
    output=ROOT/'local/recon/collision-dispatch.json'
    report={'schema':'tm2020_collision_dispatch_v1','sha256':SHA,'constructorPrefix':['0x197d90','0x1985cb'],
        'stopBeforeUnrelatedTailCall':'0x19b250','tableRva':hex(table),'shapeNamesTableRva':hex(names_table),
        'rowIndex':'20*typeA+typeB','types':dict(enumerate(names)),'registrations':registrations,'pairs':pairs,
        'registeredOrderedPairs':sum(p['kind']!='unsupported diagnostic' for p in pairs),
        'uniqueDirectHandlers':len({p['handlerRva'] for p in pairs if p['kind']=='direct'}),
        'executedDataWrites':write_count,'reconstructedTableMatchesExecutedTable':True,
        'originalCodeModified':False,'gameProcessAccessed':False,'initializerTailExecuted':False,
        'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'procedures':procedures,
        'allCollisionPairsPorted':False,'stadiumChassisGeometryRecovered':False,'completePhysics':False}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS COLLISION_DISPATCH types=20 entries=400 registrations='+str(len(registrations)),
        'registered_ordered_pairs='+str(report['registeredOrderedPairs']),'complete_physics=false')


if __name__=='__main__':main()
