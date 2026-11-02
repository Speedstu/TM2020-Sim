"""Exercise Gymnasium API, genuine race termination and short-horizon truncation."""
import argparse
import json
from pathlib import Path

from force_worker_fixture import require
from headless_gym import TrackmaniaHeadlessEnv,gym
from gymnasium.utils.env_checker import check_env


def main(args):
    require(not args.output.exists(),"Never overwrite Gym evidence");args.output.mkdir(parents=True)
    env=TrackmaniaHeadlessEnv(args.host,args.map,args.packs,args.output/"full",horizon=5000,repeat=5,extension_sha256=args.extension_sha256)
    try:
        check_env(env,skip_render_check=True)
        env.reset(seed=2026);decisions=0
        while True:
            _,_,terminated,truncated,info=env.step([1,-1,0]);decisions+=1
            if terminated or truncated:break
        require(terminated and not truncated and env.engine.state["finishTimeMs"]==17406,
            "Expected reference full-gas race finish was not reached")
        require(info["advancedTicks"]==1,"Final action repeat must stop exactly at race finish")
        final_tick=env.engine.state["tick"]
        try:env.step([1,-1,0])
        except ValueError:pass
        else:raise ValueError("Step after terminal accepted")
        require(env.engine.state["tick"]==final_tick,"Rejected post-finish step changed clock")
        finish=env.engine.state["finishTimeMs"]
    finally:env.close()
    short=TrackmaniaHeadlessEnv(args.host,args.map,args.packs,args.output/"short",horizon=7,repeat=5,extension_sha256=args.extension_sha256)
    try:
        short.reset();_,_,terminal,truncated,first=short.step([1,-1,0])
        require(not terminal and not truncated and first["advancedTicks"]==5,"First repeat differs")
        _,_,terminal,truncated,last=short.step([1,-1,0])
        require(not terminal and truncated and last["advancedTicks"]==2,"Horizon must clip action repeat")
    finally:short.close()
    result=dict(schema="tm2020_headless_gym_api_test_v1",officialCheckerPassed=True,
        finishTimeMs=finish,decisionsToFinish=decisions,finishTicks=final_tick,
        finishPartialRepeatTicks=info["advancedTicks"],postFinishStepRejectedWithoutMutation=True,
        truncationRepeatTicks=[first["advancedTicks"],last["advancedTicks"]],
        originalGameDifferentialPerformed=False,completeExactSimulatorQualified=False)
    (args.output/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print("PASS GYM_API_AND_RACE_BOUNDARIES",finish,"ms finish; truncation 5+2 ticks")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("host","map","packs","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--extension-sha256");main(p.parse_args())
