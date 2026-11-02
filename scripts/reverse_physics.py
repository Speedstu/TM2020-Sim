"""SHA-pinned, read-only physics procedure graph and constant evidence.

Follows x64 chained unwind entries, validates instruction boundaries before
accepting RIP xrefs, and retains unresolved indirect calls. No runtime hooks.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from capstone.x86_const import X86_OP_IMM, X86_OP_MEM, X86_REG_RIP
from pe_unwind import PeCode

ROOT = Path(__file__).resolve().parents[1]
SHA = '3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda'
NAMES = ('NSceneVehiclePhy::','NSceneDyna::','MgrDyna_Integrate','PhysicsStep_TM')


def evidence(i):
    return {'rva':hex(i.address),'bytes':i.bytes.hex(),'assembly':i.mnemonic+' '+i.op_str}


def analyze(executable, destination):
    with executable.open('rb') as file:
        digest=hashlib.file_digest(file,'sha256').hexdigest()
    if digest != SHA: raise ValueError('Unknown physics build')
    code = PeCode(executable); pe = code.pe
    targets = {}
    for section in pe.sections:
        if section.Characteristics & 0x20000000: continue
        for match in re.finditer(rb'[\x20-\x7e]{6,240}',section.get_data()):
            name=match.group().decode()
            if any(t in name for t in NAMES): targets[section.VirtualAddress+match.start()] = name
    names = {}; roots = {}; xrefs = []; rejected=[]
    text = next(s for s in pe.sections if s.Name.rstrip(b'\0') == b'.text')
    data = text.get_data()
    for m in re.finditer(rb'[\x48-\x4f][\x8d\x8b\x89][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]',data):
        at=text.VirtualAddress+m.start(); target=at+7+struct.unpack_from('<i',data,m.start()+3)[0]
        if target not in targets: continue
        root=code.index.root(at)
        if root is None: continue
        try: instruction=next((i for i in code.instructions(root) if i.address==at),None)
        except ValueError as error:
            rejected.append({'rootRva':hex(root),'reason':str(error)});continue
        if instruction is None or not any(o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP and i.address+i.size+o.mem.disp==target for i in [instruction] for o in i.operands): continue
        names.setdefault(root,[]).append(targets[target]); roots.setdefault(root,0)
        xrefs.append({'name':targets[target],'stringRva':hex(target),'procedureRootRva':hex(root),'instruction':evidence(instruction)})
    # Deterministic breadth-first, depth two. Lower-level helpers outside this
    # budget remain explicit addresses rather than guessed semantic names.
    roots.setdefault(0x851f00,0) # Explicit dispatch case 5, confirmed separately in local Solo.
    queue=list(sorted(roots)); procedures={}; limit=384
    while queue and len(procedures)<limit:
        root=queue.pop(0)
        if root in procedures: continue
        depth=roots[root]
        try: instructions=code.instructions(root)
        except ValueError as error:
            rejected.append({'rootRva':hex(root),'reason':str(error)});continue
        calls=[]; constants=[]
        for i in instructions:
            if i.mnemonic=='call':
                entry=evidence(i)
                if len(i.operands)==1 and i.operands[0].type==X86_OP_IMM:
                    target=i.operands[0].imm; child=code.index.root(target)
                    entry.update(targetRva=hex(target),targetRootRva=hex(child) if child is not None else None)
                    if child is not None and child==target and depth<2 and child>=0x180000:
                        if child not in roots: roots[child]=depth+1;queue.append(child)
                else: entry['unresolvedIndirect']=True
                calls.append(entry)
            if i.mnemonic in ('movss','movsd','mulss','addss','subss','divss','comiss','ucomiss','andps','xorps'):
                for op in i.operands:
                    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                        rva=i.address+i.size+op.mem.disp; raw=pe.get_data(rva,min(16,op.size))
                        record={'addressRva':hex(rva),'rawBytes':raw.hex(),'instruction':evidence(i)}
                        if len(raw)>=4:
                            value=struct.unpack_from('<f',raw)[0]
                            if math.isfinite(value):record['binary32']=value
                        constants.append(record)
        ranges=code.index.groups[root]
        procedures[root]={'rootRva':hex(root),'profilerNames':names.get(root,[]),'graphDepth':depth,
            'ranges':[{'beginRva':hex(r.begin),'endRva':hex(r.end),'unwindRva':hex(r.unwind)} for r in ranges],
            'codeBytes':sum(r.end-r.begin for r in ranges),'instructionCount':len(instructions),'calls':calls,'constantReferences':constants}
        assembly='\n'.join(f'{i.address:08x}  {i.bytes.hex():24s} {i.mnemonic} {i.op_str}' for i in instructions)+'\n'
        (destination/f'{root:08x}.asm').write_text(assembly)
    required={0x8025a0,0x7cfce0,0x7f4d40,0x194de0,0x1886d0}
    if not required.issubset(procedures):raise ValueError('Known physics procedure graph regression')
    if len(procedures[0x8025a0]['ranges']) != 7 or not any(c.get('targetRva')=='0x7f4d40' for c in procedures[0x8025a0]['calls']):
        raise ValueError('InternalPhysicsStep chain/integrator edge missing')
    table=struct.unpack('<17I',pe.get_data(0x842e84,17*4))
    dispatch_targets={0x842b26:0x869cd0,0x842b35:0x86b060,0x842b44:0x86bc50,
        0x842b53:0x851f00,0x842b66:0x85c9e0,0x842b79:0x86d3b0,0x842b8a:None}
    if table[5]!=0x842b53 or any(t not in dispatch_targets for t in table):raise ValueError('Vehicle force dispatch table changed')
    accessors=[]
    for start,end,label in [(0x7be670,0x7be686,'model by item id'),(0x7be690,0x7be6a6,'state by item id'),
        (0x7bea40,0x7bea61,'user data by item id'),(0x7f5130,0x7f513b,'add model and item gravity coefficients')]:
        raw=pe.get_data(start,end-start);decoded=list(code.cs.disasm(raw,start))
        # Explicit leaf bounds must end at RET, never the next unrelated RET.
        if not decoded or decoded[-1].mnemonic!='ret' or decoded[-1].address+decoded[-1].size!=end:
            raise ValueError(f'Leaf accessor bound changed: {start:#x}')
        accessors.append({'label':label,'beginRva':hex(start),'endRva':hex(end),'instructions':[evidence(i) for i in decoded]})
    report={'schema':'tm2020_physics_procedure_graph_v1','sha256':digest,'analysisScope':'ordinary .text only',
        'runtimeRanges':len(code.index.ranges),'procedureRoots':len(code.index.groups),'excludedNonTextRanges':code.excluded_ranges,
        'namedPhysicsXrefs':xrefs,'analyzedProcedures':list(procedures.values()),'graphTruncated':bool(queue),'rejectedIncompleteDecodes':rejected,
        'authoritativeLiveOwnerVerified':False,'completeVehiclePhysicsPorted':False,
        'postForcePoseKernel':{'rva':'0x7f4d40','stateStride':0x58,'positionOffset':0x24,'quaternionOffset':0x30,
            'linearVelocityOffset':0x40,'angularVelocityOffset':0x4c,'quaternionOrder':'w,x,y,z',
            'angularNormSquaredThresholdBinary32Bits':'0x2edbe6ff','linearVelocityClamp':[-10000,10000],
            'angularSpeedLimitModelOffset':0x4c,'order':'position; quaternion; matrix; auxiliary model copy; linear clamp; angular clamp'},
        'vehicleForceDispatch':{'procedureRootRva':'0x8427d0','selectorOffset':0x1790,'tableRva':'0x842e84','unsignedMaximumSelector':16,
            'cases':[{'selector':n,'branchRva':hex(t),'forceProcedureRva':hex(dispatch_targets[t]) if dispatch_targets[t] else None} for n,t in enumerate(table)],
            'case5RootRva':'0x851f00','case5UnwindRanges':len(code.index.groups[0x851f00]),
            'case5InstructionCount':len(code.instructions(0x851f00))},
        'explicitlyBoundedLeafAccessors':accessors,
        'forceVelocityKernel':{'rva':'0x7f89d0','stateStride':0x58,'coefficientStride':0x10,'itemStride':0x38,'forceStride':0x18,
            'itemSkipFlag':2,'sleepSentinel':65535,'smallVelocityEnabledGlobalRva':'0x1ebccfc',
            'smallVelocityThresholdGlobalRva':'0x1ebcd04','smallVelocityMultiplierGlobalRva':'0x1ebcd00',
            'callerProvidesEffectiveParameters':True},
        'warning':'Unwind extents can include jump-table data: linear decoding is not a complete CFG. Static edges and exact arithmetic kernels do not establish a stable player root, contacts/solver fidelity or complete vehicle forces. Unresolved indirect calls remain explicit.'}
    (destination/'physics-procedure-graph.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PHYSICS_GRAPH named_xrefs',len(xrefs),'procedures',len(procedures),'truncated',bool(queue),'full_vehicle_physics=false')
    for root,items in names.items():print(hex(root),'; '.join(items),'ranges',len(code.index.groups[root]))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path,default=Path('D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe'))
    parser.add_argument('--output',type=Path,default=ROOT/'local/recon/physics');args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);analyze(args.exe,args.output)
