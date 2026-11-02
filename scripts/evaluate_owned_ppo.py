"""Deterministic, no-update evaluation of native PPO in the guarded owned scene."""
import argparse
import hashlib
import json
from pathlib import Path

from force_worker_fixture import require
from owned_step_machine import open_owned_machine,UncapturedStepError
from owned_ppo import OwnedPolicy
from train_owned_scene import schema_for_fixture,encode


def main(args):
    training=json.loads((args.run/"report.json").read_text())
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32,
        max_steps=training["horizon"],native_guard=args.native_guard,
        initialize_writes=training.get("writeInitializationTracked",False))
    require(training["fixtureSha256"]==machine.fixture.sha256,"Evaluation fixture differs")
    origin=machine.observation()["position"];axis=training["reward"]["axis"];repeat=training["actionRepeat"]
    names=[("before",args.run/"update-0000"/"behavior.tmppo",None),
           ("after",args.run/f"update-{len(training['updates'])-1:04d}"/"updated.tmppo",None),
           ("neutral",None,[0,0,0]),("full_throttle",None,[1,0,0])]
    rows=[]
    for name,model,fixed in names:
        policy=OwnedPolicy(args.policy_dll,model,schema_for_fixture(machine.metadata)) if model else None
        runs=[]
        try:
            for trial in range(2):
                machine.reset();trace=hashlib.sha256();score=0.0;observation=machine.observation();error=None
                for _ in range(training["horizon"]//repeat):
                    controls=fixed
                    if policy:
                        a,_=policy.predict(encode(observation,origin));controls=[(a[0]+1)/2,(a[1]+1)/2,a[2]]
                    before=observation
                    try:
                        for _ in range(repeat):trace.update(machine.step(controls))
                        observation=machine.observation()
                    except UncapturedStepError as exc:error=str(exc);break
                    score+=sum((a-b)*v for a,b,v in zip(observation["position"],before["position"],axis))
                runs.append(dict(acceptedFrames=machine.frame,completed=error is None,
                    acceptedReward=score,traceSha256=trace.hexdigest(),lastAcceptedObservation=observation,error=error))
            require(runs[0]==runs[1],"Deterministic evaluation changed across reset")
        finally:
            if policy:policy.close()
        rows.append(dict(name=name,modelSha256=hashlib.sha256(model.read_bytes()).hexdigest() if model else None,
            repeatTrials=2,bitExactAcrossResets=True,**runs[0]))
    result=dict(schema="tm2020_owned_ppo_deterministic_evaluation_v1",fixtureSha256=machine.fixture.sha256,
        trainingReportSha256=hashlib.sha256((args.run/"report.json").read_bytes()).hexdigest(),
        policies=rows,trainingUpdatesPerformed=False,allTrialsCompleted=all(r["completed"] for r in rows),
        beforeAfterRewardChange=rows[1]["acceptedReward"]-rows[0]["acceptedReward"],
        independentMapEvaluation=False,fullSimulatorQualified=False,generalRlQualified=False,
        raceStrengthQualified=False,sourceGameProcessAccessed=False)
    args.report.write_text(json.dumps(result,indent=2)+"\n")
    print("OWNED_PPO_EVALUATION",[(r["name"],r["acceptedReward"],r["completed"]) for r in rows])


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("run","fixture","exe","native-guard","policy-dll","report"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    p.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    main(p.parse_args())
