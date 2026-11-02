"""Build a local ray-feature cache from validated captured mesh prototypes.

Exact binary32 stored poses are reconstructed from nine-significant-digit
JSON. Candidate placements and incomplete shape-type coverage remain explicit.
No original executable, map assets or live game are needed for this conversion.
"""
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from reverse_physics import ROOT,SHA


def main():
    source=ROOT/'local/recon/live-geometry-26616-v2'
    summary=json.loads((source/'summary.json').read_text())
    if not summary['readOnly'] or summary['pid']!=26616 or summary['meshes']!=351 or summary['exactCookers']!=351 or summary['exactTreeRebuilds']!=351 or summary['completeMapCollisionVerified']:raise ValueError('Unexpected captured geometry qualification')
    meshes={};geometry_hashes={}
    dtype=np.dtype([('normal','<f4',(3,)),('plane','<f4'),('indices','<u4',(3,)),('surface','<u2'),('reserved','<u2')])
    for row in map(json.loads,(source/'meshes.jsonl').read_text().splitlines()):
        path=source/f"mesh-{row['cacheIndex']}.tmmesh";raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256'] or not row['cookerDefinedBytesExact'] or not row['treeRebuildBitExact']:raise ValueError('Geometry checksum/oracle mismatch')
        magic,nv,nt,nn=struct.unpack_from('<4I',raw)
        if magic!=0x314d5254 or len(raw)!=16+12*nv+32*nt+28*nn:raise ValueError('Malformed local mesh cache')
        vertices=np.frombuffer(raw,dtype='<f4',count=nv*3,offset=16).reshape(nv,3)
        triangles=np.frombuffer(raw,dtype=dtype,count=nt,offset=16+nv*12)
        if not np.all(np.isfinite(vertices)) or np.any(triangles['indices']>=nv):raise ValueError('Invalid captured mesh extent')
        meshes[row['cacheIndex']]=(vertices,triangles);geometry_hashes[row['cacheIndex']]=row['sha256']
    placements={}
    for row in map(json.loads,(source/'instances.jsonl').read_text().splitlines()):
        index=row['meshIndex'];pose=struct.pack('<12f',*(row['rotation']+row['translation']))
        if row['worldPlacementVerified'] or index not in meshes:raise ValueError('Unexpected placement claim or mesh index')
        placements.setdefault((geometry_hashes[index],pose),(index,pose))
    destination=ROOT/'local/collision-maps/ypPmohQofd72MyTsIsijKfrJH98-live-meshes.tmcol';destination.parent.mkdir(parents=True,exist_ok=True)
    surfaces=destination.with_suffix('.surfaces');total=0;degenerate=0;source_triangles=0
    with destination.open('wb') as output,surfaces.open('wb') as material_output:
        output.write(b'TMCOL01\0'+bytes(4));material_output.write(b'TMSURF1\0'+bytes(4))
        for index,pose in placements.values():
            vertices,triangles=meshes[index];values=np.frombuffer(pose,dtype='<f4');r=values[:9].reshape(3,3);t=values[9:]
            if not np.all(np.isfinite(values)):raise ValueError('Nonfinite placement')
            # Preserve separate multiply/add operations and native Y-X-Z order.
            world=np.empty_like(vertices)
            for k in range(3):world[:,k]=((vertices[:,1]*r[k,1]+vertices[:,0]*r[k,0])+vertices[:,2]*r[k,2])+t[k]
            coords=world[triangles['indices']].astype('<f8');normal=np.cross(coords[:,1]-coords[:,0],coords[:,2]-coords[:,0]);valid=np.linalg.norm(normal,axis=1)>=1e-12
            source_triangles+=len(valid);degenerate+=int(np.sum(~valid));count=int(np.sum(valid));total+=count
            if total>5000000:raise ValueError('Ray cache exceeds native triangle limit')
            output.write(coords[valid].tobytes());material_output.write(triangles['surface'][valid].astype('<u2').tobytes())
        output.seek(8);output.write(struct.pack('<I',total));material_output.seek(8);material_output.write(struct.pack('<I',total))
    report={'schema':'tm2020_captured_mesh_ray_cache_v1','sha256':SHA,'mapUidLabel':'ypPmohQofd72MyTsIsijKfrJH98',
        'captureProcess':26616,'prototypeMeshes':351,'prototypeVertices':197692,'prototypeTriangles':348332,
        'allPrototypeCookersAndTreesBitExact':True,'capturedPlacementCandidates':summary['typedInstanceHypotheses'],
        'uniqueGeometryPlacements':len(placements),'placedSourceTriangles':source_triangles,'triangles':total,'degenerateWorldTrianglesExcluded':degenerate,
        'cacheSha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'surfaceIdsSha256':hashlib.sha256(surfaces.read_bytes()).hexdigest(),
        'instanceInventorySha256':hashlib.sha256((source/'instances.jsonl').read_bytes()).hexdigest(),
        'runtimeNeedsGame':False,'runtimeNeedsPython':False,'worldPlacementVerified':False,'allNativeShapeTypesCaptured':False,
        'completeMapCollisionVerified':False,'exactNativeRaycastClaim':False}
    destination.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS CAPTURED_RAY_CACHE meshes=351 placements='+str(len(placements))+' triangles='+str(total)+' game_runtime=false full_map_qualified=false')


if __name__=='__main__':main()
