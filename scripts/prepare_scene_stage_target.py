"""Write a PID/creation/build/scene-bound target for the stage-observer debugger."""
import argparse
import json
from pathlib import Path
from force_worker_fixture import require
from pinned_build import SHA


def main(args):
    b=json.loads(args.binding.read_text());registry=b["sceneRegistryDiscovery"]
    require(b["executableSha256"]==SHA and b["readOnly"] and registry["serviceGetterInstructionsVerified"],
            "Unverified scene registry discovery")
    require(len(registry["sceneRoots"])==1,"A unique source scene is required")
    root=registry["sceneRoots"][0];index=root["bindingIndex"];candidate=b["candidates"][index]
    require(candidate["typedBacklinksRechecked"] and registry["atomicSnapshot"] is False,"Unexpected source qualification")
    # Collision/force service addresses must be read again by the stopped observer;
    # the target text only carries current typed discovery identities.
    import ctypes as C
    k=C.WinDLL("kernel32",use_last_error=True)
    k.OpenProcess.argtypes=[C.c_uint32,C.c_int,C.c_uint32];k.OpenProcess.restype=C.c_void_p
    k.ReadProcessMemory.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]
    k.CloseHandle.argtypes=[C.c_void_p]
    p=k.OpenProcess(0x1010,False,b["pid"]);require(p,"Cannot read scene source")
    def word(address):
        value=C.c_uint64();got=C.c_size_t()
        require(k.ReadProcessMemory(p,C.c_void_p(address),C.byref(value),8,C.byref(got)) and got.value==8,
                "Unreadable source service")
        return value.value
    try:
        context=int(root["registry"],0)
        slots=[registry[n] for n in ("dynaSlot","collisionSlot","vehicleSlot")]
        values=[word(context+16+slot*8) for slot in slots]
        require(values[0]==int(candidate["manager"],0) and word(int(root["address"],0)+0x7c8)==context,
                "Scene discovery changed")
        lines=["TM2020_SCENE_STAGE_TARGET_V1",str(b["pid"]),b["processCreationFiletime"],SHA,
               b["moduleBase"],root["address"],root["registry"],*[hex(v) for v in values],*[str(v) for v in slots]]
        require(not args.output.exists(),"Scene target never overwrites a retained file")
        args.output.write_text("\n".join(lines)+"\n")
    finally:k.CloseHandle(p)
    print("SAVED CURRENT SCENE STAGE TARGET",args.output)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    main(parser.parse_args())
