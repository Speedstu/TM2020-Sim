"""Retain source/tool/replay identities without packaging installed game assets."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess

from force_worker_fixture import require
from pinned_build import ROOT,SHA
from headless_engine import UPSTREAM


def main(args):
    require(not args.output.exists(),"Never overwrite build provenance")
    def record(path):
        path=Path(path).resolve(strict=True)
        return dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    files=[ROOT/p for p in ("cache/gearbox-host-target/release/tm2020-gearbox-host.exe",
        "cache/gearbox-host-target/release/replay_audit.exe","cache/gearbox-host-target/release/inspect_assets.exe",
        "native/build/libtm2020_policy.dll","native/build/tm2020_headless_bc.exe","native/build/tm2020_init_headless_policy.exe",
        "native/src/headless_bc.cpp","native/src/init_headless_policy.cpp","native/src/trainer_abi.cpp")]
    files.extend(p for p in (ROOT/"integrations/gearbox-host").rglob("*") if p.is_file() and "target" not in p.parts)
    files.extend(ROOT/"scripts"/name for name in ("headless_engine.py","headless_gym.py","owned_ppo.py",
        "train_headless_ppo.py","audit_headless_ppo.py","evaluate_headless_ppo.py","test_headless_engine.py",
        "test_headless_gym.py","build-headless-backend.ps1","run-headless-checks.ps1"))
    replays=[*sorted((ROOT/"local/corpus").glob("*.Replay.Gbx")),*[ROOT/"local/replays"/f"tmtas-{i}.Replay.Gbx" for i in (4634,4754,4902)]]
    require(len(replays)==23,"Replay provenance corpus changed")
    checkout=ROOT/"cache/gearbox-upstream-e0583ee"
    revision=subprocess.check_output(["git","-C",str(checkout),"rev-parse","HEAD"],text=True).strip()
    changes=subprocess.check_output(["git","-C",str(checkout),"status","--porcelain"],text=True).strip()
    require(revision==UPSTREAM and not changes,"Pinned upstream checkout changed")
    bc=[]
    for role,index in (("fit",4634),("validation",4902),("test",4754)):
        path=ROOT/"local/recon/gearbox-game-replay-comparison-v2"/f"tmtas-{index}.Replay.Gbx.observations.csv"
        bc.append(dict(role=role,**record(path)))
    packs=Path(r"D:/SteamLibrary/steamapps/common/Trackmania/Packs")
    inventory=[dict(name=p.name,bytes=p.stat().st_size,modifiedNs=p.stat().st_mtime_ns) for p in sorted(packs.iterdir()) if p.is_file()]
    game=record(r"D:/SteamLibrary/steamapps/common/Trackmania/Trackmania.exe");require(game["sha256"]==SHA,"Game executable changed")
    report=dict(schema="tm2020_headless_build_provenance_v1",generatedUtc=datetime.now(timezone.utc).isoformat(),
        upstreamRevision=revision,upstreamCheckoutUnmodified=True,toolchain="rustc 1.99.1; Windows MSVC linker; MinGW C++20 SDK",
        gameExecutable=game,projectFiles=[record(path) for path in sorted(set(files))],replays=[record(p) for p in replays],
        bcDatasetFiles=bc,packInventory=inventory,fullPackContentHashesCaptured=False,
        rawAssetHashesInMilestoneAudit=True,completeExactSimulatorQualified=False,generalPolicyQualified=False)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print("HEADLESS PROVENANCE",len(files),"project files; 23 replays; three separate BC datasets")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);main(p.parse_args())
