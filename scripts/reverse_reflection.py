"""Extract current-build Nadeo reflection registration from bounded PE functions.

Offline development tool; Python/Capstone are not native SDK dependencies.
Offsets are registration evidence, not proof of an authoritative player object.
Only decode at .pdata function starts, and forget volatile registers at calls
and control-flow boundaries. Emit the exact supporting instruction bytes.
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
from pathlib import Path
import re
import struct
import pefile
from pe_unwind import PeCode
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_GRP_JUMP
from capstone.x86_const import X86_OP_IMM, X86_OP_REG, X86_OP_MEM, X86_REG_RIP

ROOT = Path(__file__).resolve().parents[1]
# These anchors were inspected in the SHA-pinned executable. Unknown builds
# must be analyzed again; never silently carry offsets into another release.
BUILD_SHA = '3fc7d8cda542beda131c44306b123f4004d07d7e22f512b46b762afc29f6edda'
CLASS = 0x2EA9E0
FIELD = 0x2EB040
CALLBACK = 0x1DC170
FACTORY = 0x2EABA0
FINALIZE = 0x2EBC70
ALIASES = {a:b for a,b in [('eax','rax'),('ecx','rcx'),('edx','rdx'),('r8d','r8'),('r9d','r9'),('r10d','r10'),('r11d','r11')]}
ALIASES.update(dict(zip(('ebx','ebp','esi','edi','r12d','r13d','r14d','r15d'),('rbx','rbp','rsi','rdi','r12','r13','r14','r15'))))
VOLATILE = ('rax','rcx','rdx','r8','r9','r10','r11')

def analyze(instructions, read_string):
    registers = {}
    evidence = {}
    classes = []
    current = None
    calls = []
    last_call = None
    finalized = False
    def name(ins, reg):
        n = ins.reg_name(reg)
        return ALIASES.get(n,n)
    def assign(reg, value, ins):
        if value is None:
            registers.pop(reg,None); evidence.pop(reg,None)
        else:
            registers[reg] = value
            evidence[reg] = {'rva':hex(ins.address),'bytes':ins.bytes.hex(),'assembly':ins.mnemonic+' '+ins.op_str}
    for ins in instructions:
        ops = ins.operands
        if ins.mnemonic == 'call':
            target = ops[0].imm if len(ops)==1 and ops[0].type==X86_OP_IMM else None
            calls.append(target)
            if target == CLASS:
                text = read_string(registers.get('rdx'))
                if text and re.fullmatch(r'[CN][A-Za-z0-9_:$<>]+',text):
                    current = {'name':text,'registrationRva':hex(ins.address),
                               'registeredSize':registers.get('r8'), 'properties':[],
                               'callbacks':[], 'evidence':{k:v for k,v in evidence.items() if k in ('rdx','r8')},
                               'precedingCalls':[hex(t) for t in calls[-5:-1] if t is not None]}
                    classes.append(current)
            elif current is not None and target == FIELD:
                text = read_string(registers.get('rcx'))
                offset = registers.get('rdx')
                if text and offset is not None and 0 <= offset < 0x100000:
                    current['properties'].append({'name':text,'offset':offset,
                        'registrationRva':hex(ins.address),'descriptorHelperRva':hex(last_call) if last_call else None,
                        'evidence':{k:v for k,v in evidence.items() if k in ('rcx','rdx')}})
            elif current is not None and target == CALLBACK:
                text = read_string(registers.get('rcx'))
                if text:
                    current['callbacks'].append({'name':text,'registrationRva':hex(ins.address),
                        'argumentRdxRva':hex(registers['rdx']) if 'rdx' in registers else None,
                        'argumentR8Rva':hex(registers['r8']) if 'r8' in registers else None})
            elif current is not None and target == FACTORY:
                current['factoryArguments']={k:hex(v) for k,v in registers.items() if k in ('rcx','rdx','r8','r9')}
            finalized = target == FINALIZE
            for r in VOLATILE:
                registers.pop(r,None); evidence.pop(r,None)
            last_call = target
            continue
        # The finalize() result is stored at a RIP-relative global. This is a
        # class descriptor slot, NOT a player pointer.
        if (current is not None and finalized and ins.mnemonic=='mov' and len(ops)==2
                and ops[0].type==X86_OP_MEM and ops[0].mem.base==X86_REG_RIP
                and ops[1].type==X86_OP_REG and name(ins,ops[1].reg)=='rax'):
            current['descriptorGlobalRva']=hex(ins.address+ins.size+ops[0].mem.disp)
        finalized = False
        if ins.group(CS_GRP_JUMP) or ins.mnemonic.startswith('ret'):
            registers.clear(); evidence.clear()
            continue
        if len(ops)<1 or ops[0].type!=X86_OP_REG:
            continue
        dest = name(ins,ops[0].reg)
        value = None
        if ins.mnemonic=='mov' and len(ops)==2:
            if ops[1].type==X86_OP_IMM: value=ops[1].imm
            elif ops[1].type==X86_OP_REG: value=registers.get(name(ins,ops[1].reg))
        elif ins.mnemonic=='xor' and len(ops)==2 and ops[1].type==X86_OP_REG and ops[0].reg==ops[1].reg:
            value=0
        elif ins.mnemonic=='lea' and len(ops)==2 and ops[1].type==X86_OP_MEM:
            m=ops[1].mem
            if m.base==X86_REG_RIP: value=ins.address+ins.size+m.disp
            elif not m.index and name(ins,m.base) in registers: value=registers[name(ins,m.base)]+m.disp
        # Only invalidate destinations actually written (cmp/test have no writes).
        if ins.mnemonic in ('mov','lea','xor','add','sub','and','or','pop','inc','dec'):
            assign(dest,value,ins)
    return classes

def selftest():
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    # mov r8d,0x360; lea rdx,[rip+0x100]; call CLASS;
    # mov edx,0x20; lea rcx,[rip+0x200]; call FIELD
    b=bytearray()
    b.extend(bytes.fromhex('41b860030000488d1500010000'))
    b.extend(b'\xe8'+struct.pack('<i',CLASS-(0x1000+len(b)+5)))
    b.extend(bytes.fromhex('ba20000000488d0d00020000'))
    b.extend(b'\xe8'+struct.pack('<i',FIELD-(0x1000+len(b)+5)))
    result=analyze(list(cs.disasm(bytes(b),0x1000)),lambda r:'CFixture' if r==0x110d else ('Speed' if r==0x121e else None))
    assert result and result[0]['registeredSize']==0x360,result
    assert result[0]['properties'][0]['offset']==0x20,result
    # Namespace structs are registered too. A zeroed nonvolatile 32-bit
    # register is a valid base for LEA offsets in the continued procedure.
    ns=analyze(list(cs.disasm(bytes(b),0x1000)),lambda r:'NSceneDyna::SFixture' if r==0x110d else 'Speed')
    assert ns[0]['name']=='NSceneDyna::SFixture',ns
    alias=bytearray(b[:18])+bytes.fromhex('4531e4418d542420488d0d00020000')
    field_name=0x1000+len(alias)+0x200
    alias+=b'\xe8'+struct.pack('<i',FIELD-(0x1000+len(alias)+5))
    ns=analyze(list(cs.disasm(bytes(alias),0x1000)),lambda r:'NFixture' if r==0x110d else ('Speed' if r==field_name else None))
    assert ns[0]['properties'][0]['offset']==0x20,ns
    # Branching and unknown helper calls must invalidate argument evidence.
    for barrier in (b'\x75\x00',b'\xe8\x00\x00\x00\x00'):
        prefix=bytes(b[:18])+bytes.fromhex('ba20000000488d0d00020000')+barrier
        call=b'\xe8'+struct.pack('<i',FIELD-(0x1000+len(prefix)+5))
        guarded=analyze(list(cs.disasm(prefix+call,0x1000)),lambda r:'CFixture' if r==0x110d else 'Speed')
        assert len(guarded)==1 and not guarded[0]['properties'],guarded
    print('PASS reflection argument extraction, branch/call invalidation, evidence')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--selftest',action='store_true')
    ap.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    ap.add_argument('--out',type=Path,default=ROOT/'local/recon/reflection-current-build.json')
    args=ap.parse_args()
    if args.selftest:return selftest()
    data=args.exe.read_bytes(); sha=hashlib.sha256(data).hexdigest()
    if sha!=BUILD_SHA:raise ValueError('Unsupported executable hash: revalidate reflection anchors first')
    code=PeCode(args.exe);pe=code.pe
    cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True
    candidates=set()
    for s in pe.sections:
        if not s.Characteristics & 0x20000000:continue
        raw=s.get_data();pos=0
        while True:
            i=raw.find(b'\xe8',pos)
            if i<0 or i+5>len(raw):break
            pos=i+1; rva=s.VirtualAddress+i
            if rva+5+struct.unpack_from('<i',raw,i+1)[0]!=CLASS:continue
            root=code.index.root(rva)
            if root is not None:candidates.add(root)
    def read_string(rva):
        if rva is None:return None
        try:
            b=pe.get_data(rva,256).split(b'\0',1)[0]
            if not b or len(b)>=256 or any(x<32 or x>126 for x in b):return None
            return b.decode('ascii')
        except pefile.PEFormatError:return None
    classes=[]
    rejected=[]
    for begin in sorted(candidates):
        ranges=code.index.groups[begin]
        if sum(r.end-r.begin for r in ranges)>0x40000:continue
        try:ins=code.instructions(begin)
        except ValueError as error:rejected.append({'root':hex(begin),'reason':str(error)});continue
        for c in analyze(ins,read_string):
            c['functionBeginRva']=hex(begin);c['functionEndRva']=hex(max(r.end for r in ranges))
            c['functionRanges']=[{'beginRva':hex(r.begin),'endRva':hex(r.end)} for r in ranges]
            c['sizeArgumentSemantics']='registered allocation/struct extent; dynamic use unverified'
            c['offsetsAreRegistrationArguments']=True
            c['authoritativeVehicleOwnerVerified']=False
            classes.append(c)
    result={'schema':'tm2020_nadeo_reflection_v1','exeSha256':sha,'readOnly':True,
        'classRegisterRva':hex(CLASS),'fieldRegisterRva':hex(FIELD),
        'functionBoundariesSource':'PE .pdata with validated chained UNWIND_INFO, ordinary .text only',
        'rejectedIncompleteDecodes':rejected,
        'classCount':len(classes),'propertyCount':sum(len(c['properties']) for c in classes),
        'livePlayerPointerVerified':False,'classes':classes}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    interesting=[c for c in classes if re.search('Vehicle|PlayerInfo|InputPort|PlayerInput',c['name'])]
    for c in interesting:
        print(c['name'],'size',hex(c['registeredSize'] or 0),'fields',len(c['properties']),'global',c.get('descriptorGlobalRva'))
        for f in c['properties']:
            if re.search('State|Pos|Vel|Speed|Input|Steer|Phy|Player|Contact|Rot|Time',f['name']):
                print(' ',hex(f['offset']),f['name'])
    print('EXTRACTED',len(classes),'classes',result['propertyCount'],'properties',args.out)

if __name__=='__main__':main()
