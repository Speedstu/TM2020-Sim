"""Local JSON-lines interface to guarded original-code stepping and checkpoints.

No game process, injection, Openplanet, network, reward model or policy training.
An unknown branch fails the episode; reset/restore is required afterwards.
"""
import argparse
import json
from pathlib import Path
import sys

from owned_step_machine import open_owned_machine, UncapturedStepError


def serve(args):
    machine = open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32,args.max_steps,
                                 native_guard=getattr(args,"native_guard",None),
                                 initialize_writes=getattr(args,"initialize_writes",False))
    checkpoints = {}
    def reject_nonfinite_json(value):
        raise ValueError("Nonfinite JSON number is not permitted: "+value)
    for line in sys.stdin:
        request_id = None
        try:
            if len(line)>65536:
                raise ValueError("Request size bound exceeded")
            request = json.loads(line,parse_constant=reject_nonfinite_json)
            if not isinstance(request,dict):
                raise ValueError("Expected a JSON object")
            request_id=request.get("id")
            op=request.get("op")
            if op=="reset":
                result=machine.reset()
            elif op=="step":
                if "controls" not in request:
                    raise ValueError("Step requires controls: [drive,brake,steering]")
                if not isinstance(request["controls"],list):
                    raise ValueError("Step controls require a JSON array")
                machine.step(request["controls"])
                result=machine.observation()
            elif op=="save":
                name=request.get("name")
                if not isinstance(name,str) or not 1<=len(name)<=64:
                    raise ValueError("Checkpoint name requires 1..64 characters")
                if name not in checkpoints and len(checkpoints)>=16:
                    raise ValueError("Checkpoint count bound reached")
                checkpoints[name]=machine.save()
                result=dict(saved=name,tick=machine.frame)
            elif op=="restore":
                name=request.get("name")
                if not isinstance(name,str) or name not in checkpoints:
                    raise ValueError("Unknown checkpoint")
                result=machine.restore(checkpoints[name])
            elif op=="drop":
                name=request.get("name")
                if not isinstance(name,str) or name not in checkpoints:
                    raise ValueError("Unknown checkpoint")
                del checkpoints[name]
                result=dict(dropped=name)
            elif op=="close":
                print(json.dumps(dict(id=request_id,ok=True,result=dict(closed=True))),flush=True)
                return
            else:
                raise ValueError("Unknown operation")
            reply=dict(id=request_id,ok=True,result=result)
        except (ValueError,KeyError,TypeError,UncapturedStepError) as exc:
            reply=dict(id=request_id,ok=False,error=str(exc),resetOrRestoreRequired=machine.failed)
        print(json.dumps(reply,allow_nan=False,separators=(",",":")),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    parser.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    parser.add_argument("--max-steps",type=int)
    parser.add_argument("--native-guard",type=Path)
    parser.add_argument("--initialize-writes",action="store_true")
    serve(parser.parse_args())
