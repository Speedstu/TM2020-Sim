"""Observed input union: preserve evidence and reject conflicting provenance."""
import copy
from pathlib import Path
import unittest

import test_original_step_fixture as fixture_tests
from original_step_fixture import load_original_step_fixture
from merge_original_step_inputs import merge


class InputUnion(unittest.TestCase):
    def setUp(self):
        self.helper=fixture_tests.FixtureBounds()
        self.helper.setUp()
        self.addCleanup(self.helper.tearDown)
        self.root=Path(self.helper.directory.name)
        self.helper.raw=bytes([1]*1200+[0]*2896)+bytes(8192)
        self.helper.meta.update(sourcePid=42,sourceProcessCreationFiletime="123",
                                initialSnapshotSeedFixtureSha256="a"*64)
        self.helper.write()
        self.primary=self.helper.path
        self.contributor=self.root/"contributor.tmstep"
        self.out=self.root/"union.tmstep"
        self.report=self.root/"union.json"

    def contribute(self,conflict=False,**changes):
        self.helper.path=self.contributor
        meta=copy.deepcopy(self.helper.meta);meta.update(changes)
        raw=bytearray(self.helper.raw)
        raw[1300]=1;raw[4096+1300]=37;raw[8192+1300]=91
        if conflict:raw[4096+5]=1
        self.helper.write(meta=meta,raw=bytes(raw))

    def test_union_preserves_primary_trace_and_observed_values(self):
        self.contribute()
        result=merge(self.primary,[self.contributor],self.out,self.report)
        original=load_original_step_fixture(self.primary)
        page=result.pages[0x100000000]
        self.assertEqual(page.initial[1300],37)
        # The primary never accesses this byte; contributor final 91 is NOT used.
        self.assertEqual(page.expected[1300],37)
        self.assertEqual(result.trace_expected,original.trace_expected)
        self.assertEqual(result.metadata["observedInputUnion"]["contributors"][0]["addedObservedBytes"],1)

    def test_reject_conflicting_initial_byte(self):
        self.contribute(conflict=True)
        with self.assertRaisesRegex(ValueError,"Conflicting observed initial"):
            merge(self.primary,[self.contributor],self.out,self.report)
        self.assertFalse(self.out.exists())

    def test_reject_other_process(self):
        self.contribute(sourcePid=99)
        with self.assertRaisesRegex(ValueError,"different process"):
            merge(self.primary,[self.contributor],self.out,self.report)

    def test_reject_unrelated_seed(self):
        self.contribute(initialSnapshotSeedFixtureSha256="b"*64)
        with self.assertRaisesRegex(ValueError,"common initial state"):
            merge(self.primary,[self.contributor],self.out,self.report)

    def test_reject_different_velocity_provenance(self):
        self.contribute(sourceVelocityPreserved=True)
        with self.assertRaisesRegex(ValueError,"source-velocity provenance"):
            merge(self.primary,[self.contributor],self.out,self.report)


if __name__=="__main__":unittest.main()
