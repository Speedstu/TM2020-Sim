"""Failure-first controller selection must not reward a lucky fast finish."""
import unittest
from tune_recording_feedback import rank


class FeedbackSelection(unittest.TestCase):
    def test_four_consistent_finishes_beat_one_fast_finish(self):
        slow=[{'finishMs':19000,'checkpoints':5} for _ in range(4)]
        lucky=[{'finishMs':18000,'checkpoints':5}]+[{'finishMs':None,'checkpoints':4} for _ in range(3)]
        self.assertGreater(rank(slow),rank(lucky))

    def test_worst_finish_and_mean_precede_lucky_best(self):
        stable=[{'finishMs':19000,'checkpoints':5} for _ in range(4)]
        variable=[{'finishMs':18000,'checkpoints':5} for _ in range(3)]+[{'finishMs':23000,'checkpoints':5}]
        self.assertGreater(rank(stable),rank(variable))

    def test_more_checkpoints_in_failed_runs_are_progress(self):
        a=[{'finishMs':None,'checkpoints':4,'maximumReferenceIndex':1200} for _ in range(4)]
        b=[{'finishMs':None,'checkpoints':3,'maximumReferenceIndex':1400} for _ in range(4)]
        self.assertGreater(rank(a),rank(b))


if __name__=='__main__':unittest.main()
