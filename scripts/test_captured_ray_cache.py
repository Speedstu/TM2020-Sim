"""Compare native BVH closest distances with independent exhaustive plane tests."""
import json
from pathlib import Path
import struct
import subprocess
import numpy as np
from reverse_physics import ROOT


def main():
    cache=ROOT/'local/collision-maps/ypPmohQofd72MyTsIsijKfrJH98-live-meshes.tmcol'
    with cache.open('rb') as source:
        if source.read(8)!=b'TMCOL01\0':raise ValueError('Unexpected triangle cache')
        count=struct.unpack('<I',source.read(4))[0]
    triangles=np.memmap(cache,dtype='<f8',mode='r',offset=12,shape=(count,3,3))
    a=triangles[:,0];e1=triangles[:,1]-a;e2=triangles[:,2]-a;normal=np.cross(e1,e2);normal_squared=np.sum(normal*normal,axis=1)
    rng=np.random.default_rng(2026102403);rays=[]
    for index in rng.integers(0,count,128):
        n=normal[index]/np.sqrt(normal_squared[index]);center=triangles[index].mean(axis=0);rays.append([*(center+n*.1),*(-n),1.])
    for _ in range(128):
        origin=np.array([rng.uniform(500,1700),rng.uniform(5,120),rng.uniform(800,1900)]);direction=rng.normal(size=3);rays.append([*origin,*direction,250.])
    output=ROOT/'local/recon/captured-ray-audit';output.mkdir(parents=True,exist_ok=True)
    inputs=output/'rays.txt';inputs.write_text(''.join(' '.join(format(x,'.17g') for x in r)+'\n' for r in rays))
    result=subprocess.run([str(ROOT/'native/build/tm2020_trackray.exe'),str(cache),'--batch',str(inputs)],check=True,capture_output=True,text=True)
    actual=[json.loads(row) for row in result.stdout.splitlines()]
    if len(actual)!=len(rays):raise ValueError('Native ray count differs')
    hits=0;misses=0;maximum_error=0.
    for index,(ray,native) in enumerate(zip(rays,actual)):
        origin=np.asarray(ray[:3]);direction=np.asarray(ray[3:6]);direction=direction/np.linalg.norm(direction);limit=ray[6]
        denominator=np.sum(normal*direction,axis=1);valid=np.abs(denominator)>=1e-13;safe=np.where(valid,denominator,1.)
        distances=np.sum(normal*(a-origin),axis=1)/safe;valid&=(distances>=1e-8)&(distances<=limit)
        at=np.flatnonzero(valid)
        if len(at):
            relative=(origin-a[at])+distances[at,None]*direction
            u=np.sum(np.cross(relative,e2[at])*normal[at],axis=1)/normal_squared[at]
            v=np.sum(np.cross(e1[at],relative)*normal[at],axis=1)/normal_squared[at]
            inside=(u>=-1e-11)&(u<=1+1e-11)&(v>=-1e-11)&(u+v<=1+1e-11);at=at[inside]
        if bool(native['hit'])!=bool(len(at)):raise AssertionError(f'BVH/exhaustive hit differs for ray {index}')
        if len(at):
            expected=float(np.min(distances[at]));error=abs(native['distance']-expected);maximum_error=max(maximum_error,error)
            if error>1e-7:raise AssertionError(f'BVH/exhaustive closest distance differs for ray {index}: {error}')
            hits+=1
        else:misses+=1
    if not hits or not misses:raise AssertionError('Ray hit/miss cohort missing')
    report={'schema':'tm2020_captured_ray_bvh_audit_v1','triangles':count,'rays':len(rays),'hits':hits,'misses':misses,
        'independentExhaustivePlaneAndBarycentricChecks':True,'distanceAbsoluteTolerance':1e-7,'maximumDistanceError':maximum_error,
        'triangleTieIdentityQualified':False,'originalGameRaycastOracleQualified':False,'completeMapCollisionQualified':False}
    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'native-output.jsonl').write_text(result.stdout)
    print('PASS CAPTURED_RAY_BVH triangles='+str(count)+' rays='+str(len(rays))+' hits='+str(hits)+' misses='+str(misses)+' exhaustive_distance_match=true')


if __name__=='__main__':main()
