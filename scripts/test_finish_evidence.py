#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from finish_evidence import UID,verified_goal


class FinishEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.write('board.json',{'mapUid':UID,'scope':'world_personal_best','thresholdMs':20006,
                    'fetchedUtc':dt.datetime.now(dt.timezone.utc).isoformat()})
        for name in ('model.tmppo','runtime.dll','finish.Replay.Gbx'):(self.root/name).write_bytes(name.encode())
        sha=lambda name:hashlib.sha256((self.root/name).read_bytes()).hexdigest()
        self.write('control.json',{'mode':'control','mapUid':UID,'workerReturnedNormally':True,
            'modelSha256':sha('model.tmppo'),'dllSha256':sha('runtime.dll'),
            'offlineProof':{'isolatedFromHost':True}})
        self.write('trial.json',{'consumerReadbackExact':True,'workerDetachedNormally':True,
            'unexpectedFaults':{},'internalControlTicks':4000})
        self.proof={'status':'GAME_FINISH_VERIFIED','mapUid':UID,'finishMs':19999,
                    'modelSha256':sha('model.tmppo'),'replaySha256':sha('finish.Replay.Gbx')}
        for key,name in [('leaderboard','board.json'),('model','model.tmppo'),('runtime','runtime.dll'),
                         ('replay','finish.Replay.Gbx'),('controlReport','control.json'),('trialReport','trial.json')]:
            self.proof[key]=str(self.root/name)
        self.meta={'mapUid':UID,'respawns':0,'declaredMs':19999}

    def tearDown(self):self.temp.cleanup()
    def write(self,name,value):(self.root/name).write_text(json.dumps(value))
    def check(self):
        self.write('verified-game.json',self.proof)
        with patch('finish_evidence.subprocess.run') as run:
            run.return_value.stdout=json.dumps(self.meta)
            return verified_goal(self.root)

    def test_complete_owned_fixture_and_native_metadata_pass(self):self.assertTrue(self.check())
    def test_simulated_success_never_qualifies(self):
        self.proof['status']='SIMULATED_FINISH';self.assertFalse(self.check())
    def test_hash_and_respawn_and_time_gates(self):
        self.meta['respawns']=1;self.assertFalse(self.check())
        self.meta['respawns']=0;self.meta['declaredMs']=23366;self.assertFalse(self.check())
        self.meta['declaredMs']=19999;self.proof['modelSha256']='wrong';self.assertFalse(self.check())
    def test_stale_board_and_abnormal_worker_rejected(self):
        board=json.loads((self.root/'board.json').read_text())
        board['fetchedUtc']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=3)).isoformat()
        self.write('board.json',board);self.assertFalse(self.check())
        board['fetchedUtc']=dt.datetime.now(dt.timezone.utc).isoformat();self.write('board.json',board)
        c=json.loads((self.root/'control.json').read_text());c['workerReturnedNormally']=False
        self.write('control.json',c);self.assertFalse(self.check())


if __name__=='__main__':unittest.main()
