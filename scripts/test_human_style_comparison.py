import unittest
from compare_human_sim_inputs import human_style_proxy, summarize_rows

class StyleComparisonRegression(unittest.TestCase):
    def test_duration_extrema_are_checked_for_the_duration_metric(self):
        human={'empiricalMinMax':{'steeringHoldMsP10P50P90':[[10,10,20],[20,50,100]]}}
        result=human_style_proxy({'top100Runs':1,'steeringHoldMsP10P50P90':[10,10,300]},human)
        self.assertFalse(result['passes'])
        self.assertIn('steering hold P90 outside observed human range',result['failedCriteria'])

    def test_whole_lap_gas_hold_is_censored_by_finish(self):
        human={'gasDuty':1.,'gasTransitionsPerSecond':0.,'empiricalMinMax':{
            'gasPressMsP10P50P90':[[20000]*3,[21000]*3]},'empiricalP10P90':{}}
        result=human_style_proxy({'top100Runs':1,'gasDuty':1.,'gasTransitionsPerSecond':0.,
            'gasPressMsP10P50P90':[19000]*3},human)
        self.assertTrue(result['passes'])
        self.assertIn('gasPressMsP10P50P90',result['rightCensoredDurationMetricsExcluded'])
        human['gasDuty']=.8
        self.assertFalse(human_style_proxy({'top100Runs':1,'gasDuty':1.,'gasTransitionsPerSecond':0.,
            'gasPressMsP10P50P90':[19000]*3},human)['passes'])

    def test_summary_uses_median_across_runs(self):
        rows=[{'finishMs':19000,'inputs':{'steeringChangesPerSecond':v}} for v in (10.,12.,90.)]
        self.assertEqual(summarize_rows(rows,20000,'top100')['steeringChangesPerSecond'],12.)

if __name__=='__main__':unittest.main()
