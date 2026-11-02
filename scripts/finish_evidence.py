"""Fail-closed local-client finish qualification; simulation cannot satisfy it."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
from run_fast_ppo import ROOT

UID='ypPmohQofd72MyTsIsijKfrJH98'


def verified_goal(folder):
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    try:
        g=json.loads((Path(folder)/'verified-game.json').read_text())
        board=json.loads(Path(g['leaderboard']).read_text())
        age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(board['fetchedUtc'])).total_seconds()
        if not (g['status']=='GAME_FINISH_VERIFIED' and g['mapUid']==board['mapUid']==UID
                and board['scope']=='world_personal_best' and 0<=age<=7200):return False
        if digest(g['model'])!=g['modelSha256'] or digest(g['replay'])!=g['replaySha256']:return False
        control=json.loads(Path(g['controlReport']).read_text());trial=json.loads(Path(g['trialReport']).read_text())
        if not (control['mode']=='control' and control['mapUid']==UID and control['workerReturnedNormally']
                and control['modelSha256']==g['modelSha256'] and control['dllSha256']==digest(g['runtime'])
                and trial['consumerReadbackExact'] and trial['workerDetachedNormally']
                and not trial['unexpectedFaults'] and trial['internalControlTicks']>=100):return False
        if not (control['offlineProof'].get('isolatedFromHost') or control['offlineProof'].get('localSoloDeclaredByUser')):return False
        binary=ROOT/'cache/training-metadata-target/release/tm2020-training-metadata'
        result=subprocess.run([str(binary),'replay',g['replay']],capture_output=True,text=True,check=True,timeout=30)
        meta=json.loads(result.stdout)
        return bool(meta['mapUid']==UID and meta['respawns']==0 and meta['declaredMs']==g['finishMs']
                    and 0<g['finishMs']<=board['thresholdMs'])
    except (KeyError,ValueError,TypeError,OSError,subprocess.SubprocessError):return False
