#!/usr/bin/env python3
"""Generate a game-build and PID-bound, UNVERIFIED live pose candidate manifest.

Sources are the four read-only movement snapshots corroborated by GBX geometry.
Addresses are ABSOLUTE, valid only for the current live process. This tool
never promotes candidates into stable vehicle struct offsets.
"""
import hashlib
import json
import ctypes
from ctypes import wintypes
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/"local/recon"
SOURCE=D/"map-corroborated-pose-clusters.json"
OUT=D/"session-pose-candidates-v3.txt"
GAME=Path(r"D:\SteamLibrary\steamapps\common\Trackmania\Trackmania.exe")

def process_creation_filetime(pid:int)->int:
    PROCESS_QUERY_LIMITED_INFORMATION=0x1000
    class FILETIME(ctypes.Structure):
        _fields_=[("low",wintypes.DWORD),("high",wintypes.DWORD)]
    k=ctypes.WinDLL("kernel32",use_last_error=True)
    k.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
    k.OpenProcess.restype=wintypes.HANDLE
    k.GetProcessTimes.argtypes=(wintypes.HANDLE,ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME),
                                ctypes.POINTER(FILETIME),ctypes.POINTER(FILETIME))
    k.GetProcessTimes.restype=wintypes.BOOL
    k.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=k.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,False,pid)
    if not handle:raise OSError(ctypes.get_last_error(),"Cannot read game process creation time")
    try:
        a,b,c,d=FILETIME(),FILETIME(),FILETIME(),FILETIME()
        if not k.GetProcessTimes(handle,ctypes.byref(a),ctypes.byref(b),ctypes.byref(c),ctypes.byref(d)):
            raise OSError(ctypes.get_last_error(),"GetProcessTimes failed")
        return a.low+(a.high<<32)
    finally:k.CloseHandle(handle)

def main():
    d=json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    ranked=d["rankedCandidates"]
    # Require independently authored GBX start-block agreement and multiple
    # copies on different memory pages.
    acceptable=[g for g in ranked
        if g["startHorizontalErrorM"]<1.
        and g["endNearestBlockCenterDistanceM"]<25.
        and g["distinct4KPages"]>=4
        and len(g["addressesInCurrentProcess"])>=4]
    if not acceptable:raise SystemExit("No sufficiently corroborated pose candidate")
    best=min(acceptable,key=lambda g:(g["startHorizontalErrorM"],-g["distinct4KPages"]))
    distinct=[]
    pages=set()
    for addr in best["addressesInCurrentProcess"]:
        a=int(addr,16)
        if a//4096 in pages:continue
        pages.add(a//4096)
        distinct.append(a)
    if len(distinct)<4:raise SystemExit("Not enough independent memory copies")
    h=hashlib.sha256(GAME.read_bytes()).hexdigest()
    # Native C++ reader verifies SHA+process identity before touching a byte.
    lines=[
        "TM2020_POSE_CANDIDATES_V3",
        str(d["gamePid"]),
        str(process_creation_filetime(d["gamePid"])), 
        h,
        "XYZ_CANDIDATE_ONLY",
        str(d["startBlockCenterXZ"][0]),
        str(d["startBlockCenterXZ"][1]),
        str(len(distinct)),
        *(hex(a) for a in distinct),
    ]
    OUT.write_text("\n".join(lines)+"\n",encoding="ascii")
    summary={
        "schema":"tm2020_pose_manifest_provenance_v3",
        "manifest":str(OUT),
        "gamePid":d["gamePid"],
        "processCreationFiletime":process_creation_filetime(d["gamePid"]),
        "exeSHA256":h,
        "mapUid":d["mapUid"],
        "referenceStartXZ":d["startBlockCenterXZ"],
        "candidateBeforeXYZ":best["beforeXYZ"],
        "candidateAfterXYZ":best["afterXYZ"],
        "candidateAddresses":len(distinct),
        "candidateCopies":best["supportingTriplets"],
        "gamePhysicalStateConfirmed":False,
        "100HzInternalPhysicsConfirmed":False,
        "stableAcrossProcessRestart":False,
        "warning":"Absolute addresses depend on this PID. XYZ order corrected. Candidate replicas may be rendering/camera transforms."
    }
    (D/"pose-manifest-provenance-v3.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print("PASS v3 MANIFEST",len(distinct),"copies","pid",d["gamePid"],
          "startError",best["startHorizontalErrorM"],"file",OUT)
if __name__=="__main__":main()
