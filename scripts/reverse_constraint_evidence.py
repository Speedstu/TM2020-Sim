"""Source-pinned constraint layouts, argument contracts, and math constants."""
import hashlib
import json
import struct
from pathlib import Path
from capstone.x86_const import X86_OP_MEM,X86_REG_RIP
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA,evidence


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown executable')
    code=PeCode(exe);procedures=[]
    stages={0x85ecd0:'dynamic Jacobian coefficient initializer',0x85fc50:'dynamic unilateral Jacobian sweep',
        0x85ffd0:'static unilateral Jacobian sweep',0x85eab0:'bounded dynamic Jacobian impulse',
        0x85ff00:'dynamic friction sweep, bounds from referenced normal impulse',
        0x8601a0:'static friction sweep, bounds from referenced normal impulse',
        0x85eea0:'dynamic contact constraint preparation',0x85f5b0:'static contact constraint preparation',
        0x85e4f0:'positive axis-angle position correction',0x85e7d0:'negative axis-angle position correction',
        0x8603b0:'dynamic position constraint sweep',0x860980:'static position constraint sweep',
        0x1a17f0:'sphere/sphere contact geometry',0x7f6ec0:'complete velocity island scheduler, external callbacks empty',
        0x7f5090:'world-point velocity',0x7f51a0:'general point constraint delta',0x7f5390:'general point impulse application',
        0x7f56d0:'general point constraint sweep',0x7f5600:'angular constraint delta',
        0x7f5f40:'angular constraint sweep',0x7f67a0:'angular rate coupling sweep',
        0x1955c0:'quaternion-vector rotation without normalization assumption',
        0x7f6110:'projection position correction helper',0x7f61d0:'anchored position correction helper',
        0x7f63f0:'complete projection position sweep',0x7f6590:'complete anchored position sweep',
        0x7f6a50:'complete quaternion-axis position sweep',0x7f8db0:'complete model-center frame shift'}
    for root,label in stages.items():
        ins=code.instructions(root);constants=[]
        (ROOT/f'local/recon/physics/{root:08x}-qualified.asm').write_text(
            '\n'.join(f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in ins)+'\n')
        for i in ins:
            for o in i.operands:
                if o.type==X86_OP_MEM and o.mem.base==X86_REG_RIP:
                    rva=i.address+i.size+o.mem.disp;raw=code.pe.get_data(rva,max(4,o.size))
                    constants.append({'rva':hex(rva),'raw':raw.hex(),'instruction':evidence(i)})
        procedures.append({'root':hex(root),'label':label,'ranges':[[hex(r.begin),hex(r.end)] for r in code.index.groups[root]],
            'instructionCount':len(ins),'calls':[evidence(i) for i in ins if i.mnemonic=='call'],'ripReferences':constants})
    position_loop=list(code.cs.disasm(code.pe.get_data(0x8033b2,0x80359a-0x8033b2),0x8033b2))
    if not position_loop or position_loop[-1].address+position_loop[-1].size!=0x80359a:raise ValueError('Position-loop instruction boundary changed')
    (ROOT/'local/recon/physics/008033b2-position-loop-qualified.asm').write_text(
        '\n'.join(f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in position_loop)+'\n')
    constants={}
    for name,rva in {'cos_z3':0x1d23560,'cos_z2':0x1d23550,'cos_z1':0x1d23540,'cos_z3_add':0x1d23558,
        'cos_z2_add':0x1d23548,'sin_z3':0x1d23588,'sin_z2':0x1d23578,'sin_z3_add':0x1d23580,
        'sin_z2_add':0x1d23570,'sin_small_cubic':0x1d22ce0}.items():
        raw=code.pe.get_data(rva,8);constants[name]={'rva':hex(rva),'binary64Bits':hex(struct.unpack('<Q',raw)[0]),'value':struct.unpack('<d',raw)[0]}
    source_files=['native/include/tm2020/recovered_jacobian.hpp','native/src/recovered_jacobian.cpp',
        'native/include/tm2020/recovered_position.hpp','native/src/recovered_position.cpp',
        'native/include/tm2020/recovered_collision.hpp','native/src/recovered_collision.cpp',
        'native/include/tm2020/recovered_solver.hpp','native/src/recovered_solver.cpp',
        'native/include/tm2020/recovered_joints.hpp','native/src/recovered_joints.cpp',
        'native/include/tm2020/recovered_joint_position.hpp','native/src/recovered_joint_position.cpp',
        'native/include/tm2020/recovered_frames.hpp','native/src/recovered_frames.cpp',
        'native/include/tm2020/recovered_world.hpp','native/src/recovered_world.cpp']
    result={'schema':'tm2020_constraint_evidence_v1','sha256':SHA,'procedures':procedures,'scalarMathConstants':constants,
        'dynamicJacobianRecord':{'stride':0x58,'bodyA':0,'bodyB':4,'direction':8,'angularA':0x14,'angularB':0x20,
            'weightedAngularA':0x2c,'weightedAngularB':0x38,'inverseMassA':0x44,'inverseMassB':0x48,
            'effectiveCoefficient':0x4c,'target':0x50,'accumulatedImpulse':0x54},
        'staticJacobianRecord':{'stride':0x38,'body':0,'direction':4,'angular':0x10,'weightedAngular':0x1c,
            'inverseMass':0x28,'effectiveCoefficient':0x2c,'target':0x30,'accumulatedImpulse':0x34},
        'frictionRecords':{'dynamicStride':0x60,'dynamicNormalIndex':0x58,'dynamicMu':0x5c,
            'staticStride':0x40,'staticNormalIndex':0x38,'staticMu':0x3c,
            'bounds':'[-mu*normalAccumulatedImpulse,+mu*normalAccumulatedImpulse]','axesClampedIndependently':True},
        'contactInput':{'stride':0x2c,'bodyA':0,'bodyB':4,'point':8,'normal':0x14,'separation':0x20,'friction':0x24,'restitution':0x28},
        'contactPreparation':{'positionAnchors':'point + (-normal)*(separation * +/-0.5)',
            'normalDirection':'negative input normal','tangentBasis':'axis selected by abs(normalX)>abs(normalY), second is normal cross first',
            'containerAllocationPorted':False,'sufficientCapacityOriginalPathQualified':True},
        'positionConfigArgument':{'allowedSeparation':0x14,'maximumCorrection':0x18,'factor':0x1c,'isSolverParametersReinterpretation':False},
        'positionCorrectionDomain':{'maximumAngularNorm':1.57079625,'mathDispatchFlagRva':'0x1f840e4','qualifiedValues':[0,1],
            'trigArgumentReductionRecovered':False,'boundedAvxFmaMathPathQualified':True,
            'fmaPortUsesExplicitCorrectlyRoundedDoubleFma':True,'fullFmaPositionSweepsOriginalInstructionsNative':True,
            'ownedExecutableLoaderTlsNullProfiler':True,'wholeFmaPositionIslandLoopInstructionOracleQualified':False},
        'sphereGeometry':{'root':'0x1a17f0','shapeRadius':0x28,'shapeSurfaceId':0x20,'instanceCenter':0x2c,
            'strictOverlap':True,'coincidentCutoff':1e-5,'coincidentFallbackUsesRadiusBOnly':True},
        'sourceHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files},
        'contactIslandScheduler':{'islandStride':0x140,'configStaticFrictionIterations':0,'configDynamicFrictionIterations':4,'configVelocityIterations':8,
            'contactSpanOffsets':{'staticFrictionNormals':0x10,'staticFinalNormals':0x20,'staticFriction':0x40,'staticNormals':0x50,
                'dynamicFrictionNormals':0xa0,'dynamicFinalNormals':0xb0,'dynamicNormals':0xd0,'dynamicFriction':0xe0},
            'contactOnlyApiEmptyGeneralConstraintSpanOffsets':[0x30,0xc0,0x120,0x130],'externalConstraintListEmpty':True,
            'iterationOrder':['for each island: dynamic compact + friction if below dynamic threshold',
                'for each island: static compact + friction if below static threshold','for each island: static Jacobian normals',
                'for each island: dynamic compact final + Jacobian normals','for each island: static compact final'],
            'scheduleTraceVerifiedEveryDifferentialCase':True,'generalJointVelocitySpansQualified':True,
            'generalJointVelocitySpanOffsets':{'latePoints':0x30,'earlyPoints':0xc0,'angularCouplings':0x120,'angularConstraints':0x130}},
        'pointConstraint':{'stride':60,'bodyA':0,'bodyB':4,'worldPointA':8,'worldPointB':0x14,'direction':0x20,
            'bias':0x2c,'softness':0x30,'effectiveCoefficient':0x34,'accumulatedImpulse':0x38,
            'clamp':'nonnegative accumulated impulse only when softness == 0','fixedBodyBSentinel':'0xffffffff','bodyAMustExist':True},
        'angularConstraint':{'stride':36,'bodyA':0,'bodyB':4,'direction':8,'bias':0x14,'softness':0x18,
            'effectiveCoefficient':0x1c,'accumulatedImpulse':0x20,'applicationCoefficientLane':3,'eitherBodyMayBeFixed':True},
        'angularCoupling':{'stride':60,'bodyA':0,'bodyB':4,'axisA':8,'axisB':0x14,'weightsA':0x20,'weightsB':0x2c,'ratio':0x38,
            'relativeErrorThresholdBits':'0x3a83126f','updatesOverwriteFullAngularVectorsWithAxisProjections':True,
            'jointPreparationQualified':False,'generalJointPositionCorrectionsQualified':True},
        'positionIslandScheduler':{'parentRoot':'0x8025a0','start':'0x8033b2','stopExclusive':'0x80359a',
            'entireParentFunctionQualified':False,'positionIterationsGlobalRva':'0x1ebcd1c',
            'islandStride':0x140,'orderPerIsland':['dynamicOrientation','staticOrientation','dynamicAnchors','staticAnchors','dynamicProjection','staticProjection','dynamicContacts','staticContacts'],
            'spanOffsets':{'dynamicOrientation':0x100,'staticOrientation':0x80,'dynamicAnchors':0x110,'staticAnchors':0x70,
                'dynamicProjection':0x90,'staticProjection':0,'dynamicContacts':0xf0,'staticContacts':0x60},
            'allEightOriginalPassesExecute':True,'everyCallTraceChecked':True},
        'projectionPositionConstraint':{'stride':36,'bodyA':0,'bodyB':4,'projectionLimit':8,'worldPoint':0xc,'direction':0x18,
            'negativeErrorsOnly':True,'dynamicCorrectionMultiplier':0.5},
        'anchoredPositionConstraint':{'stride':60,'bodyA':0,'bodyB':4,'localA':8,'localB':0x14,'projectionTarget':0x20,
            'worldPoint':0x24,'direction':0x30,'localAMultiplierBits':'0x3f733333','dynamicCorrectionMultiplierBits':'0x3dcccccd'},
        'quaternionAxisConstraint':{'stride':40,'body':0,'axis':8,'referenceWxyz':0x18,
            'rotationMatrixPreservedByOriginal':True,'axisProjectionCutoff':1e-5},
        'modelCenterFrame':{'root':'0x7f8db0','modelCenterOffset':0x40,'statePositionOffset':0x24,
            'stepOrder':['integrate forces in model-origin frame','add R*modelCenter','collision and velocity/pose/position solvers','subtract newR*modelCenter'],
            'wholeStepQualified':False,'inverseShiftsNeedNotBitCancel':True},
        'completeTireModelRecovered':False,'allNarrowPhasePairsPorted':False,'completePhysics':False}
    (ROOT/'local/recon/constraint-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS CONSTRAINT_EVIDENCE procedures='+str(len(procedures)),'scalar_constants='+str(len(constants)),'complete_physics=false')


if __name__=='__main__':main()
