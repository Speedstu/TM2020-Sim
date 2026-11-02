"""Replay accepted native PPO histories on fresh cold-loaded engine instances.

This checks collection integrity, not agreement with the original game.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from force_worker_fixture import require
from headless_gym import TrackmaniaHeadlessEnv,ACTION_SCHEMA,encode
from headless_engine import OBSERVATIONS
from owned_ppo import OwnedPolicy
from train_headless_ppo import state_digest


def main(args):
    require(not args.output.exists(),"Audit never overwrites evidence")
    args.output.mkdir(parents=True)
    source=args.run/"report.json";report=json.loads(source.read_text())
    require(report["hostSha256"]==hashlib.sha256(args.host.read_bytes()).hexdigest(),"Host changed")
    require(report["policyDllSha256"]==hashlib.sha256(args.policy_dll.read_bytes()).hexdigest(),"Policy SDK changed")
    require(report["observationSchema"]==ACTION_SCHEMA,"Unknown policy schema")
    envs=[];total=0;ticks=0;updates=[]
    try:
        for index,item in enumerate(report["maps"]):
            env=TrackmaniaHeadlessEnv(args.host,Path(item["path"]),args.packs,args.output/f"map-{index}",
                horizon=report["horizon"],repeat=report["actionRepeat"],seed=item["seed"])
            envs.append(env);require(env.engine.map_sha256==item["sha256"],"Map changed")
        for update in report["updates"]:
            folder=args.run/f"update-{update['index']:04d}"
            model=folder/"behavior.tmppo"
            require(hashlib.sha256(model.read_bytes()).hexdigest()==update["behaviorSha256"],"Behavior model changed")
            policy=OwnedPolicy(args.policy_dll,model,ACTION_SCHEMA,OBSERVATIONS,3)
            decisions=json.loads((folder/"decisions.json").read_text())
            with (folder/"rollout.csv").open() as stream:rows=list(csv.DictReader(stream))
            require(len(rows)==len(decisions)==update["acceptedTransitions"],"Rollout count mismatch")
            previous=None;max_bootstrap=0.0
            try:
                for row,decision in zip(rows,decisions):
                    env=envs[decision["mapIndex"]]
                    episode=(decision["episode"],decision["mapIndex"])
                    if episode!=previous:env.reset();previous=episode
                    before=env.engine.state
                    require(state_digest(before)==decision["beforeDigest"],"Replay pre-state differs")
                    require(encode(before).tolist()==[float(row[f"observation_{i}"]) for i in range(OBSERVATIONS)],
                        "PPO observation misaligned with physics")
                    action=[math.tanh(float(row[f"latent_{i}"])) for i in range(3)]
                    require(all(abs(a-b)<1e-14 for a,b in zip(action,decision["action"])),"Latent/action mismatch")
                    # Gym action quantization is intentional and must match the collector.
                    mapped=np.asarray(action,dtype=np.float32).astype(np.float64).tolist()
                    controls=[(mapped[0]+1)/2,(mapped[1]+1)/2,mapped[2]]
                    require(controls==decision["controls"],"Quantized controls differ")
                    obs,reward,terminated,truncated,info=env.step(action)
                    require(state_digest(env.engine.state)==decision["afterDigest"],"Replay successor differs")
                    require(reward==decision["reward"]==float(row["reward"]),"Reward mismatch")
                    require(terminated==decision["terminated"]==bool(int(row["terminated"]))
                        and truncated==decision["truncated"]==bool(int(row["truncated"])),"Boundary mismatch")
                    require(before["tick"]==decision["beforeTick"] and env.engine.state["tick"]==decision["afterTick"],"Clock mismatch")
                    require(float(row["elapsed_steps"])==info["advancedTicks"]/report["actionRepeat"],"Duration mismatch")
                    _,value=policy.predict(obs.tolist())
                    # The CSV retains the critic output; terminal masking occurs in native GAE.
                    error=abs(value-float(row["next_value"]))
                    max_bootstrap=max(max_bootstrap,error);require(error<1e-12,"Bootstrap mismatch")
                    total+=1;ticks+=info["advancedTicks"]
            finally:policy.close()
            updates.append(dict(index=update["index"],transitions=len(rows),maxBootstrapError=max_bootstrap,
                allStateDigestsExact=True,rewardsExact=True,quantizedActionsExact=True,boundariesExact=True))
        require(total==report["totalAcceptedTransitions"],"Total transitions differ")
    finally:
        for env in envs:env.close()
    result=dict(schema="tm2020_headless_ppo_physics_audit_v1",transitions=total,engineTicksReplayed=ticks,
        trainingReportSha256=hashlib.sha256(source.read_bytes()).hexdigest(),updates=updates,
        originalGameDifferentialPerformed=False,completeExactSimulatorQualified=False,generalPolicyQualified=False)
    (args.output/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print("PASS HEADLESS_PPO_PHYSICS_AUDIT",total,"transitions",ticks,"engine ticks")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("run","host","packs","policy-dll","output"):p.add_argument("--"+name,type=Path,required=True)
    main(p.parse_args())
