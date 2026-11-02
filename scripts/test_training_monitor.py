"""Promotion must match fresh world timing and this exact officially checked actor."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from training_monitor import gate,top_ten,render_unit,monitor,digest,policy_matches_checkpoint,advance


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime.now(dt.timezone.utc)
        self.board={'mapUid':'mapA','scope':'world_personal_best','fetchedUtc':self.now.isoformat(),'thresholdMs':20006}
        self.validation={'status':'OFFICIAL_TIME_VERIFIED','originalGamePhysicsExecuted':True,'modelSha256':'modelA',
                         'mapUid':'mapA','thresholdAchieved':True,'finishMs':20005}

    def test_verified_faster_actor_can_advance(self):
        self.assertTrue(gate(self.board,self.validation,'modelA','mapA',self.now))

    def test_simulation_wrong_actor_map_or_failed_finish_never_advances(self):
        for key,value in [('status','SIMULATION_BELOW_TARGET'),('originalGamePhysicsExecuted',False),
                          ('modelSha256','modelB'),('mapUid','mapB'),('thresholdAchieved',False),
                          ('finishMs',20006),('finishMs',20007),('finishMs',0)]:
            candidate={**self.validation,key:value}
            self.assertFalse(gate(self.board,candidate,'modelA','mapA',self.now),(key,value))

    def test_old_or_nonworld_threshold_never_advances(self):
        for key,value in [('fetchedUtc',(self.now-dt.timedelta(hours=3)).isoformat()),
                          ('fetchedUtc',(self.now+dt.timedelta(hours=1)).isoformat()),
                          ('scope','national'),('mapUid','mapB')]:
            self.assertFalse(gate({**self.board,key:value},self.validation,'modelA','mapA',self.now))
        self.assertFalse(gate({},self.validation,'modelA','mapA',self.now))

    def test_threshold_requires_exact_rank_ten_and_ordered_integer_times(self):
        raw={'tops':[{'position':i,'time':19900+i,'url':None} for i in range(1,11)]}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'threshold.json'
            with patch('training_monitor.http',return_value=json.dumps(raw).encode()):
                result=top_ten('mapA',out)
            self.assertEqual(result['thresholdMs'],19910);self.assertTrue(out.exists())
            for malformed in ({'tops':raw['tops'][:-1]}, {'tops':list(reversed(raw['tops']))},
                              {'tops':[dict(r,time=True) for r in raw['tops']]}):
                with patch('training_monitor.http',return_value=json.dumps(malformed).encode()):
                    with self.assertRaises(ValueError):top_ten('mapA',out)

    def test_next_unit_preserves_bounds_and_cannot_inject_systemd_options(self):
        config={'library':'/tmp/library.so'}
        active={'session':'/tmp/next','map':'/tmp/map.Map.Gbx','seed':42,'horizon':6000}
        unit=render_unit(config,active,Path('/tmp/initial'))
        self.assertIn('"--horizon" "6000"',unit);self.assertIn('"--eval-trials" "20"',unit)
        self.assertIn('"--restart-from-best"',unit)
        for bad in ('/tmp/map\nExecStart=bad','/tmp/%n','/tmp/"bad'):
            with self.assertRaises(ValueError):render_unit(config,{**active,'map':bad},Path('/tmp/initial'))

    def test_monitor_restarts_a_stalled_enabled_service_and_writes_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'training';session.mkdir()
            (session/'best.tmppo').write_bytes(b'portable actor');(session/'best.checkpoint').write_bytes(b'checkpoint')
            champion={'checkpointSha256':digest(session/'best.checkpoint'),'updatedUtc':self.now.isoformat(),
                      'evaluation':{'trials':20,'finishes':20,'bestFinishMs':28000,'meanFinishMs':29000,'meanReward':71}}
            (session/'best.json').write_text(json.dumps(champion))
            (session/'state.json').write_text(json.dumps({'updatedUtc':(self.now-dt.timedelta(minutes=20)).isoformat()}))
            active={'index':0,'session':str(session),'map':'test.Map.Gbx','mapUid':'mapA','name':'Test','seed':42}
            config={'directory':str(root/'monitor'),'initialActive':active,'maps':[active],'library':'unused.so'}
            with patch('training_monitor.active_service',return_value=True),patch('training_monitor.systemctl',return_value=SimpleNamespace(returncode=0)) as control,\
                 patch('training_monitor.metadata',return_value={'mapUid':'mapA'}),patch('training_monitor.top_ten',return_value=self.board),\
                 patch('training_monitor.policy_matches_checkpoint',return_value=True):
                result=monitor(config)
            self.assertEqual(result['status'],'MONITORING');self.assertIn('restarted_unhealthy_training',result['actions'])
            self.assertTrue(any(call.args[0]=='restart' for call in control.call_args_list))
            self.assertTrue((root/'monitor/latest.json').is_file());self.assertTrue((root/'monitor/history.jsonl').is_file())

    def test_explicit_training_stop_marker_prevents_automatic_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);session=root/'training';session.mkdir();(session/'STOP').touch()
            active={'index':0,'session':str(session),'map':'test.Map.Gbx','mapUid':'mapA','name':'Test','seed':42}
            with patch('training_monitor.systemctl') as control:
                monitor({'directory':str(root/'monitor'),'initialActive':active,'maps':[active]})
            control.assert_not_called()
            self.assertEqual(json.loads((root/'monitor/latest.json').read_text())['status'],'TRAINING_STOP_MARKER')

    def test_interleaved_champion_publication_cannot_mix_model_and_checkpoint(self):
        nx,na,h=48,1,8;ns=4;count=h*(nx+1)+na*(h+1)+h*(nx+2)+1+na
        header=struct.pack('<6I',1,nx,na,h,ns,0);body=b'test'+bytes(count*8)
        model=b'TMPPO001'+header+body+bytes(8)
        checkpoint=b'TMTRAIN1'+header+bytes(96)+body+bytes(count*16)+bytes(8)
        self.assertTrue(policy_matches_checkpoint(model,checkpoint))
        changed=bytearray(model);changed[40]=1
        self.assertFalse(policy_matches_checkpoint(changed,checkpoint))
        self.assertFalse(policy_matches_checkpoint(model[:-1],checkpoint))

    def test_failed_next_map_preflight_leaves_training_service_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);snapshot=root/'snapshot';snapshot.mkdir();folder=root/'transition';folder.mkdir()
            for name in ('best.tmppo','best.checkpoint','best.json'):(snapshot/name).write_bytes(b'qualified artifact')
            validation={**self.validation,'modelSha256':digest(snapshot/'best.tmppo')}
            active={'index':0,'mapUid':'mapA'}
            config={'maps':[active,{'mapUid':'mapB','map':'next.Map.Gbx','name':'Next','authorScore':22000}],'library':'test.so'}
            with patch('training_monitor.ROOT',root),patch('training_monitor.ensure_map',return_value=Path('next.Map.Gbx')),\
                 patch('training_monitor.evaluate',side_effect=RuntimeError('unsupported map')),patch('training_monitor.systemctl') as control:
                with self.assertRaisesRegex(RuntimeError,'unsupported map'):
                    advance(config,active,root/'training',snapshot,validation,self.board,folder)
            control.assert_not_called()
            self.assertTrue((folder/'mastered/qualification.json').is_file())


if __name__=='__main__':unittest.main()
