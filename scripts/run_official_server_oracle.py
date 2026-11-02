"""Run pinned official Linux dedicated server on owned local replay fixtures.

This is a whole-game oracle, not a standalone reimplementation. It uses a
temporary staging directory and never publishes game binaries or private maps.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

SERVER_SHA='3b6107824feea402bd32c888e994dcd6df4a10afc8676a2647ac9560ccf0d779'
BAD_TIME_MS=4_294_967_000
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def parse(text):
    raw,_=json.JSONDecoder().raw_decode(text.lstrip())
    if not isinstance(raw,list):raise ValueError('Unexpected official result document')
    results=[]
    for item in raw:
        if not isinstance(item,dict) or not isinstance(item.get('FileName'),str):raise ValueError('Malformed official result')
        validated=item.get('ValidatedResult');declared=item.get('DeclaredResult')
        def time(value):
            if value is None:return None
            ms=value['Time']
            return ms if isinstance(ms,int) and 0<=ms<=BAD_TIME_MS else None
        results.append(dict(file=item['FileName'],validatedMs=time(validated),declaredMs=time(declared),
            validatedCheckpoints=validated.get('NbCheckpoints') if validated else None,
            declaredCheckpoints=declared.get('NbCheckpoints') if declared else None,
            serverIsValid=item.get('IsValid'),description=item.get('Desc'),
            gameBuild=item.get('GameBuild'),mapUid=item.get('MapUid')))
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--server',type=Path,required=True)
    p.add_argument('--map',type=Path,required=True)
    p.add_argument('--ghost',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    server=args.server.resolve(strict=True);track=args.map.resolve(strict=True);ghosts=[g.resolve(strict=True) for g in args.ghost]
    if args.output.exists():raise ValueError('Never overwrite oracle evidence')
    if sha(server/'TrackmaniaServer')!=SERVER_SHA:raise ValueError('Unqualified dedicated server build')
    if not (server/'Packs').is_dir():raise ValueError('Missing server packs')
    if len({g.name for g in ghosts})!=len(ghosts):raise ValueError('Duplicate replay names')
    if any(g.suffix.lower()!='.gbx' or not g.name.endswith(('.Ghost.Gbx','.Replay.Gbx')) for g in ghosts):
        raise ValueError('Unsupported replay name')
    with tempfile.TemporaryDirectory(prefix='tm2020-official-oracle-') as temporary:
        root=Path(temporary);(root/'UserData/Maps').mkdir(parents=True);(root/'UserData/Replays').mkdir(parents=True)
        (root/'TrackmaniaServer').symlink_to(server/'TrackmaniaServer')
        (root/'Packs').symlink_to(server/'Packs',target_is_directory=True)
        (root/'UserData/Maps'/track.name).symlink_to(track)
        for ghost in ghosts:(root/'UserData/Replays'/ghost.name).symlink_to(ghost)
        result=subprocess.run(['./TrackmaniaServer','/nodaemon','/validatepath=.'],cwd=root,
            capture_output=True,text=True,timeout=180)
    if result.returncode!=0:raise RuntimeError('Official validator failed: '+result.stdout[-1000:]+result.stderr[-1000:])
    outputs=parse(result.stdout)
    if len(outputs)!=len(ghosts):raise RuntimeError(f'Validator returned {len(outputs)} results for {len(ghosts)} ghosts: '+result.stdout[-3000:]+result.stderr[-500:])
    if {o['file'] for o in outputs}!={g.name for g in ghosts}:raise RuntimeError('Oracle response files differ')
    report=dict(schema='tm2020_official_server_oracle_v1',serverSha256=SERVER_SHA,
        map=dict(path=str(track),sha256=sha(track)),ghosts=[dict(path=str(g),sha256=sha(g)) for g in ghosts],
        results=outputs,serverExitCode=result.returncode,sourceGameProcessAccessed=False,
        originalGamePhysicsExecuted=True,completeIndependentSimulatorQualified=False)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS OFFICIAL_SERVER_ORACLE',[(o['file'],o.get('validatedMs'),o.get('declaredMs')) for o in outputs])

if __name__=='__main__':main()
