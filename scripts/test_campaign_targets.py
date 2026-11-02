"""Regression: a Top-10 result must not end a Top-1 pursuit."""
import unittest
import tempfile
import contextlib
import io
from pathlib import Path
from unittest.mock import patch
from campaign_targets import set_goal,milestone,cached_goal_passed
from pursue_campaign_records import development_key


class Targets(unittest.TestCase):
    def setUp(self):
        self.metadata={'mapUid':'map-02','referenceMs':21999,'targetMs':21315}
        self.board={'sourceUrl':'https://trackmania.io/api/leaderboard/map/map-02?length=10&offset=0',
            'fetchedUtc':'2026-10-31T02:00:00Z','tops':[{'position':1,'time':21290},{'position':10,'time':21315}]}
        self.goal=set_goal(self.metadata,self.board,1)

    def result(self,time):
        return {'map':{'mapUid':'map-02'},'nominal64':{'count':64,'finishes':64,'worstMs':time},
            'development':{'finishes':4,'meanMs':time,'trials':[{'finishMs':time}]}}

    def test_top10_promotes_without_completing_top1(self):
        result=self.result(21315)
        self.assertEqual(milestone(result['development'],self.goal)['phase'],'pursuing_top1')
        self.assertFalse(cached_goal_passed(result,self.goal))
        self.assertTrue(cached_goal_passed(result,set_goal(self.metadata,self.board,10)))

    def test_wr_tie_is_insufficient_and_faster_finish_passes(self):
        self.assertFalse(cached_goal_passed(self.result(21290),self.goal))
        self.assertTrue(cached_goal_passed(self.result(21289),self.goal))
        self.assertEqual(self.goal['referenceMs'],21999)
        self.assertEqual(self.goal['targetMs'],21289) # Current board, not teacher replay time.

    def test_wrong_map_and_missing_threshold_fail(self):
        wrong=dict(self.board,sourceUrl='https://trackmania.io/api/leaderboard/map/another')
        with self.assertRaises(ValueError):set_goal(self.metadata,wrong,1)
        with self.assertRaises(ValueError):set_goal(self.metadata,dict(self.board,tops=[]),1)
        wrong_result=self.result(21200);wrong_result['map']['mapUid']='another'
        self.assertFalse(cached_goal_passed(wrong_result,self.goal))

    def test_failed_nominal_and_faster_candidate_selection(self):
        failed=self.result(None);failed['nominal64']['finishes']=0
        self.assertFalse(cached_goal_passed(failed,self.goal))
        self.assertGreater(development_key(self.result(21289)),development_key(self.result(21315)))

    def test_failed_stages_keep_progress_without_outranking_a_finish(self):
        def failed(cp,progress):
            return {'development':{'finishes':0,'meanMs':None,
                'trials':[{'finishMs':None,'checkpoints':cp,'maximumReferenceIndex':progress}]}}
        self.assertGreater(development_key(failed(3,1500)),development_key(failed(2,2100)))
        self.assertGreater(development_key(failed(3,1600)),development_key(failed(3,1500)))
        self.assertGreater(development_key(self.result(22000)),development_key(failed(5,8000)))

    def test_search_continues_past_top10_until_top1(self):
        import numpy as np
        import optimize_fall_campaign as search
        class FakeEvaluator:
            calls=0
            def __init__(self,*args,**kwargs):pass
            def evaluate(self,gains,cases,assets=None):
                FakeEvaluator.calls+=1
                time=21315 if FakeEvaluator.calls==1 else 21289
                return [dict(seed=c['seed'],finishMs=time,checkpoints=5,tick=2132,finalPosition=[0,0,0]) for c in cases],0.
            def close(self):pass
        ref=np.zeros((2200,25),dtype=np.float32)
        ref[:,0]=ref[:,4]=ref[:,8]=ref[:,12]=ref[:,22]=1;ref[:,18]=10
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'02').mkdir();map_file=root/'map.gbx';map_file.write_bytes(b'owned test identity')
            metadata=dict(self.goal,index=2,map=str(map_file))
            with patch.object(search,'NativeEvaluator',FakeEvaluator),patch.object(search,'export',return_value=(ref,{'seed':123})),contextlib.redirect_stdout(io.StringIO()):
                result=search.optimize(metadata,root,generations=2,plateau=2)
            self.assertEqual(result['generation'],1) # Generation zero already reached Top 10.
            self.assertEqual(result['stopReason'],'target_on_development')
            self.assertEqual(FakeEvaluator.calls,4) # Two search generations and two qualifications.
            self.assertTrue(result['simGoalPassed'])


if __name__=='__main__':unittest.main()
