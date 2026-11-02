"""Our native PPO SDK against cold, map-loaded physics through local IPC."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from force_worker_fixture import require
from headless_gym import TrackmaniaHeadlessEnv,ACTION_SCHEMA,encode
from headless_engine import OBSERVATIONS,UPSTREAM,EngineCommandError
from owned_ppo import OwnedPpo


def state_digest(state):
    value=dict(tick=state["tick"],trace=state["upstreamTraceState"],observation=encode(state).tolist(),
        finished=state["finished"],left=state["checkpointsLeft"])
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def main(args):
    require(not args.output.exists(),"Headless training never overwrites a run")
    require(1<=args.updates<=10000 and 1<=args.episodes<=1000 and 8<=args.hidden<=256,"Training bounds")
    require(1<=args.repeat<=100 and 1<=args.horizon<=100_000,"Episode bounds")
    args.output.mkdir(parents=True)
    trainer=OwnedPpo(args.policy_dll,OBSERVATIONS,3,ACTION_SCHEMA,args.seed,hidden=args.hidden)
    environments=[]
    report=dict(schema="tm2020_asset_loaded_ppo_v1",upstreamRevision=UPSTREAM,
        hostSha256=hashlib.sha256(args.host.read_bytes()).hexdigest(),
        policyDllSha256=hashlib.sha256(args.policy_dll.read_bytes()).hexdigest(),
        observationSchema=ACTION_SCHEMA,observations=OBSERVATIONS,actions=3,hidden=args.hidden,
        actionMapping="float32 tanh action; gas=(a0+1)/2; brake=(a1+1)/2; steer=a2",
        seed=args.seed,horizon=args.horizon,actionRepeat=args.repeat,
        reward="0.01*goal_distance_delta within unchanged checkpoint set +10/checkpoint +100/finish -0.0002/tick",
        rewardUsesEngineRaceTriggers=True,gameProcessAccessed=False,openplanetUsed=False,
        sparseSnapshotsRequired=False,configuredInitialDistributionNotLearned=args.resume is None,
        originalGameDifferentialPerformed=False,completeExactSimulatorQualified=False,
        generalPolicyQualified=False,raceStrengthQualified=False,maps=[],updates=[])
    started=time.perf_counter()
    try:
        if args.resume:initial=args.resume
        else:
            initial=args.output/"initial.checkpoint"
            result=subprocess.run([str(args.initializer.resolve()),str(OBSERVATIONS),"3",str(args.hidden),
                str(args.seed),ACTION_SCHEMA,str(initial.resolve())],capture_output=True,text=True,timeout=30)
            require(result.returncode==0,"Native initial distribution failed: "+result.stderr)
        trainer.file("resume",initial)
        report["initialCheckpointSha256"]=hashlib.sha256(initial.read_bytes()).hexdigest()
        for index,map_path in enumerate(args.maps):
            env=TrackmaniaHeadlessEnv(args.host,map_path,args.packs,args.output/f"map-{index:03d}",
                horizon=args.horizon,repeat=args.repeat,seed=(args.seed+index)%2**32)
            environments.append(env)
            report["maps"].append(dict(path=str(env.engine.map),sha256=env.engine.map_sha256,seed=env.engine.seed,
                assetBodyMass=env.engine.state["assetBodyMass"],gravity=env.engine.state["gravity"]))
        for update in range(args.updates):
            folder=args.output/f"update-{update:04d}";folder.mkdir()
            behavior=folder/"behavior.tmppo";trainer.file("export",behavior)
            decisions=[];episodes=[]
            for episode in range(args.episodes):
                map_index=(update*args.episodes+episode)%len(environments);env=environments[map_index]
                observation,_=env.reset();score=0.0;accepted=0;error=None
                while True:
                    before=env.engine.state;before_hash=state_digest(before)
                    action=trainer.sample(observation.tolist())
                    try:next_observation,reward,terminated,truncated,info=env.step(action)
                    except EngineCommandError as exc:
                        trainer.cancel();error=dict(message=str(exc),response=exc.response);break
                    trainer.observe(reward,next_observation.tolist(),truncated=truncated,terminated=terminated,
                        duration=info["advancedTicks"]/args.repeat)
                    decisions.append(dict(episode=episode,index=accepted,mapIndex=map_index,action=action,
                        controls=info["controls"],reward=reward,beforeDigest=before_hash,
                        afterDigest=state_digest(env.engine.state),beforeTick=before["tick"],
                        afterTick=env.engine.state["tick"],terminated=terminated,truncated=truncated))
                    score+=reward;accepted+=1;observation=next_observation
                    if terminated or truncated:break
                episodes.append(dict(episode=episode,mapIndex=map_index,acceptedDecisions=accepted,reward=score,
                    finished=env.engine.state["finished"],finishTimeMs=env.engine.state["finishTimeMs"],
                    checkpointsPassed=env.engine.state["checkpointsPassed"],ticks=env.engine.state["tick"],error=error))
            (folder/"decisions.json").write_text(json.dumps(decisions,separators=(",",":"))+"\n")
            row=dict(index=update,episodes=episodes,acceptedTransitions=len(decisions),
                behaviorSha256=hashlib.sha256(behavior.read_bytes()).hexdigest())
            if decisions:
                csv=folder/"rollout.csv";audit=folder/"behavior-audit.json";trainer.file("rollout_csv",csv)
                result=subprocess.run([str(args.auditor.resolve()),str(behavior),str(csv),str(audit),"--multiple-episodes"],
                    capture_output=True,text=True,timeout=60)
                require(result.returncode==0,"Independent native behavior audit failed: "+result.stderr)
                row["behaviorAudit"]=json.loads(audit.read_text());row["ppoMetrics"]=trainer.update()
            else:row["ppoMetrics"]=None
            trainer.file("checkpoint",folder/"training.checkpoint");trainer.file("export",folder/"updated.tmppo")
            row["updatedModelSha256"]=hashlib.sha256((folder/"updated.tmppo").read_bytes()).hexdigest()
            report["updates"].append(row);report["totalAcceptedTransitions"]=sum(r["acceptedTransitions"] for r in report["updates"])
            report["elapsedSeconds"]=time.perf_counter()-started
            (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
            print("HEADLESS_NATIVE_PPO",update,"decisions",len(decisions),"finishes",sum(e["finished"] for e in episodes),flush=True)
            require(decisions,"No valid transition; see explicit engine failure evidence")
    finally:
        for env in environments:env.close()
        trainer.close()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("host","packs","policy-dll","auditor","initializer","output"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--maps",type=Path,nargs="+",required=True);p.add_argument("--resume",type=Path)
    p.add_argument("--updates",type=int,default=4);p.add_argument("--episodes",type=int,default=4)
    p.add_argument("--horizon",type=int,default=2500);p.add_argument("--repeat",type=int,default=5)
    p.add_argument("--hidden",type=int,default=128);p.add_argument("--seed",type=int,default=2026)
    main(p.parse_args())
