"""Compare native policies and fixed controls on training and held-out maps."""
import argparse
import hashlib
import json
from pathlib import Path

from force_worker_fixture import require
from headless_gym import TrackmaniaHeadlessEnv,ACTION_SCHEMA
from headless_engine import EngineCommandError,OBSERVATIONS
from owned_ppo import OwnedPolicy
from train_headless_ppo import state_digest


def main(args):
    require(not args.output.exists(),"Evaluation never overwrites evidence")
    args.output.mkdir(parents=True);source=args.run/"report.json";training=json.loads(source.read_text())
    require(hashlib.sha256(args.host.read_bytes()).hexdigest()==training["hostSha256"],"Evaluation engine differs")
    require(hashlib.sha256(args.policy_dll.read_bytes()).hexdigest()==training["policyDllSha256"],"Policy SDK differs")
    cases=[("before",args.run/"update-0000/behavior.tmppo",None),
        ("candidate" if args.candidate else "after",args.candidate or args.run/f"update-{len(training['updates'])-1:04d}/updated.tmppo",None),
        ("neutral",None,[-1,-1,0]),("full_throttle",None,[1,-1,0])]
    results=[]
    for index,map_path in enumerate(args.maps):
        env=TrackmaniaHeadlessEnv(args.host,map_path,args.packs,args.output/f"map-{index}",
            horizon=args.horizon,repeat=training["actionRepeat"],seed=args.seed)
        try:
            policies=[]
            for name,model,fixed in cases:
                policy=OwnedPolicy(args.policy_dll,model,ACTION_SCHEMA,OBSERVATIONS,3) if model else None
                runs=[]
                try:
                    for _ in range(2):
                        observation,_=env.reset();score=0.0;error=None;trace=hashlib.sha256()
                        while True:
                            action=policy.predict(observation.tolist())[0] if policy else fixed
                            try:observation,reward,terminated,truncated,_=env.step(action)
                            except EngineCommandError as exc:error=exc.response;break
                            score+=reward;trace.update(state_digest(env.engine.state).encode())
                            if terminated or truncated:break
                        state=env.engine.state
                        runs.append(dict(reward=score,ticks=state["tick"],finished=state["finished"],
                            finishTimeMs=state["finishTimeMs"],checkpointsPassed=state["checkpointsPassed"],
                            traceSha256=trace.hexdigest(),error=error,completed=error is None))
                    require(runs[0]==runs[1],"Evaluation changed across reset")
                finally:
                    if policy:policy.close()
                policies.append(dict(name=name,modelSha256=hashlib.sha256(model.read_bytes()).hexdigest() if model else None,
                    repeatTrials=2,deterministicReset=True,**runs[0]))
            results.append(dict(map=str(env.engine.map),mapSha256=env.engine.map_sha256,
                heldOut=env.engine.map_sha256 not in {m["sha256"] for m in training["maps"]},policies=policies))
            print("HEADLESS_EVALUATION",map_path.name,[(r["name"],r["finished"],round(r["reward"],3)) for r in policies],flush=True)
        finally:env.close()
    result=dict(schema="tm2020_headless_ppo_evaluation_v1",maps=results,horizon=args.horizon,seed=args.seed,
        trainingReportSha256=hashlib.sha256(source.read_bytes()).hexdigest(),trainingUpdatesPerformed=False,
        originalGameDifferentialPerformed=False,completeExactSimulatorQualified=False,generalPolicyQualified=False,
        raceStrengthQualified=False)
    (args.output/"report.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("run","host","packs","policy-dll","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--maps",type=Path,nargs="+",required=True)
    p.add_argument("--candidate",type=Path,help="Optional independently trained model to compare")
    p.add_argument("--horizon",type=int,default=5000);p.add_argument("--seed",type=int,default=2026)
    main(p.parse_args())
