"""Focused wheel/contact/CCD evidence with explicit supported and missing stages."""
import hashlib
import json
from pathlib import Path
from capstone.x86_const import X86_OP_MEM
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA,evidence


def main():
    executable=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(executable.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown executable')
    code=PeCode(executable);records=[]
    stages={0x851f00:'observed vehicle force variant',0x844090:'conditional mode-2 spring/damper branch',
        0x84f720:'vehicle helper; complete semantics unresolved',0x850e50:'vehicle helper; complete semantics unresolved',
        0x84de60:'vehicle helper; complete semantics unresolved',0x7d2b90:'PhysicsStep_ProcessContactPoints',
        0x840890:'M3to6_AbsorbContact',0x7fc730:'Dynas_StaticCollisionDetection',0x7fc210:'static collision dispatch',
        0x4d8c10:'88-byte array capacity growth, not a narrow-phase backend',0x800060:'MakeContactConstraints2',
        0x8003f0:'CreateSolverConstraints',0x7f6ec0:'SolveConstraints',0x7f5860:'prepared dynamic normal impulse sweep',
        0x7f5cb0:'prepared static normal impulse sweep',0x8603b0:'SolvePosDynaConstraints2, bounded-angle arithmetic port',
        0x860980:'SolvePosStaticConstraints2, bounded-angle arithmetic port',0x800750:'contact reevaluation between pose fractions, unported'}
    for root,label in stages.items():
        instructions=code.instructions(root)
        if not instructions:raise ValueError(f'Expected procedure absent {root:#x}')
        records.append({'root':hex(root),'label':label,'ranges':[[hex(r.begin),hex(r.end)] for r in code.index.groups[root]],
            'instructionCount':len(instructions),'calls':[evidence(i) for i in instructions if i.mnemonic=='call']})
    reads=[]
    # R15 is established as the current wheel at 0x85241b and remains the
    # wheel base through this loop. No names are inferred from numeric values.
    for i in code.instructions(0x851f00):
        if not 0x85241b<=i.address<0x852a75:continue
        for op in i.operands:
            if op.type==X86_OP_MEM and i.reg_name(op.mem.base)=='r15':
                reads.append({'wheelOffset':hex(op.mem.disp),'bytes':op.size,'instruction':evidence(i)})
    report={'schema':'tm2020_wheel_contact_pipeline_v1','sha256':SHA,'procedures':records,'wheelLoopReferences':reads,
        'springBranch':{'root':'0x844090','vehicleWheelArrayOffset':0x1780,'wheelStride':0xb8,
            'lengthOffset':0,'speedOffset':4,'contactWordOffset':0x34,'requireAllContactsVehicleOffset':0x171c,
            'configurationOffsets':{'mode':0x238,'stiffness':0x23c,'damping':0x240,'restLength':0x244},
            'formula':'(restLength - wheelLength) * stiffness - wheelSpeed * damping',
            'activeMode':2,'forceVector':'body-local (0,force,0), passed to 0x845100',
            'forceApplicationQualified':True,'forceApplicationDomain':'native wake queue disabled; supplied pose/model parameters',
            'actualBranchExecutionObserved':False},
        'substepSelection':{'root':'0x8025a0','itemSkipFlagOffset':4,'itemSkipFlag':0x10,
            'modelEnableOffset':0x5c,'additionalGeometryPointerRequired':True,
            'minimumFraction':.1,'maximumFraction':1,'remainingIntervalCutoff':1e-5,
            'formula':'dt if dot(dt*v,dt*v)<=limit^2 else dt*clamp(sqrt(limit^2/dot(dt*v,dt*v)),0.1,1)',
            'contactReevaluationCall':'0x800750','completeSchedulerRecovered':False},
        'preparedNormalConstraints':{'dynamic':{'root':'0x7f5860','stride':0x2c},'static':{'root':'0x7f5cb0','stride':0x28},
            'projection':'max(0, -(relativeNormalSpeed + bias)*effectiveCoefficient + accumulatedImpulse)',
            'dotOrder':'Y then X then Z','singleSequentialSweepOnly':True},
        'positionConstraintLayouts':{'dynamic':{'stride':0x2c,'bodyA':0,'bodyB':4,'localA':8,'localB':0x14,'normal':0x20},
            'static':{'stride':0x28,'body':0,'localPoint':4,'targetPoint':0x10,'normal':0x1c},
            'warning':'Same strides as velocity constraints do not mean the same field layout or interchangeable buffers'},
        'remaining':['Complete force variant and material/slip helpers','Narrow-phase geometry and contact generation',
            'Complete constraint iteration scheduler and unqualified trig domains','Adaptive contact-interleaved step orchestration','Verified physics-tick capture and held-out trajectory validation'],
        'completeSemanticReverse':False,'fullVehiclePhysics':False}
    target=ROOT/'local/recon/wheel-contact-pipeline.json';target.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS WHEEL_CONTACT_PIPELINE procedures',len(records),'wheel_refs',len(reads),'complete_physics=false')


if __name__=='__main__':main()
