"""A campaign-wide Top-10 barrier must exclude already qualified maps."""
import unittest
from campaign_targets import goal_for_rank,cached_goal_passed
from pursue_campaign_records import campaign_plan,selection_key


class CampaignOrder(unittest.TestCase):
    def setUp(self):
        self.indices=[2,4,7]
        self.configs={i:{'mapUid':f'map-{i}','targetMs':9999,'targetRank':1,
            'top10TargetMs':11000,'top1TargetMs':9999,'referenceMs':10000} for i in self.indices}
        self.states={i:{'state':'queued_with_changed_search','attempts':i,'selected':None} for i in self.indices}
    def result(self,i,time,count=64,finishes=64):
        return {'map':{'mapUid':f'map-{i}'},
            'nominal64':{'count':count,'finishes':finishes,'worstMs':time},
            'development':{'finishes':4,'meanMs':time,'trials':[{'finishMs':time}]}}

    def test_top10_maps_wait_even_if_they_have_fewer_attempts(self):
        self.states[2].update(attempts=0,selected=self.result(2,10500))
        self.states[4]['attempts']=100
        self.states[7]['selected']=self.result(7,9999)
        s=campaign_plan(self.states,self.configs,self.indices)
        self.assertEqual(s['targetRank'],10)
        self.assertEqual(s['todo'],[4])
        self.assertEqual(s['top10QualifiedMaps'],[2,7])

    def test_development_success_and_incomplete_holdout_cannot_unlock_phase(self):
        for i in self.indices:self.states[i]['selected']=self.result(i,10500)
        self.states[4]['selected']['nominal64']['finishes']=63
        s=campaign_plan(self.states,self.configs,self.indices)
        self.assertEqual(s['targetRank'],10);self.assertEqual(s['todo'],[4])

    def test_all_top10_unlocks_top1_and_preserves_existing_top1(self):
        for i in self.indices:self.states[i]['selected']=self.result(i,10500)
        self.states[7]['selected']=self.result(7,9999)
        s=campaign_plan(self.states,self.configs,self.indices)
        self.assertEqual(s['targetRank'],1);self.assertEqual(s['todo'],[2,4])
        self.assertEqual(s['top1QualifiedMaps'],[7])
        self.assertFalse(cached_goal_passed(self.states[2]['selected'],goal_for_rank(self.configs[2],1)))

    def test_failed_unfinished_map_blocks_top1_instead_of_silently_skipping(self):
        for i in (2,7):self.states[i]['selected']=self.result(i,10500)
        self.states[4]['state']='failed_requires_fix'
        s=campaign_plan(self.states,self.configs,self.indices)
        self.assertEqual(s['targetRank'],10);self.assertEqual(s['todo'],[])
        self.assertEqual(s['remainingTop10Maps'],[4])

    def test_all_maps_complete_and_unlimited_rounds(self):
        for i in self.indices:self.states[i]['attempts']=10000
        self.assertEqual(campaign_plan(self.states,self.configs,self.indices)['todo'],self.indices)
        for i in self.indices:self.states[i]['selected']=self.result(i,9999)
        self.assertEqual(campaign_plan(self.states,self.configs,self.indices)['todo'],[])

    def test_failed_faster_development_does_not_replace_qualified_incumbent(self):
        qualified=self.result(2,10500)
        unstable=self.result(2,10000,finishes=0)
        self.assertGreater(selection_key(qualified,self.configs[2]),selection_key(unstable,self.configs[2]))
        self.assertGreater(selection_key(self.result(2,9999),self.configs[2]),selection_key(qualified,self.configs[2]))


if __name__=='__main__':unittest.main()
