"""Retention and publication checks for unattended, long-running CUDA training."""
import json
from pathlib import Path
import tempfile
import unittest
from train_continuous import atomic_copy,atomic_json,prune_evidence,publish_best,score

class ContinuousTests(unittest.TestCase):
    def test_prune_keeps_first_tail_and_external_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cycle=root/'cycle';run=cycle/'run';service=cycle/'cuda-service';service.mkdir(parents=True)
            for i in range(12):
                p=run/f'update-{i}';p.mkdir(parents=True);(p/'physics.bin').write_bytes(b'evidence')
                (service/f'request-{i}.txt').write_text('request');(service/f'response-{i}.txt').write_text('response')
            unrelated=root/'older-original-evidence.bin';unrelated.write_bytes(b'preserve')
            prune_evidence(cycle,10,3)
            self.assertEqual({p.name for p in run.iterdir()},{'update-0','update-8','update-9','update-10','update-11'})
            self.assertTrue(unrelated.exists());self.assertTrue((service/'request-11.txt').exists())
            self.assertFalse((service/'request-7.txt').exists())
    def test_evidence_symlink_cannot_delete_outside(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);outside=root/'outside';outside.mkdir();(outside/'important').write_text('keep')
            run=root/'cycle/run';run.mkdir(parents=True);(run/'update-1').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):prune_evidence(root/'cycle',10,3)
            self.assertEqual((outside/'important').read_text(),'keep')
    def test_best_prefers_completion_then_time_and_keeps_independent_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);model=root/'source.tmppo';checkpoint=root/'source.checkpoint'
            model.write_bytes(b'best model');checkpoint.write_bytes(b'optimizer state')
            first={'trials':5,'finishes':5,'meanFinishMs':30000,'meanReward':100}
            self.assertTrue(publish_best(root,first,model,checkpoint,{'test':True}))
            model.write_bytes(b'changed source')
            self.assertEqual((root/'best.tmppo').read_bytes(),b'best model')
            fewer={'trials':5,'finishes':4,'meanFinishMs':20000,'meanReward':200}
            self.assertFalse(publish_best(root,fewer,model,checkpoint,{}))
            slower={**first,'meanFinishMs':31000,'meanReward':999}
            self.assertFalse(publish_best(root,slower,model,checkpoint,{}))
            faster={**first,'meanFinishMs':29000}
            self.assertTrue(publish_best(root,faster,model,checkpoint,{}))
            self.assertEqual(json.loads((root/'best.json').read_text())['evaluation'],faster)
    def test_atomic_checkpoint_replaces_contents_without_changing_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source';target=root/'target';source.write_bytes(b'weights and Adam')
            atomic_copy(source,target);self.assertEqual(source.read_bytes(),target.read_bytes())
            source.write_bytes(b'new checkpoint');atomic_copy(source,target)
            self.assertEqual(target.read_bytes(),b'new checkpoint');self.assertFalse((root/'target.tmp').exists())

if __name__=='__main__':unittest.main()
