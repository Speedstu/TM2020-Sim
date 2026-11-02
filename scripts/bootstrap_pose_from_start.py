#!/usr/bin/env python3
"""Read-only automatic start-grid bootstrap of Pose V3 candidate addresses.

Requires an independently inspected Solo Trackmania map and a bounded
TMVEC numeric-only memory capture. Group same-XYZ numeric copies around the
GBX RoadTechStart center, sample unit-quaternion-like fields before XYZ,
then issue PID+creation+SHA pinned temporary manifest. Does not assert
ownership by physical vehicle, physics engine fidelity, or permanent offsets.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import struct
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
GBX=ROOT/"local/campaign-2026-autumn/Autumn-2026-01.Map.json"
GAME=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
DT=np.dtype([("address","<u8"),("xyz","<f4",(3,))])
HEAD="<8sIIQQQ"

class FT(ctypes.Structure):
    _fields_=[("lo",wintypes.DWORD),("hi",wintypes.DWORD)]

def calculate(snapshot:Path, output:Path):
    m=json.loads(GBX.read_text(encoding="utf-8-sig"))
    start=[b for b in m["blocks"] if b["name"]=="RoadTechStart"]
    if len(start)!=1:raise ValueError("Map must have exactly one RoadTechStart")
    expected=(start[0]["grid"][0]*32+16,start[0]["grid"][2]*32+16)
    with snapshot.open("rb") as f:head=f.read(struct.calcsize(HEAD))
    if len(head)!=struct.calcsize(HEAD):
        raise ValueError("Missing snapshot header")
    magic,version,size,pid,scanned,count=struct.unpack(HEAD,head)
    if (magic!=b"TMVEC1\0\0" or version!=1 or size!=DT.itemsize
        or count>1_000_000 or snapshot.stat().st_size!=len(head)+count*size):
        raise ValueError("Invalid numeric-only snapshot format")
    rows=np.memmap(snapshot,dtype=DT,offset=len(head),shape=(count,),mode="r")
    xy=rows["xyz"]
    near=(np.abs(xy[:,0]-expected[0])<=0.75)&(
        np.abs(xy[:,2]-expected[1])<=0.75)&(
        (xy[:,1]>=20)&(xy[:,1]<=50))
    indices=np.nonzero(near)[0]
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    k.OpenProcess.restype=wintypes.HANDLE
    k.GetProcessId.argtypes=[wintypes.HANDLE]
    k.GetProcessId.restype=wintypes.DWORD
    k.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(FT)]*4)]
    k.GetProcessTimes.restype=wintypes.BOOL
    k.ReadProcessMemory.argtypes=[wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    k.ReadProcessMemory.restype=wintypes.BOOL
    k.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=k.OpenProcess(0x1010,False,pid)
    if not handle:raise OSError(ctypes.get_last_error(),"Game process cannot be inspected read-only")
    try:
        if k.GetProcessId(handle)!=pid:raise RuntimeError("PID resolved to a different process")
        creation,exited,user,kernel=FT(),FT(),FT(),FT()
        if not k.GetProcessTimes(handle,ctypes.byref(creation),ctypes.byref(exited),
                                 ctypes.byref(user),ctypes.byref(kernel)):
            raise OSError(ctypes.get_last_error(),"Cannot pin game creation time")
        created=creation.lo+(creation.hi<<32)
        groups={}
        for index in indices:
            address=int(rows["address"][index])
            buff=ctypes.create_string_buffer(28)
            countRead=ctypes.c_size_t()
            if not k.ReadProcessMemory(handle,ctypes.c_void_p(address-16),buff,28,ctypes.byref(countRead)):
                continue
            if countRead.value!=28:continue
            values=struct.unpack("<7f",buff.raw)
            xyz=values[4:]
            original=rows["xyz"][index]
            if max(abs(float(x)-float(y)) for x,y in zip(xyz,original))>0.015:
                continue
            q=values[:4]
            norm=sum(float(a)*a for a in q)
            if abs(norm-1)>0.003:continue
            # Double cover: q and -q encode equivalent rotations, but do NOT
            # use that fact as proof that these fields are car orientation.
            q=list(q)
            pivot=max(range(4),key=lambda j:abs(q[j]))
            if q[pivot]<0:q=[-v for v in q]
            key=(tuple(round(float(x),2) for x in xyz),
                 tuple(round(float(a),2) for a in q))
            groups.setdefault(key,[]).append(address)
    finally:k.CloseHandle(handle)
    ranked=[]
    for key,addresses in groups.items():
        distinct={}
        for addr in addresses:distinct.setdefault(addr//4096,addr)
        if len(distinct)<4:continue
        xyz,q=key
        err=((xyz[0]-expected[0])**2+(xyz[2]-expected[1])**2)**0.5
        ranked.append((err,len(distinct),list(distinct.values())[:16],xyz,q,len(addresses)))
    if not ranked:raise RuntimeError("No convincing multi-page start-grid numeric candidate group")
    # Prefer minimum horizontal error, then support, and finally proximity
    # to previously observed car start height, but never accept it as proof.
    ranked.sort(key=lambda g:(g[0],-g[1],abs(g[3][1]-34)))
    best=ranked[0]
    sha=hashlib.sha256(GAME.read_bytes()).hexdigest()
    addresses=best[2]
    out=[
        "TM2020_POSE_CANDIDATES_V3",str(pid),str(created),sha,
        "XYZ_CANDIDATE_ONLY",str(expected[0]),str(expected[1]),str(len(addresses)),
        *[hex(a) for a in addresses],
    ]
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text("\n".join(out)+"\n",encoding="ascii")
    report={
        "schema":"tm2020_offline_map_start_numeric_bootstrap_v1",
        "mapUid":m["uid"],
        "pid":pid,
        "sourceSnapshot":str(snapshot),
        "selectedAddresses":len(addresses),
        "independentPages":best[1],
        "samplesAtSelectedPose":best[5],
        "selectedPoseXYZ":best[3],
        "selectedQuatCandidate":best[4],
        "horizontalDistanceToAuthoredStartM":best[0],
        "candidateGroupCount":len(ranked),
        "confirmedVehicleOwner":False,
        "confirmedAuthoritativePhysicsState":False,
        "verifiedAcrossProcessRestarts":False,
        "runtimeNoInjection":True,
        "note":"Start-grid spatial + quaternion correlation only; dynamic car owner must still be confirmed through movement/reset."
    }
    reportPath=output.with_suffix(".research.json")
    reportPath.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("PASS AUTO_BOOTSTRAP_PID",pid,"xyz",best[3],"q",best[4],
          "copies",len(addresses),"pages",best[1],
          "startHorizontalError",round(best[0],4),"verifiedCarOwner",False)
    print("MANIFEST",output)
    return report

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--snapshot",required=True,type=Path)
    a.add_argument("--output",required=True,type=Path)
    options=a.parse_args()
    calculate(options.snapshot,options.output)
if __name__=="__main__":main()
