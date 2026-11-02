"""Map/model identity and fresh physical binding gates for campaign switching."""
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from hybrid_tracking import save_asset
from campaign_play_bundle import freeze_candidate,check_entry,check_qualification


class CampaignPlay(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)
        m=self.root/'map.gbx';m.write_bytes(b'owned map identity')
        self.metadata={'index':2,'mapUid':'owned_map02','name':'Owned map','map':str(m),
            'mapSha256':hashlib.sha256(m.read_bytes()).hexdigest(),'top10TargetMs':12345}
        ref=np.zeros((100,25),dtype='<f4');ref[:,0]=ref[:,4]=ref[:,8]=ref[:,12]=ref[:,22]=1;ref[:,9:12]=[100,20,300]
        self.reference=self.root/'reference.f32';ref.tofile(self.reference)
        asset=self.root/'model.tmhyb';save_asset(asset,ref,[0,0,0,0,.001,0],map_path=m,uid=self.metadata['mapUid'])
        self.result={'model':str(asset),'modelSha256':hashlib.sha256(asset.read_bytes()).hexdigest(),
            'nominal64':{'count':64,'finishes':64,'worstMs':12340}}
    def tearDown(self):self.temporary.cleanup()
    def test_qualified_bundle_freezes_asset_and_spawn(self):
        e=freeze_candidate(self.result,self.metadata,self.root/'bundle',self.reference)
        self.assertEqual(e['spawn'],[100,20,300]);check_entry(e)
        Path(self.result['model']).write_bytes(b'replaced search candidate')
        check_entry(e) # Bundle retained its own immutable snapshot.
        Path(e['model']).write_bytes(b'corrupted')
        with self.assertRaises(ValueError):check_entry(e)
    def test_incomplete_or_slow_result_rejected(self):
        for values in ({'finishes':63},{'worstMs':12346}):
            r=dict(self.result,nominal64=dict(self.result['nominal64'],**values))
            with self.assertRaises(ValueError):freeze_candidate(r,self.metadata,self.root/'bundle',self.reference)
    def test_stale_or_other_map_qualification_rejected(self):
        e=freeze_candidate(self.result,self.metadata,self.root/'bundle',self.reference)
        q={'physicalConsumerQualified':True,'workerReturnedNormally':True,'hostPid':123,
            'offlineProof':{'processStartTicks':'abc'},'mapUid':e['mapUid'],'mapSha256':e['mapSha256'],
            'spawn':e['spawn'],'binding':{'manager':1,'vehicle':2,'body':3}}
        check_qualification(q,e,123,'abc')
        for overrides in ({'mapUid':'wrong'},{'hostPid':124},{'spawn':[0,0,0]},
                {'offlineProof':{'processStartTicks':'old'}},{'workerReturnedNormally':False}):
            with self.assertRaises(ValueError):check_qualification(dict(q,**overrides),e,123,'abc')

    def test_reset_precedes_observer_installation(self):
        import play_internal_campaign as play
        entry=freeze_candidate(self.result,self.metadata,self.root/'bundle',self.reference)
        events=[];directory=self.root/'qualification'
        report={'physicalConsumerQualified':True,'workerReturnedNormally':True,'hostPid':123,
            'offlineProof':{'processStartTicks':'abc'},'mapUid':entry['mapUid'],'mapSha256':entry['mapSha256'],
            'spawn':entry['spawn'],'binding':{'manager':1,'vehicle':2,'body':3}}
        class Telemetry:
            pid=123;start_ticks='abc'
            def current(self):return {'valid':True,'state':2,'mapUid':entry['mapUid']}
        class Child:
            returncode=0
            def __init__(self,*args,**kwargs):
                self.assert_order=list(events);events.append('install_observer')
                trace=directory/'trace';trace.mkdir(parents=True)
                (trace/'report.json').write_text(__import__('json').dumps(report))
            def poll(self):return 0
        with (patch.object(play,'reset_local_map',side_effect=lambda:events.append('reset')),
             patch.object(play.subprocess,'Popen',Child)):
            result=play.qualify(Telemetry(),entry,self.root,directory,lambda:False)
        self.assertEqual(events,['reset','install_observer'])
        self.assertTrue(result.exists())

    def test_unstable_but_normally_detached_observation_is_retryable(self):
        import play_internal_campaign as play
        entry=freeze_candidate(self.result,self.metadata,self.root/'bundle',self.reference)
        directory=self.root/'unstable'
        class Telemetry:
            pid=123;start_ticks='abc'
            def current(self):return {'valid':True,'state':2,'mapUid':entry['mapUid']}
        class Child:
            returncode=0
            def __init__(self,*args,**kwargs):
                p=directory/'trace';p.mkdir(parents=True)
                (p/'report.json').write_text('{"workerReturnedNormally":true,"physicalConsumerQualified":false}')
            def poll(self):return 0
        with patch.object(play,'reset_local_map'),patch.object(play.subprocess,'Popen',Child):
            with self.assertRaises(play.QualificationUnavailable):
                play.qualify(Telemetry(),entry,self.root,directory,lambda:False)


if __name__=='__main__':unittest.main()
