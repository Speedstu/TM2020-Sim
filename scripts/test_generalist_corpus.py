"""Check the whole-map leakage controls using adversarial miniature corpora."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import build_generalist_corpus as corpus


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name)
        self.previous=corpus.ROOT;corpus.ROOT=self.root
        self.rows=[]
        for i in range(10):
            map_path=self.root/f'map-{i}.Map.Gbx';map_path.write_bytes(f'owned fixture {i}'.encode())
            meta=self.root/f'map-{i}.json'
            meta.write_text(json.dumps(dict(uid=f'uid-{i}',mapName=f'Name {i}',
                blocks=[dict(name='Road',grid=[i,0,0])],items=[])))
            replay=self.root/f'replay-{i}.Replay.Gbx';replay.write_bytes(f'replay {i}'.encode())
            self.rows.append(dict(mapUid=f'uid-{i}',mapName=f'Name {i}',mapGbx=map_path.name,
                mapJson=meta.name,replayGbx=replay.name,mapSha256=corpus.sha(map_path),replaySha256=corpus.sha(replay)))
        self.manifest=self.root/'manifest.json';self.save()
        self.args=argparse.Namespace(manifest=self.manifest,families=None,extra_map=[],known_training_uid=['uid-0'],
            seed=38,output=self.root/'output.json')

    def tearDown(self):
        corpus.ROOT=self.previous;self.temporary.cleanup()

    def save(self):self.manifest.write_text(json.dumps(dict(pairs=self.rows)))

    def build(self):
        with contextlib.redirect_stdout(io.StringIO()):corpus.build(self.args)
        x=json.loads(self.args.output.read_text())
        return x,{r['mapUid']:k for k,rows in x['splits'].items() for r in rows}

    def test_different_replays_never_split_the_same_map(self):
        self.rows.append(dict(self.rows[0],replayGbx=self.rows[1]['replayGbx'],replaySha256=self.rows[1]['replaySha256']))
        self.save();x,split=self.build()
        self.assertEqual(len(split),10);self.assertEqual(split['uid-0'],'train')
        self.assertEqual(len(next(r for r in x['splits']['train'] if r['mapUid']=='uid-0')['demonstrations']),2)

    def test_renamed_map_with_identical_layout_stays_together(self):
        path=self.root/self.rows[1]['mapJson'];x=json.loads(path.read_text())
        x['blocks']=json.loads((self.root/self.rows[0]['mapJson']).read_text())['blocks']
        path.write_text(json.dumps(x))
        _,split=self.build();self.assertEqual(split['uid-0'],split['uid-1'])

    def test_family_and_layout_grouping_is_transitive(self):
        path=self.root/self.rows[1]['mapJson'];x=json.loads(path.read_text())
        x['blocks']=json.loads((self.root/self.rows[0]['mapJson']).read_text())['blocks'];path.write_text(json.dumps(x))
        families=self.root/'families.json';families.write_text(json.dumps({'uid-1':'edited-family','uid-2':'edited-family'}))
        self.args.families=families
        _,split=self.build();self.assertEqual(split['uid-2'],'train')

    def test_changed_file_is_rejected(self):
        (self.root/self.rows[0]['mapGbx']).write_bytes(b'changed')
        with self.assertRaises(ValueError):self.build()

    def test_conflicting_uid_is_rejected(self):
        row=dict(self.rows[1],mapUid='uid-0')
        meta=self.root/row['mapJson'];x=json.loads(meta.read_text());x['uid']='uid-0';meta.write_text(json.dumps(x))
        self.rows.append(row);self.save()
        with self.assertRaises(ValueError):self.build()

    def test_outputs_are_not_overwritten(self):
        self.build()
        with self.assertRaises(ValueError):self.build()

    def test_misspelled_family_uid_cannot_silently_disable_grouping(self):
        path=self.root/'families.json';path.write_text(json.dumps({'wrong-uid':'family'}))
        self.args.families=path
        with self.assertRaises(ValueError):self.build()


if __name__=='__main__':unittest.main()
