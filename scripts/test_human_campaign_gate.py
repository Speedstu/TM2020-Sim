import copy
import unittest
from run_hardcode_human_campaign import qualified

class CampaignQualification(unittest.TestCase):
    def setUp(self):
        arm={'top100Finishes':64,'top10Finishes':64,
             'perRunHumanTop100':{'commonStylePasses':64},'perRunHumanTop10':{'commonStylePasses':64}}
        self.report={'benchmark':{'normal64':copy.deepcopy(arm),'perturbed64':copy.deepcopy(arm)},
                     'acknowledgementMismatchTicks':0}

    def test_one_nonhuman_perturbed_run_prevents_qualification(self):
        self.assertTrue(qualified(self.report,10))
        self.report['benchmark']['perturbed64']['perRunHumanTop10']['commonStylePasses']=63
        self.assertFalse(qualified(self.report,10))

    def test_top100_success_does_not_imply_top10(self):
        self.report['benchmark']['normal64']['top10Finishes']=63
        self.assertTrue(qualified(self.report,100));self.assertFalse(qualified(self.report,10))

    def test_input_acknowledgement_failure_prevents_qualification(self):
        self.report['acknowledgementMismatchTicks']=1
        self.assertFalse(qualified(self.report,100))

if __name__=='__main__':unittest.main()
