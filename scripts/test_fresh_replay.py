import unittest
from verify_fresh_internal_replay import check_fresh


class FreshReplay(unittest.TestCase):
    def test_old_personal_best_cannot_verify_a_new_trial(self):
        report={'mode':'control','workerReturnedNormally':True,'startedUnixNs':1000,'mapUid':'owned'}
        check_fresh(report,1001,'owned')
        for changed,time,uid in (({},999,'owned'),({},1001,'other'),({'workerReturnedNormally':False},1001,'owned'),
                                 ({'mode':'observe'},1001,'owned'),({'startedUnixNs':None},1001,'owned')):
            with self.assertRaises(ValueError):check_fresh(dict(report,**changed),time,uid)


if __name__=='__main__':unittest.main()
