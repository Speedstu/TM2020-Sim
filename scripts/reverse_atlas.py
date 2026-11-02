"""Whole ordinary-.text procedure/call/string atlas for the SHA-pinned game.

This is a static inventory, not a semantic decompilation or CFG proof. Linear
unwind extents can contain data. Indirect edges and rejected decodes stay explicit.
The database is local evidence; neither executable nor process is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
from capstone.x86_const import X86_OP_IMM,X86_OP_MEM,X86_REG_RIP
from pe_unwind import PeCode
from reverse_physics import SHA,ROOT


def build(executable,destination):
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=SHA:raise ValueError('Unsupported executable')
    code=PeCode(executable);destination.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(destination)
    # A new build replaces only this tool's explicitly named tables.
    connection.executescript('''
    DROP TABLE IF EXISTS procedures; DROP TABLE IF EXISTS edges; DROP TABLE IF EXISTS strings; DROP TABLE IF EXISTS xrefs;
    CREATE TABLE procedures(root INTEGER PRIMARY KEY, ranges TEXT, instruction_count INTEGER, decode_status TEXT);
    CREATE TABLE edges(source INTEGER, instruction INTEGER, kind TEXT, target INTEGER, target_root INTEGER);
    CREATE TABLE strings(rva INTEGER PRIMARY KEY, text TEXT);
    CREATE TABLE xrefs(source INTEGER, instruction INTEGER, string_rva INTEGER);
    ''')
    strings={}
    for section in code.pe.sections:
        if section.Characteristics&0x20000000:continue
        for match in re.finditer(rb'[\x20-\x7e]{6,200}\x00',section.get_data()):
            strings[section.VirtualAddress+match.start()]=match.group()[:-1].decode('ascii')
    connection.executemany('INSERT INTO strings VALUES (?,?)',strings.items())
    started=time.monotonic();rejected=0;instructions=0;edges_count=0;xrefs_count=0
    for n,(root,ranges) in enumerate(sorted(code.index.groups.items()),1):
        edges=[];xrefs=[];status='linear_complete';ins=[]
        try:ins=code.instructions(root)
        except ValueError as error:status=str(error);rejected+=1
        for i in ins:
            if i.mnemonic in ('call','jmp'):
                target=i.operands[0].imm if len(i.operands)==1 and i.operands[0].type==X86_OP_IMM else None
                edges.append((root,i.address,i.mnemonic if target is not None else i.mnemonic+'_indirect',target,code.index.root(target) if target is not None else None))
            for op in i.operands:
                if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
                    target=i.address+i.size+op.mem.disp
                    if target in strings:xrefs.append((root,i.address,target))
        connection.execute('INSERT INTO procedures VALUES (?,?,?,?)',(root,json.dumps([[r.begin,r.end] for r in ranges]),len(ins),status))
        connection.executemany('INSERT INTO edges VALUES (?,?,?,?,?)',edges)
        connection.executemany('INSERT INTO xrefs VALUES (?,?,?)',xrefs)
        instructions+=len(ins);edges_count+=len(edges);xrefs_count+=len(xrefs)
        code.cache.pop(root,None) # Do not retain millions of Capstone objects.
        if n%5000==0:
            connection.commit();print('ATLAS_PROGRESS',n,'/',len(code.index.groups),'seconds',round(time.monotonic()-started,1),flush=True)
    connection.executescript('CREATE INDEX edge_target ON edges(target); CREATE INDEX edge_root ON edges(target_root); CREATE INDEX xref_source ON xrefs(source);')
    connection.commit()
    named=list(connection.execute("SELECT p.root,s.text FROM procedures p JOIN xrefs x ON x.source=p.root JOIN strings s ON s.rva=x.string_rva WHERE s.text LIKE '%Susp%' OR s.text LIKE '%Tire%' OR s.text LIKE '%Tyre%' OR s.text LIKE '%Wheel%' OR s.text LIKE '%NSceneDyna%'"))
    report={'schema':'tm2020_ordinary_text_atlas_v1','sha256':SHA,'procedures':len(code.index.groups),
        'runtimeRanges':len(code.index.ranges),'excludedNonTextRanges':code.excluded_ranges,'instructionsLinearlyDecoded':instructions,
        'rejectedIncompleteProcedures':rejected,'edges':edges_count,'stringXrefs':xrefs_count,'strings':len(strings),
        'elapsedSeconds':time.monotonic()-started,'physicsRelatedStringReferences':[{'root':hex(r),'text':s} for r,s in named],
        'completeSemanticReverse':False,'completeControlFlowGraph':False,'indirectEdgesResolved':False,
        'limitations':['Ordinary .text only','Unwind ranges may include data','No inferred leaf bounds','No promotion of linear edges to dynamically executed paths']}
    connection.close()
    with destination.open('rb') as stream:report['databaseSha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    report['generatorSha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    destination.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS ATLAS',json.dumps({k:report[k] for k in ('procedures','edges','rejectedIncompleteProcedures','elapsedSeconds')}))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,default=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe'))
    ap.add_argument('--out',type=Path,default=ROOT/'local/recon/game-atlas.sqlite');args=ap.parse_args();build(args.exe,args.out)
