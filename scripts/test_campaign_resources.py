"""Keep concurrent map admission and interrupted stage recovery conservative."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from campaign_resources import can_admit,live_client_running
from pursue_campaign_records import prepare


class ResourceTests(unittest.TestCase):
    def test_client_detection_uses_executable_not_shell_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'1').mkdir();p=root/'1/cmdline'
            p.write_bytes(b'bash\0-c\0echo Trackmania.exe\0');self.assertFalse(live_client_running(root))
            p.write_bytes(b'C:\\Games\\Trackmania.exe\0');self.assertTrue(live_client_running(root))
            p.unlink();self.assertFalse(live_client_running(root))

    def test_game_reserve_prevents_second_large_search(self):
        self.assertTrue(can_admit(15360,6144,8192,[9000]))
        self.assertFalse(can_admit(15360,6144+4096,8192,[9000]))
    def test_third_search_fits_but_fourth_waits(self):
        self.assertTrue(can_admit(14336,6144,4096,[3072,3072]))
        self.assertFalse(can_admit(11264,6144,4096,[3072,3072,3072]))

    def test_pending_world_allocations_are_reserved(self):
        self.assertFalse(can_admit(14336,6144,4096,[3072,3072,0]))
        self.assertTrue(can_admit(24576,6144,4096,[3072,3072,3072]))

    def test_low_memory_does_not_start_a_worker(self):
        self.assertFalse(can_admit(5000,6144,4096,[]))

    def test_long_map_reservation_keeps_third_large_world_out(self):
        self.assertTrue(can_admit(25600,6144,8192,[0]))
        self.assertFalse(can_admit(25600,6144,8192,[0,0]))
        self.assertFalse(can_admit(10240,6144,8192,[7168,7168]))

    def test_interrupted_stage_keeps_checkpoint_without_claiming_arrival(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';out=root/'output'
            s=source/'02';d=out/'02';stage=out/'stages/000/02'
            for p in (s,d,stage):p.mkdir(parents=True,exist_ok=True)
            (s/'map.json').write_text(json.dumps({'index':2,'mapUid':'owned-map','targetMs':10000,'referenceMs':9900}))
            for name in ('reference.json','reference.f32'):(s/name).write_bytes(b'owned fixture data')
            (d/'leaderboard.json').write_text(json.dumps({'sourceUrl':'https://trackmania.io/api/leaderboard/map/owned-map?length=10',
                'fetchedUtc':'2026-10-31T00:00:00Z','tops':[{'position':1,'time':9900},{'position':10,'time':10000}]}))
            (stage/'best.tmhyb').write_bytes(b'owned checkpoint snapshot')
            (d/'pursuit.json').write_text(json.dumps({'index':2,'attempts':0,'selected':None,'bestAsset':None,'state':'searching',
                'selectionProtocol':'nominal-first-v2','currentStage':str(stage)}))
            with contextlib.redirect_stdout(io.StringIO()):_,states=prepare(source,out,[2])
            state=states[2]
            self.assertEqual(state['attempts'],1)
            self.assertEqual(Path(state['resumeAsset']).read_bytes(),b'owned checkpoint snapshot')
            self.assertIsNone(state['selected'])
            self.assertFalse(state['simGoalPassed'])


if __name__=='__main__':unittest.main()
