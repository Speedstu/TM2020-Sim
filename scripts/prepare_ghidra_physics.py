"""Build a bounded, SHA-pinned Ghidra function manifest from PE unwind chains."""
import argparse
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_IMM
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA


def main(research_set='physics'):
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown game build')
    c=PeCode(exe)
    seeds={0x851f00:'Vehicle_ForceVariant5',0x84f720:'Vehicle_Helper_84f720',0x850e50:'Vehicle_Helper_850e50',
        0x84de60:'Vehicle_Helper_84de60',0x8427d0:'Vehicle_ComputeForces',0x840890:'Vehicle_AbsorbContact',
        0x7d2b90:'Vehicle_ProcessContactPoints',0x804a10:'Dyna_ContactPatchProcessing',0x7ffcc0:'Dyna_StaticContactPreparation',
        0x7ffe90:'Dyna_DynamicContactPreparation',0x7fcd10:'Dyna_Helper_7fcd10',0x7bf0d0:'Dyna_SurfaceResponse',
        0x1b4410:'Geometry_ConvexMesh',0x19cec0:'Geometry_ConvexConvex',0x19c430:'Geometry_PrepareConvexPair',
        0x1b4260:'Geometry_PrepareTriangle',0x1cae40:'Geometry_SeparatingAxes',0x1cad10:'Geometry_AxisTest',
        0x1cb980:'Geometry_EdgeSelection',0x1cc200:'Geometry_EdgeFrame',0x1c9080:'Geometry_EdgePairContact',
        0x1cbcb0:'Geometry_FaceFromNormal',0x1cbef0:'Geometry_IncidentFace',0x1cca10:'Geometry_FaceContacts',
        0x1d19c0:'Geometry_GJK_Collision',0x1d02f0:'Geometry_GJK_Step',0x1d05c0:'Geometry_EPA_Step',
        0x19b1d0:'Geometry_BoxConvexAdapter',0x7f6ec0:'Dyna_SolveConstraints',0x8025a0:'Dyna_InternalPhysicsStep'}
    if research_set=='contacts':
        seeds={root:f'Contact_Research_{root:08x}' for root in [0x7f51a0,0x7f5390,0x7f5600,0x7f5670,
            0x7f56d0,0x7f5f40,0x7f67a0,0x7f6a50,0x7f6590,0x7f63f0,0x7ff0c0,0x7ff540,
            0x7ffcc0,0x7ffe90,0x800750,0x8020a0,0x84da80,0x841b40,0x8456b0]}
    elif research_set=='vehicle':
        seeds={root:f'Vehicle_Research_{root:08x}' for root in [0x844130,0x843190,0x8447b0,0x845b60,
            0x84f1a0,0x84f450,0x84de60,0x846010,0x850e50,0x8427d0,0x840890,0x7d2b90]}
    elif research_set=='world':
        seeds={root:f'World_Tick_Research_{root:08x}' for root in
            [0x1312870,0x12e9ea0,0x1312610,0x1311d00,0x129d760,0x12f0b50]}
    elif research_set=='controls':
        seeds={root:f'Vehicle_Control_Research_{root:08x}' for root in
            [0x80f5f0,0x819ff0,0x81a820,0x8295c0,0x829950,0x829bf0,0x83d490,0x83d8e0,
             0x83de60,0x841500,0x843190,0x850e50,0x851f00,0x869cd0,0x86b060,0x86bc50,
             0x7cfce0,0x7cfac0,0x7d1fa0,0x7d1380,0x842500,0x6c1150]}
    elif research_set=='inputsource':
        seeds={root:f'Input_Source_Research_{root:08x}' for root in
            [0x71f8c0,0x7c73a0,0x7cd040,0x7eb2c0,0x12e8a80,0x13205e0,0x1467ca0]}
    elif research_set=='sceneinputs':
        seeds={root:f'Scene_Input_Research_{root:08x}' for root in
            [0x12bce40,0x12c26a0,0x12c2cc0,0x12bdd70,0x12bde90,0x12bfc20,
             0x12f6e40,0x12dd6d0,0x2d2260,0x2d3c50,0x116fc0]}
    elif research_set=='wheelpipeline':
        seeds={root:f'Wheel_Contact_Pipeline_{root:08x}' for root in
            [0x1500140,0x840890,0x843920,0x7d2b90,0x7d41d0,0x83cc90,
             0x83d490,0x8427d0,0x851f00,0x841790,0x8447b0,0x1501f00,0x1501f50,0x83df50,0x1501800,
             0x7d2cf0,0x15009d0,0x14ffee0,0x14ff9d0,0x1501090]}
    reviewed_leaves={0x7f5670:0x7f56c4,0x7f3ec0:0x7f3f3a} if research_set=='contacts' else {}
    if research_set=='controls':
        reviewed_leaves={0x83db50:0x83db72,0x83db80:0x83dba2,
            0x83dbb0:0x83dbcb,0x83dbd0:0x83dbeb,0x83dbf0:0x83dc0b,
            0x83dc10:0x83dc2e,0x83dc30:0x83dc60,0x83dc60:0x83dc78,
            0x83dc80:0x83dc9e,0x83dd60:0x83dd85,0x83de20:0x83de5b,
            0x6c1150:0x6c1169,0x7c79e0:0x7c7a42,0x7c7c70:0x7c7c7d,
            0x1467c90:0x1467c9c}
    seeds.update({r:f'Reviewed_Leaf_{r:08x}' for r in reviewed_leaves})
    roots=dict(seeds);rejected=[]
    helper_prefix=('World_Tick_Helper' if research_set=='world' else
        'Vehicle_Control_Helper' if research_set=='controls' else 'Physics_Helper')
    for root in list(seeds):
        try:ins=c.instructions(root)
        except ValueError as error:rejected.append({'root':hex(root),'reason':str(error)});continue
        for i in ins:
            if i.mnemonic=='call' and len(i.operands)==1 and i.operands[0].type==X86_OP_IMM:
                target=i.operands[0].imm;child=c.index.root(target)
                if child==target and c.index.containing(target) is not None:roots.setdefault(target,f'{helper_prefix}_{target:08x}')
    out=ROOT/('local/recon/ghidra' if research_set=='physics' else 'local/recon/ghidra-'+research_set);out.mkdir(parents=True,exist_ok=True)
    lines=[]
    for root,name in sorted(roots.items()):
        if root in reviewed_leaves:
            if c.index.root(root) is not None:raise ValueError('Reviewed leaf unexpectedly has unwind metadata')
            end=reviewed_leaves[root];ins=list(c.cs.disasm(c.pe.get_data(root,end-root),root))
            if not ins or ins[-1].address+ins[-1].size!=end or ins[-1].mnemonic!='ret':raise ValueError('Reviewed leaf bounds changed')
            ranges=f'{root:x}-{end:x}'
        else:
            if c.index.root(root)!=root:raise ValueError(f'Unexpected non-root entry {root:#x}')
            ranges=','.join(f'{r.begin:x}-{r.end:x}' for r in c.index.groups[root])
        lines.append(f'{root:x}\t{name}\t{ranges}')
    (out/'physics-functions.tsv').write_text('\n'.join(lines)+'\n')
    (out/'manifest.json').write_text(json.dumps({'schema':'tm2020_ghidra_physics_manifest_v1','sha256':SHA,
        'functions':len(lines),'seedFunctions':len(seeds),'followedDirectCallDepth':1,'capstoneRejected':rejected,
        'automaticWholeGameAnalysisRequested':False,'semanticNamesAreResearchLabels':True,
        'reviewedLeafRanges':{hex(r):hex(end) for r,end in reviewed_leaves.items()},'completePhysics':False},indent=2)+'\n')
    print('PASS GHIDRA_MANIFEST functions='+str(len(lines)),'explicit_bounded_bodies=true')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--set',choices=['physics','contacts','vehicle','world','controls','inputsource','wheelpipeline','sceneinputs'],default='physics')
    main(parser.parse_args().set)
