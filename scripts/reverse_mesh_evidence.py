"""Record pinned mesh/SAT layouts, procedures and unresolved manifold stages."""
import hashlib
import json
from pathlib import Path
from pe_unwind import PeCode
from reverse_physics import ROOT,SHA,evidence


def main():
    exe=Path(r'D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe')
    if hashlib.sha256(exe.read_bytes()).hexdigest()!=SHA:raise ValueError('Unknown geometry executable')
    code=PeCode(exe);records=[]
    names={0x1adb10:'triangle cooker, preallocated output path',0x1ae360:'mesh AABB preparation, arithmetic slice qualified',
        0x19ee90:'center mean/variance axis',0x19f2e0:'strict mean partition with fallback',0x19f580:'leaf/internal node generation',
        0x19fad0:'recursive preorder tree construction',0x1a01b0:'AABB tree iterator',0x1af710:'sphere/cooked-mesh contact generation',
        0x1cab20:'vertex projection interval',0x1cad10:'single SAT axis evaluation',0x1cae40:'face and cross-edge separating axes',
        0x1b4410:'convex/mesh manifold, deterministic clipping and edge domain',0x19cec0:'convex/convex manifold, deterministic clipping and edge domain',
        0x1cc3e0:'polygon split, deterministic intersection domain',0x1cca10:'face contact clipping, deterministic intersection domain',
        0x1cb980:'support edge selection',0x1cbcb0:'face selection within normal group',0x1cbef0:'incident face selection',
        0x1cc200:'edge frame construction',0x1c9080:'complete piecewise edge-pair minimization',
        0x804a10:'complete contact patch grouping and penetration length conversion'}
    for root,label in names.items():
        ins=code.instructions(root);records.append({'root':hex(root),'label':label,'ranges':[[hex(r.begin),hex(r.end)] for r in code.index.groups[root]],
            'instructions':len(ins),'calls':[evidence(i) for i in ins if i.mnemonic=='call']})
        (ROOT/f'local/recon/physics/{root:08x}-qualified.asm').write_text('\n'.join(f'{i.address:08x} {i.bytes.hex():24} {i.mnemonic} {i.op_str}' for i in ins)+'\n')
    sources=['native/include/tm2020/recovered_mesh.hpp','native/src/recovered_mesh.cpp',
        'native/include/tm2020/recovered_convex.hpp','native/src/recovered_convex.cpp',
        'native/include/tm2020/recovered_polygon.hpp','native/src/recovered_polygon.cpp',
        'native/include/tm2020/recovered_features.hpp','native/src/recovered_features.cpp','native/src/recovered_edge_pair.cpp',
        'native/include/tm2020/recovered_convex_collision.hpp','native/src/recovered_convex_collision.cpp',
        'native/include/tm2020/recovered_patches.hpp','native/src/recovered_patches.cpp']
    result={'schema':'tm2020_mesh_convex_evidence_v1','sha256':SHA,'procedures':records,
        'meshObject':{'verticesPointer':0x20,'indexedTrianglesPointer':0x30,'indexedTriangleCount':0x38,
            'cookedTrianglesPointer':0x40,'cookedTriangleCount':0x48,'aabbNodesPointer':0x50,'aabbNodeCount':0x58},
        'indexedTriangle':{'stride':0x10,'vertexIndices':[0,4,8],'surfaceId':0xc,'reserved':0xe},
        'cookedTriangle':{'stride':0x20,'normal':0,'planeConstant':0xc,'vertexIndices':[0x10,0x14,0x18],'surfaceId':0x1c,'reserved':0x1e,
            'normalizationSquaredThresholdBits':'0x1e3ce509','planeConstantOrder':'((-nx)*vx-ny*vy)-nz*vz'},
        'aabbNode':{'stride':0x1c,'center':0,'halfExtent':0xc,'tag':0x18,'leafBit':1,
            'leafPayload':'triangle index','internalPayload':'preorder subtree skip count','payloadShift':1},
        'treeConstruction':{'meshDefaultLeafWidth':2,'axis':'largest center variance; strict ties favor X then Y then Z',
            'partition':'move centers strictly greater than mean to front, in native swap order',
            'fallback':'midpoint if split<=begin+floor(n/3) or split>=end-floor(n/3)-1',
            'nativeAllocationQualified':False,'topLevelMeshConstructorQualified':False},
        'sphereMesh':{'frontFacesOnly':True,'meshTangencyAccepted':True,'faceFlag':1,'meshPointFlag':2,
            'vertexSquaredCutoffBits':'0x2edbe6ff','edgeInteriorSquaredCutoffBits':'0x3727c5ac',
            'penetrationDirection':'triangle normal, even for edge/vertex hits','pointNormal':'radial at edge/vertex',
            'duplicatesRemoved':False,'faceEdgeVertexAndBooleanQueriesQualified':True},
        'convexAxesDescriptor':{'verticesSpan':0,'normalDirectionsSpan':0x10,'edgeDirectionsSpan':0x20,
            'faceTopologySpan':0x30,'edgeTopologySpan':0x40,'manifoldArithmeticQualifiedWithinDomain':True},
        'faceTopology':{'stride':40,'normalIndex':0x10,'keepNormal':0x14,'vertexIndexPointer':0x18,'vertexIndexCount':0x20},
        'edgeTopology':{'stride':12,'vertexA':0,'vertexB':4,'directionIndex':8},
        'convexManifolds':{'handlers':['0x19cec0','0x1b4410'],'allThreeWitnessKindsQualified':True,
            'nativeUnusedContactBytesCompared':False,'meshCandidateCap':128,'candidateCapSaturationQualified':True,
            'nearParallelUndefinedClipBranchQualified':False,'bothZeroHalfLengthEdgePairsQualified':False,
            'registeredThreeArgumentWrapperQualified':False,'nativeScratchAllocationQualified':False,
            'relativeTranslation':'separate positive and negative projections before addition',
            'convexPairPenetrationOrder':'multiply in local space, then rotate',
            'convexMeshPenetrationOrder':'rotate normal, then multiply by depth'},
        'sat':{'margin':'expands A interval only','crossAxisSquaredCutoffBits':'0x2edbe6ff','crossAxisSelectionBiasBits':'0x38d1b717',
            'witnessKinds':{'0':'A face axis','1':'B face axis','2':'edge cross axis'},
            'unusedNativeFeatureBytesCompared':False,'contactManifoldPortedWithinDomain':True},
        'polygonClipping':{'classifyPointLeafRange':['0x1cc390','0x1cc3d5'],
            'classification':{'0':'distance > +1e-4','1':'distance < -1e-4','2':'inclusive on-plane band'},
            'nearParallelUninitializedNativeBranchQualified':False,'sdkRejectsIntersectionAbsDenominatorAtMost':1e-5,
            'faceClipPreservesEmptyInputPingPongStaleBufferBehavior':True,
            'faceFinalFilter':'signed distance <= 0, no tolerance',
            'nativeScratchAllocatorQualified':'precommitted sufficient-capacity arena only'},
        'contactPatches':{'entry':'0x804a10','maxContactsPerChunk':255,'normalDotThresholdBits':'0x3f7fbe77',
            'surfaceGrouping':'low byte of each surface ID','mergesNonconsecutiveRuns':True,
            'pointOrder':'primary run followed by its linked matching runs','depth':'sqrt((penX^2 + penY^2) + penZ^2)',
            'nativeHeapGrowthQualified':False,'precommittedNativeBlockAllocatorQualified':True},
        'sourceHashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
        'stadiumTrackAssetsRecovered':False,'completeVehiclePhysics':False}
    (ROOT/'local/recon/mesh-convex-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS MESH_CONVEX_EVIDENCE procedures='+str(len(records)),'bounded_domain_manifolds=true full_vehicle_physics=false')


if __name__=='__main__':main()
