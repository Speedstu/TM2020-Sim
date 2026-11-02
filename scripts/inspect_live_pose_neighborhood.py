#!/usr/bin/env python3
"""Read-only scalar neighborhood analysis of 9 independent Trackmania pose copies.

Do not read/process/store raw arbitrary game process page dumps. Sample only
bounded floats around previously GBX-corroborated numeric candidate addresses,
aggregate consensus, save summary JSON. Suspected quaternion/rotation fields
are still UNKNOWN until behavior during turns validates semantics.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
MAN=ROOT/"local/recon/session-pose-candidates-v3.txt"
OUT=ROOT/"local/recon/pose-neighborhood-numeric-consensus.json"
EXPECTED_GAME=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")
BEFORE=128
AFTER=192
TOTAL=BEFORE+AFTER+12

class FT(ctypes.Structure):
    _fields_=[("lo",wintypes.DWORD),("hi",wintypes.DWORD)]

def main():
    lines=MAN.read_text(encoding="ascii").splitlines()
    if lines[0]!="TM2020_POSE_CANDIDATES_V3" or lines[4]!="XYZ_CANDIDATE_ONLY":
        raise ValueError("Unsupported pose candidate schema")
    pid=int(lines[1]);started=int(lines[2]);sha=lines[3]
    assert len(sha)==64 and len(lines[8:])==int(lines[7])>=4
    if hashlib.sha256(EXPECTED_GAME.read_bytes()).hexdigest()!=sha:
        raise RuntimeError("Unexpected game binary version")
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
    handle=k.OpenProcess(0x1000|0x0010,False,pid)
    if not handle:raise OSError(ctypes.get_last_error(),"OpenProcess read-only refused")
    try:
        if k.GetProcessId(handle)!=pid:
            raise RuntimeError("Windows opened a nonmatching canonical PID")
        a,b,c,d=FT(),FT(),FT(),FT()
        if not k.GetProcessTimes(handle,ctypes.byref(a),ctypes.byref(b),ctypes.byref(c),ctypes.byref(d)):
            raise OSError(ctypes.get_last_error(),"GetProcessTimes")
        if a.lo+(a.hi<<32)!=started:
            raise RuntimeError("Game process restarted after old samples")
        addr=[int(x,16) for x in lines[8:]]
        arrays=[]
        for pos in addr:
            buf=ctypes.create_string_buffer(TOTAL)
            got=ctypes.c_size_t()
            if not k.ReadProcessMemory(handle,ctypes.c_void_p(pos-BEFORE),buf,TOTAL,ctypes.byref(got)):
                continue
            if got.value!=TOTAL:continue
            arrays.append([struct.unpack_from("<f",buf,offset)[0] for offset in range(0,TOTAL,4)])
        if len(arrays)<4:raise RuntimeError("Not enough full-neighborhood read-only memory replicas")
    finally:
        k.CloseHandle(handle)
    def median(x):
        x=sorted(x)
        return x[len(x)//2]
    entries=[]
    consensus=0
    for col in range(TOTAL//4):
        vals=[a[col] for a in arrays]
        if not all(math.isfinite(x) and abs(x)<1e7 for x in vals):
            continue
        med=median(vals)
        deviation=max(abs(v-med) for v in vals)
        agrees=sum(abs(v-med)<=0.002 for v in vals)
        if agrees>=len(vals)//2+1:
            consensus+=1
        entries.append({
            "relativeByteOffset":col*4-BEFORE,
            "numericMedian":round(med,6),
            "maxDifference":round(deviation,5),
            "matchingCopies":agrees,
            "possibleUnitLengthRotationComponent": abs(med)<=1.0,
        })
    # Field semantics must be inferred independently from controlled turning.
    report={
        "schema":"tm2020_numeric_neighborhood_correlated_copies_v1",
        "gamePid":pid,"copyAddressesRead":len(arrays),
        "offsetWindowBytes":[-BEFORE,AFTER+12],
        "matchingFloatColumns":consensus,
        "coordinateColumnsCheckedAtOffsets":[0,4,8],
        "positionXYZSemanticsCorroboratedByGBX":True,
        "quaternionFieldSemanticsVerified":False,
        "velocityFieldSemanticsVerified":False,
        "physicalCarOwnerIdentified":False,
        "readOnly":True,
        "numericColumns":entries,
    }
    OUT.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("PASS READ_ONLY_NEIGHBORHOOD pid",pid,"copies",len(arrays),
          "floatColumns",len(entries),"majorityConsensus",consensus,
          "verifiedQuat=false verifiedVelocity=false")
    for x in entries:
        if -40<=x["relativeByteOffset"]<=64 and x["matchingCopies"]>=len(arrays)//2+1:
            print("OFFSET",x["relativeByteOffset"],"value",x["numericMedian"],
                  "copies",x["matchingCopies"],"maxDelta",x["maxDifference"])
    print("SAVED",OUT)
if __name__=="__main__":
    main()
