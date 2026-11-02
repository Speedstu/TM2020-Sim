"""Reject unacknowledged/incorrect physics extensions before accepting a state."""
import argparse
import json
from pathlib import Path
from force_worker_fixture import require
from headless_engine import HeadlessEngine

def main(args):
    require(not args.output.exists(),"Never overwrite protocol identity evidence");args.output.mkdir(parents=True)
    rejected=0
    for label,expected in (("unacknowledged",None),("wrong-digest","0"*64)):
        try:
            with HeadlessEngine(args.host,args.map,args.packs,args.output/(label+".log"),extension_sha256=expected):pass
        except ValueError as error:
            require("identity/protocol" in str(error),"Unexpected rejection reason");rejected+=1
        else:raise ValueError("Extension was accepted with wrong identity")
    with HeadlessEngine(args.host,args.map,args.packs,args.output/"acknowledged.log",extension_sha256=args.extension_sha256) as engine:
        require(engine.ready["physicsExtensionSha256"]==args.extension_sha256,"Correct engine did not identify its patch")
    (args.output/"report.json").write_text(json.dumps(dict(schema="tm2020_extension_identity_audit_v1",
        wrongIdentitiesRejected=rejected,acknowledgedExtensionAccepted=True,sourceGameProcessAccessed=False),indent=2)+"\n")
    print("PASS EXTENSION_IDENTITY two wrong identities denied")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("host","map","packs","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--extension-sha256",required=True);main(p.parse_args())
