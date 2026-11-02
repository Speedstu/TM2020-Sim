"""Fail closed on retained geometry/cache, native replay and name-table evidence."""
import hashlib
import json
from pathlib import Path
import struct
from reverse_physics import ROOT,SHA


def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()


def main():
    source=ROOT/'local/recon/live-geometry-26616-v2'
    summary=json.loads((source/'summary.json').read_text())
    entries=[json.loads(x) for x in (source/'meshes.jsonl').read_text().splitlines()]
    if summary['meshes']!=len(entries) or len(entries)!=351 or summary['exactCookers']!=351 or summary['exactTreeRebuilds']!=351:raise ValueError('Live prototype qualification differs')
    for row in entries:
        p=source/f"mesh-{row['cacheIndex']}.tmmesh"
        if digest(p)!=row['sha256'] or not row['cookerDefinedBytesExact'] or not row['treeRebuildBitExact']:raise ValueError('Mesh prototype checksum differs')
        with p.open('rb') as f:magic,nv,nt,nn=struct.unpack('<4I',f.read(16))
        if magic!=0x314d5254 or p.stat().st_size!=16+nv*12+nt*32+nn*28:raise ValueError('Malformed prototype file')
    cache=ROOT/'local/collision-maps/ypPmohQofd72MyTsIsijKfrJH98-live-meshes.tmcol';meta=json.loads(cache.with_suffix('.json').read_text())
    if meta['sha256']!=SHA or meta['triangles']!=795089 or meta['uniqueGeometryPlacements']!=6805 or meta['completeMapCollisionVerified']:raise ValueError('Unexpected placement/cache inventory')
    if digest(cache)!=meta['cacheSha256'] or digest(cache.with_suffix('.surfaces'))!=meta['surfaceIdsSha256']:raise ValueError('Ray cache checksum differs')
    native=json.loads((ROOT/'local/recon/captured-collision-replay-26616.json').read_text())
    if native['triangles']!=meta['triangles'] or native['groundContactStates']!=400 or native['groundContactRayHits']!=400 or native['groundContactMaterialMatches']!=399 or native['startSurfaceId']!=16 or abs(native['startFloorY']-34)>1e-4 or not native['materialComparisonUsesIndependentPhysicalNameTable']:raise ValueError('Native replay-ray evidence differs')
    if native['gameRequiredAtRuntime'] or native['pythonRequiredAtRuntime'] or native['completeMapCollisionVerified']:raise ValueError('Unexpected runtime/scope claim')
    bvh=json.loads((ROOT/'local/recon/captured-ray-audit/qualification.json').read_text())
    if bvh['rays']!=256 or bvh['triangles']!=meta['triangles'] or not bvh['independentExhaustivePlaneAndBarycentricChecks'] or bvh['maximumDistanceError']>1e-7 or not bvh['hits'] or not bvh['misses']:raise ValueError('Independent exhaustive BVH differential failed')
    names=json.loads((ROOT/'local/recon/surface-material-names.json').read_text())
    if names['sha256']!=SHA or names['count']!=80 or names['sdkHeaderSha256']!=digest(ROOT/'native/include/tm2020/surface_materials.hpp'):raise ValueError('Stale physical surface names')
    paths=['native/src/live_mesh_read.hpp','native/src/live_mesh_inventory.cpp','native/src/live_mesh_capture.cpp','native/src/collision_replay_audit.cpp','scripts/build_live_collision_cache.py']
    report={'schema':'tm2020_captured_geometry_qualification_v1','sha256':SHA,'prototypeMeshes':351,'prototypeTriangles':348332,
        'prototypeCookersBitExact':True,'prototypeTreesBitExact':True,'uniqueGeometryPlacements':6805,'rayCacheTriangles':795089,
        'groundedReplayStates':400,'groundedReplayHits':400,'mappedGroundMaterialMatches':399,'materialMismatchAtReplayInitializationRetained':True,
        'independentExhaustiveBvhRays':256,'maximumBvhDistanceError':bvh['maximumDistanceError'],
        'currentSourceHashes':{p:digest(ROOT/p) for p in paths},'cacheSha256':digest(cache),
        'gameRequiredByRayCacheRuntime':False,'pythonRequiredByRayCacheRuntime':False,
        'allWorldPlacementsVerified':False,'allNativeShapeTypesCaptured':False,'completeMapCollisionVerified':False,'completeVehiclePhysics':False}
    (ROOT/'local/recon/captured-geometry-qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS CAPTURED_GEOMETRY meshes=351 exact_cookers_and_trees=true rays=400 grounded_hits=400 material_matches=399 full_map_qualified=false')


if __name__=='__main__':main()
