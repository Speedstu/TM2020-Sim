"""Re-execute accepted PPO physics histories and independently verify rewards/bootstrap.

Behavior likelihoods are separately checked by tm2020_rollout_audit. This adds
original-code trajectory replay, action/observation alignment and successor value
checks. Unknown or canceled decisions must never appear among accepted rows.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

from force_worker_fixture import require
from owned_step_machine import open_owned_machine
from owned_ppo import OwnedPolicy
from train_owned_scene import schema_for_fixture,encode


def main(args):
    report=json.loads((args.run/"report.json").read_text())
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32,
        max_steps=report["horizon"],native_guard=args.native_guard,
        initialize_writes=report.get("writeInitializationTracked",False))
    require(report["fixtureSha256"]==machine.fixture.sha256,"Audit fixture differs")
    schema=schema_for_fixture(machine.metadata)
    require(report["observationSchema"]==schema,"Unknown audit observation/action schema")
    axis=report["reward"]["axis"];repeat=report["actionRepeat"]
    origin=machine.observation()["position"]
    total=0;steps=0;updates=[]
    for update in report["updates"]:
        if not update["acceptedTransitions"]:continue
        folder=args.run/f"update-{update['index']:04d}"
        policy=OwnedPolicy(args.policy_dll,folder/"behavior.tmppo",schema)
        decisions=json.loads((folder/"physics-decisions.json").read_text())
        with (folder/"rollout.csv").open() as f:rows=list(csv.DictReader(f))
        require(len(rows)==len(decisions)==update["acceptedTransitions"],"Accepted row count differs")
        previous_episode=None;maximum_bootstrap_error=0.0
        try:
            for index,(row,decision) in enumerate(zip(rows,decisions)):
                if decision["episode"]!=previous_episode:
                    machine.reset();previous_episode=decision["episode"]
                require(machine.observation()==decision["before"],"Before observation differs on original-code replay")
                obs=encode(decision["before"],origin)
                require(obs==[float(row[f"observation_{i}"]) for i in range(13)],"PPO observation is misaligned")
                a=[math.tanh(float(row[f"latent_{i}"])) for i in range(3)]
                controls=[(a[0]+1)/2,(a[1]+1)/2,a[2]]
                require(all(abs(a-b)<1e-14 for a,b in zip(controls,decision["controls"])),"Retained action differs from native policy sample")
                digest=hashlib.sha256()
                for _ in range(repeat):digest.update(machine.step(decision["controls"]));steps+=1
                require(machine.observation()==decision["after"] and digest.hexdigest()==decision["traceSha256"],
                        "PPO trajectory differs on original-code replay")
                reward=sum((a-b)*v for a,b,v in zip(decision["after"]["position"],decision["before"]["position"],axis))
                require(reward==decision["reward"]==float(row["reward"]),"PPO reward differs from accepted displacement")
                _,bootstrap=policy.predict(encode(decision["after"],origin))
                error=abs(bootstrap-float(row["next_value"]))
                maximum_bootstrap_error=max(maximum_bootstrap_error,error)
                require(error<1e-12,"Bootstrap uses another observation/policy")
                boundary=index+1==len(decisions) or decisions[index+1]["episode"]!=decision["episode"]
                require(float(row["truncated"])==int(boundary) and float(row["terminated"])==0
                        and float(row["elapsed_steps"])==1,"PPO truncation/duration differs")
                total+=1
        finally:policy.close()
        updates.append(dict(index=update["index"],transitions=len(rows),allPhysicsDecisionsReplayed=True,
            bootstrapMaximumError=maximum_bootstrap_error,rewardsExact=True,allEpisodeBoundariesExact=True))
    require(total==report["totalAcceptedTransitions"],"Training total differs")
    result=dict(schema="tm2020_owned_ppo_physics_audit_v1",trainingReportSha256=hashlib.sha256((args.run/"report.json").read_bytes()).hexdigest(),
        nativeGuardDllSha256=hashlib.sha256(args.native_guard.read_bytes()).hexdigest(),
        collectorNativeGuardDllSha256=report["nativeGuardDllSha256"],
        policyDllSha256=hashlib.sha256(args.policy_dll.read_bytes()).hexdigest(),
        fixtureSha256=machine.fixture.sha256,transitions=total,originalPhysicsStepsReplayed=steps,updates=updates,
        originalGameCodeUnchanged=True,sourceGameProcessAccessed=False,
        fullSimulatorQualified=False,generalRlQualified=False)
    args.report.write_text(json.dumps(result,indent=2)+"\n")
    print("PASS OWNED_PPO_PHYSICS_AUDIT transitions="+str(total)+" original_steps="+str(steps))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("run","fixture","exe","native-guard","policy-dll","report"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    p.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    main(p.parse_args())
