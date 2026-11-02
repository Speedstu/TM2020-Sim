import unittest
from monitor_hardcode_progress import diagnose,alive

class TrainingDiagnostics(unittest.TestCase):
    def test_dnf_cluster_selects_recovery_before_last_localized_tick(self):
        rows=[{'finishMs':None,'maximumReferenceIndex':1500},
              {'finishMs':None,'maximumReferenceIndex':1600}]
        plan=diagnose(2,{'stage':4,'generation':10,'stale':6,'best':{'validation':rows}}, {},22000)
        self.assertEqual(plan['primarySearchFocus'],'route-recovery')
        self.assertEqual(plan['failureFocusTick'],1445)
        self.assertTrue(plan['requestedAfterPlateau'])
        self.assertFalse(plan['inputEnvelopeChanged'])

    def test_fast_arrival_with_wrong_gas_rhythm_selects_pedal_repair(self):
        cohort={'empiricalP10P90':{'gasTransitionsPerSecond':[.1,.3]},'empiricalMinMax':{}}
        row={'finishMs':21000,'inputs':{'gasChangesPerSecond':1.}}
        plan=diagnose(2,{'stage':1,'generation':4,'stale':6,'best':{'validation':[row]}},cohort,22000)
        self.assertEqual(plan['primarySearchFocus'],'pedal-rhythm')
        self.assertEqual(plan['jointHumanTargetRuns'],0)

    def test_missing_process_is_not_reported_as_alive(self):
        self.assertFalse(alive(None));self.assertFalse(alive(999999999))

if __name__=='__main__':unittest.main()
