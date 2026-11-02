"""Retention must never break a live search, incumbent, or client evidence."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from campaign_retention import sweep


class Retention(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.map=self.root/'02';self.map.mkdir();(self.map/'reference.f32').write_bytes(b'original reference')
        self.stages=[]
        for i in range(5):
            p=self.root/f'stages/{i:03d}/02';p.mkdir(parents=True);self.stages.append(p)
            for name in ('best.tmhyb','initial.tmhyb','candidate-0.tmhyb'):(p/name).write_bytes(b'model '+str(i).encode())
            (p/'result.json').write_text('{}');(p/'search.jsonl').write_text('audit metrics\n')
            (p/'reference.f32').write_bytes(b'original reference')
        self.state={'index':2,'attempts':4,'currentStage':str(self.stages[4]),
            'selected':{'model':str(self.stages[0]/'best.tmhyb')},'bestAsset':None}
        self.save()
    def save(self):
        (self.map/'pursuit.json').write_text(json.dumps(self.state))
    def tearDown(self):self.temp.cleanup()

    def test_dry_run_does_not_modify_models(self):
        report=sweep(self.root,keep=1)
        self.assertGreater(report['removableModels'],0)
        self.assertTrue((self.stages[0]/'candidate-0.tmhyb').exists())
        self.assertFalse((self.root/'retention-status.json').exists())

    def test_active_incumbent_recent_reports_and_unknown_files_stay(self):
        unknown=self.stages[0]/'user.checkpoint';unknown.write_bytes(b'not disposable')
        report=sweep(self.root,keep=1,apply=True)
        self.assertGreater(report['removedModels'],0)
        self.assertFalse((self.stages[0]/'candidate-0.tmhyb').exists())
        self.assertTrue((self.stages[0]/'best.tmhyb').exists())
        for i in (3,4):self.assertTrue((self.stages[i]/'candidate-0.tmhyb').exists())
        self.assertEqual((self.stages[0]/'search.jsonl').read_text(),'audit metrics\n')
        self.assertTrue(unknown.exists())
        self.assertTrue((self.stages[0]/'result.json').exists())
        self.assertTrue((self.stages[0]/'reference.f32').is_symlink())
        self.assertEqual((self.stages[0]/'reference.f32').read_bytes(),b'original reference')

    def test_child_result_not_yet_acknowledged_and_incomplete_stage_stay(self):
        self.state['attempts']=1;self.save()
        (self.stages[0]/'result.json').unlink()
        report=sweep(self.root,keep=1,apply=True)
        self.assertEqual(report['removedModels'],0)
        self.assertTrue((self.stages[1]/'candidate-0.tmhyb').exists())

    def test_selected_old_snapshot_protected_and_other_snapshots_bounded(self):
        snapshots=[]
        for i in range(5):
            p=self.map/f'best-{i:020x}.tmhyb';p.write_bytes(b'checkpoint');os.utime(p,ns=(100+i,100+i));snapshots.append(p)
        self.state['bestAsset']=str(snapshots[0]);self.save()
        sweep(self.root,keep=2,apply=True)
        self.assertTrue(snapshots[0].exists())
        self.assertTrue(snapshots[3].exists());self.assertTrue(snapshots[4].exists())
        self.assertFalse(snapshots[1].exists());self.assertFalse(snapshots[2].exists())

    def test_nonidentical_reference_and_external_symlink_not_modified(self):
        (self.stages[0]/'reference.f32').write_bytes(b'different reference')
        outside=self.root/'outside.tmhyb';outside.write_bytes(b'untouchable')
        link=self.stages[0]/'candidate-1.tmhyb';link.symlink_to(outside)
        sweep(self.root,keep=1,apply=True)
        self.assertFalse((self.stages[0]/'reference.f32').is_symlink())
        self.assertEqual(outside.read_bytes(),b'untouchable');self.assertTrue(link.is_symlink())


if __name__=='__main__':unittest.main()
