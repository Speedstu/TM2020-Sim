"""Verify cleanup boundaries on disposable trees, never on the real workspace."""
import json
from pathlib import Path
import tempfile
import unittest

from clean_workspace import apply, plan


class CleanupBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'local/recon/fixture/owned-wine-prefix'
        (self.prefix / 'drive_c/windows').mkdir(parents=True)
        for name in ('system.reg', 'user.reg'):
            (self.prefix / name).write_text('generated fixture')
        self.evidence = self.prefix.parent / 'owned-windows-final.json'
        self.evidence.write_text(json.dumps({'ownedDetour': True, 'gameAccessed': False}))

    def test_removes_only_generated_prefix_and_keeps_neighboring_evidence(self):
        report = self.root / 'deletions.jsonl'
        items = plan(self.root, set())
        self.assertEqual(len(items), 1)
        apply(self.root, items, report, active_provider=set)
        self.assertFalse(self.prefix.exists())
        self.assertTrue(self.evidence.is_file())
        self.assertIn('remove-generated-directory', report.read_text())

    def test_active_prefix_is_never_planned(self):
        self.assertEqual(plan(self.root, {self.prefix.resolve()}), [])

    def test_models_and_replays_block_prefix_removal(self):
        for name in ('champion.tmhyb', 'training.checkpoint', 'run.Replay.Gbx', 'model.pt'):
            p = self.prefix / name
            p.write_bytes(b'protected')
            self.assertEqual(plan(self.root, set()), [], name)
            p.unlink()

    def test_refuses_incomplete_or_game_accessing_fixture(self):
        self.evidence.write_text(json.dumps({'ownedDetour': True, 'gameAccessed': True}))
        self.assertEqual(plan(self.root, set()), [])
        self.evidence.unlink()
        self.assertEqual(plan(self.root, set()), [])

    def test_rechecks_activity_before_deleting(self):
        items = plan(self.root, set())
        with self.assertRaises(RuntimeError):
            apply(self.root, items, self.root / 'journal',
                  active_provider=lambda: {self.prefix.resolve()})
        self.assertTrue(self.prefix.is_dir())

    def test_rechecks_new_protected_files_before_deleting(self):
        items = plan(self.root, set())
        (self.prefix / 'new.tmhyb').write_bytes(b'new champion')
        with self.assertRaises(RuntimeError):
            apply(self.root, items, self.root / 'journal', active_provider=set)
        self.assertTrue(self.prefix.is_dir())

    def test_does_not_follow_symlinks_or_clean_game_prefix(self):
        external = self.root / 'real-game'
        external.mkdir()
        (external / 'keep.txt').write_text('game')
        (self.prefix.parent / 'link').symlink_to(external, target_is_directory=True)
        # A symlinked evidence parent must not make an external directory eligible.
        (self.root / 'local/recon/symlink').symlink_to(self.prefix.parent, target_is_directory=True)
        items = plan(self.root, set())
        self.assertEqual(len(items), 1)
        apply(self.root, items, self.root / 'journal', active_provider=set)
        self.assertEqual((external / 'keep.txt').read_text(), 'game')

    def test_bytecode_only_and_preserves_tool_environments(self):
        bytecode = self.root / 'scripts/__pycache__'
        bytecode.mkdir(parents=True)
        (bytecode / 'module.pyc').write_bytes(b'cache')
        tools = self.root / 'tools/venv/__pycache__'
        tools.mkdir(parents=True)
        (tools / 'module.pyc').write_bytes(b'environment')
        items = plan(self.root, set())
        self.assertIn('scripts/__pycache__', [x['path'] for x in items])
        self.assertNotIn('tools/venv/__pycache__', [x['path'] for x in items])
        (bytecode / 'not-cache.txt').write_text('keep')
        self.assertNotIn('scripts/__pycache__', [x['path'] for x in plan(self.root, set())])


if __name__ == '__main__':
    unittest.main()
