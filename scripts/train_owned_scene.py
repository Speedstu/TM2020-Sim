"""Bounded PPO experiment using guarded ORIGINAL vehicle/scene code and our SDK.

Task: forward displacement along an explicit world axis over a short horizon.
This is not a race reward, a map-general bot, or proof of full physics fidelity.
Uncaptured actions are discarded, accepted prefixes retain proper truncation.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time

from force_worker_fixture import require
from owned_step_machine import open_owned_machine,UncapturedStepError
from owned_ppo import OwnedPpo

SCHEMA="tm2020_owned_relative_xyz100_quat_wxyz_velocity100_angular10_v1"


def schema_for_fixture(metadata):
    return SCHEMA+("|actions=scene_input_decoder_type2_v1" if metadata.get("outerSceneStage") else "")


def encode(observation,origin):
    return [(v-o)/100 for v,o in zip(observation["position"],origin)]+observation["quaternionWxyz"]+[
        v/100 for v in observation["linearVelocity"]]+[v/10 for v in observation["angularVelocity"]]


def main(args):
    require(1<=args.updates<=10000 and 1<=args.episodes<=1000,"Training iteration bound")
    require(1<=args.horizon<=1000 and 1<=args.repeat<=100 and args.horizon%args.repeat==0,
            "Horizon must be divisible by action repeat")
    axis=args.forward_axis
    require(all(math.isfinite(v) for v in axis) and abs(sum(v*v for v in axis)-1)<1e-6,
            "Forward axis must be an explicit unit vector")
    require(not args.output.exists(),"Training output never overwrites an existing run")
    machine=open_owned_machine(args.fixture,args.exe,args.ntdll,args.kernel32,
        max_steps=args.horizon,native_guard=args.native_guard,initialize_writes=args.initialize_writes)
    outer=machine.metadata.get("outerSceneStage") is not None
    require((outer or machine.metadata.get("sourceBodyActivationRestored") is True) and
            machine.metadata.get("sourceVelocityPreserved") is True,
            "Training experiment requires preserved source vehicle dynamics")
    args.output.mkdir(parents=True)
    schema=schema_for_fixture(machine.metadata)
    trainer=OwnedPpo(args.policy_dll,13,3,schema,args.seed)
    if args.resume:trainer.file("resume",args.resume)
    origin=machine.observation()["position"]
    report=dict(schema="tm2020_guarded_owned_scene_ppo_v1",fixtureSha256=machine.fixture.sha256,
        executableSha256=machine.metadata["modules"][0]["sha256"],observationSchema=schema,
        physicsEntryRva=machine.metadata["entryRva"],originalOuterSceneProcedureUsed=outer,
        inputBoundaryRva="0x12bce40" if outer else None,liveActionOracleQualified=False,
        observations=13,actions=3,actionMapping="drive=(a0+1)/2; brake=(a1+1)/2; steering=a2",
        writeInitializationTracked=args.initialize_writes,
        reward=dict(type="explicit_world_axis_displacement",axis=axis,scale=1.0,
                    raceReward=False),horizon=args.horizon,actionRepeat=args.repeat,seed=args.seed,
        resumeCheckpointSha256=hashlib.sha256(args.resume.read_bytes()).hexdigest() if args.resume else None,
        policyDllSha256=hashlib.sha256(args.policy_dll.read_bytes()).hexdigest(),
        nativeGuardDllSha256=hashlib.sha256(args.native_guard.read_bytes()).hexdigest(),
        sourceGameProcessAccessed=False,openplanetUsed=False,originalGameInstructionsModified=False,
        unknownStepsDiscarded=True,fullSimulatorQualified=False,generalRlQualified=False,
        racePerformanceQualified=False,updates=[])
    started=time.perf_counter()
    try:
        for update in range(args.updates):
            folder=args.output/f"update-{update:04d}"
            folder.mkdir()
            behavior=folder/"behavior.tmppo"
            trainer.file("export",behavior)
            episodes=[];accepted=0;decisions=[]
            for episode in range(args.episodes):
                current=machine.reset();score=0.0;rows=0;error=None;failed_controls=None
                for index in range(args.horizon//args.repeat):
                    before=current
                    action=trainer.sample(encode(current,origin))
                    controls=[(action[0]+1)/2,(action[1]+1)/2,action[2]]
                    trace=hashlib.sha256()
                    try:
                        for substep in range(args.repeat):trace.update(machine.step(controls))
                        current=machine.observation()
                    except UncapturedStepError as exc:
                        trainer.cancel();error=str(exc);failed_controls=controls;break
                    reward=sum((a-b)*v for a,b,v in zip(current["position"],before["position"],axis))
                    trainer.observe(reward,encode(current,origin),
                        truncated=index==args.horizon//args.repeat-1)
                    decisions.append(dict(episode=episode,index=index,controls=controls,reward=reward,
                        before=before,after=current,traceSha256=trace.hexdigest()))
                    score+=reward;rows+=1;accepted+=1
                episodes.append(dict(episode=episode,acceptedDecisions=rows,
                    completed=error is None,acceptedReward=score,error=error,
                    failedControls=failed_controls,failedAtPhysicsTick=machine.frame if error else None,
                    firstUncapturedAccess=(machine.report.get("uncapturedAccesses") or
                                           machine.report.get("uncapturedMappings") or [None])[0]))
            (folder/"physics-decisions.json").write_text(json.dumps(decisions,separators=(",",":"))+"\n")
            row=dict(index=update,episodes=episodes,acceptedTransitions=accepted,
                behaviorModelSha256=hashlib.sha256(behavior.read_bytes()).hexdigest())
            if accepted:
                csv=folder/"rollout.csv";audit=folder/"behavior-audit.json"
                trainer.file("rollout_csv",csv)
                result=subprocess.run([str(args.auditor.resolve()),str(behavior),str(csv),str(audit),
                                       "--multiple-episodes"],capture_output=True,text=True,timeout=60)
                require(result.returncode==0,"Independent behavior audit failed: "+result.stderr)
                proof=json.loads(audit.read_text());require(proof["transitions"]==accepted,"Transition audit count differs")
                row["behaviorAudit"]=proof;row["ppoMetrics"]=trainer.update()
            else:row["ppoMetrics"]=None
            trainer.file("checkpoint",folder/"training.checkpoint")
            trainer.file("export",folder/"updated.tmppo")
            row["updatedModelSha256"]=hashlib.sha256((folder/"updated.tmppo").read_bytes()).hexdigest()
            report["updates"].append(row)
            report["totalAcceptedTransitions"]=sum(r["acceptedTransitions"] for r in report["updates"])
            report["elapsedSeconds"]=time.perf_counter()-started
            (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
            print("OWNED_PPO_UPDATE",update,"accepted="+str(accepted),"completed_episodes="+str(sum(e["completed"] for e in episodes)),flush=True)
            require(accepted>0,"No valid transition available; capture the reported frontier before training")
    finally:trainer.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture",type=Path,required=True)
    parser.add_argument("--exe",type=Path,required=True)
    parser.add_argument("--ntdll",type=Path,default=Path(r"C:\Windows\System32\ntdll.dll"))
    parser.add_argument("--kernel32",type=Path,default=Path(r"C:\Windows\System32\kernel32.dll"))
    parser.add_argument("--native-guard",type=Path,required=True)
    parser.add_argument("--initialize-writes",action="store_true")
    parser.add_argument("--policy-dll",type=Path,required=True)
    parser.add_argument("--auditor",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--resume",type=Path)
    parser.add_argument("--updates",type=int,default=4)
    parser.add_argument("--episodes",type=int,default=4)
    parser.add_argument("--horizon",type=int,default=100)
    parser.add_argument("--repeat",type=int,default=5)
    parser.add_argument("--seed",type=int,default=2026)
    parser.add_argument("--forward-axis",type=float,nargs=3,required=True)
    main(parser.parse_args())
