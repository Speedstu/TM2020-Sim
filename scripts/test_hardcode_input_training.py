"""Performance and exact executable-input statistics, independent of imitation."""
import ctypes as C
import tempfile
import unittest
from pathlib import Path
import numpy as np
from train_hardcode_recorded_inputs import (benchmark_cases,rank,promotion_gate,mutate_reference,
    smooth_steering_reference,human_action_constraints,project_reference,mutate_route_targets,human_rhythm,mutate_pedal_intervals,mutate_pedal_rhythm)

class PerformanceSelection(unittest.TestCase):
    def test_joint_pedal_rhythm_can_cross_a_multiple_cut_local_minimum(self):
        ref=np.zeros((2200,25),dtype=np.float32);ref[:,22]=1.
        for t in (1000,1030,1060,1090):ref[t:t+3,22]=0.
        rhythm={'gasTransitionsPerSecond':4/22.,'gasReleaseMsP10P50P90':[60,70,80]}
        out,change=mutate_pedal_rhythm(ref,np.random.default_rng(77),22,rhythm)
        self.assertEqual(len(change['intervals']),2)
        self.assertEqual(np.count_nonzero(np.diff(out[:,22])),4)
        np.testing.assert_array_equal(out[:,:22],ref[:,:22]);np.testing.assert_array_equal(out[:,23:],ref[:,23:])

    def test_joint_human_fitness_rejects_fast_but_wrong_gas_rhythm(self):
        profile=human_rhythm(2)
        from compare_human_sim_inputs import METRICS
        s=profile['styleCohort'];metrics={keys[0]:s[name] for name,keys in METRICS.items() if s.get(name) is not None}
        metrics.update(ticks=2134,reversalsWithin100ms=s['reversalsWithin100msPerLap'],smallReversalsWithin100ms=s['smallReversalsWithin100msPerLap'])
        good={'finishMs':21330,'checkpoints':5,'inputs':metrics}
        bad={'finishMs':21300,'checkpoints':5,'inputs':dict(metrics,gasChangesPerSecond=10.)}
        self.assertGreater(rank([good],profile,21400,human_focus=True),rank([bad],profile,21400,human_focus=True))
        self.assertEqual(rank([good],profile,21400,human_focus=True)[0],1)

    def test_pedal_mutation_removes_and_retimes_real_gas_cuts(self):
        ref=np.zeros((600,25),dtype=np.float32);ref[:,22]=1;ref[200:205,22]=0;ref[300:307,22]=0
        seen=set()
        for seed in range(100):
            out,change=mutate_pedal_intervals(ref,np.random.default_rng(seed));seen.add(change['kind'])
            np.testing.assert_array_equal(out[:,:22],ref[:,:22]);np.testing.assert_array_equal(out[:,24],ref[:,24])
            self.assertTrue(np.isin(out[:,22:24],[0,1]).all())
        self.assertIn('removePedalInterval',seen);self.assertIn('moveResizePedalInterval',seen)

    def test_low_median_profile_preserves_pedals_and_measured_median(self):
        profile=human_rhythm(2)
        self.assertLessEqual(profile['steeringChangesPerSecond'],profile['cohortMedians']['steeringChangesPerSecond'])
        self.assertGreaterEqual(profile['steeringChangesPerSecond'],.90*profile['cohortMedians']['steeringChangesPerSecond']-1e-10)
        self.assertEqual(profile['brakeDuty'],profile['cohortMedians']['brakeDuty'])
        self.assertEqual(profile['gasDuty'],profile['cohortMedians']['gasDuty'])
        self.assertTrue(profile['completeTop100Cohort'])

    def test_route_search_changes_only_spatial_targets_with_smooth_endpoints(self):
        ref=np.zeros((1200,25),dtype=np.float32)
        ref[:,0]=ref[:,4]=ref[:,8]=1.;ref[:,22]=1.
        changed,meta=mutate_route_targets(ref,np.random.default_rng(74),600)
        np.testing.assert_array_equal(changed[:,22:25],ref[:,22:25])
        np.testing.assert_array_equal(changed[:100],ref[:100])
        np.testing.assert_array_equal(changed[-100:],ref[-100:])
        np.testing.assert_array_equal(changed[:,:9],ref[:,:9])
        self.assertGreater(np.max(np.abs(changed[:,9])),.01)
        self.assertLessEqual(np.max(np.abs(changed[:,9])),.6)
        self.assertLess(np.max(np.abs(changed[:,16:19])),2.)
        self.assertFalse(meta['physicsStateWritten'])

    def test_finish_precedes_fast_lucky_run_and_stationary_style(self):
        stable=[{'finishMs':20000,'checkpoints':5}]*4
        lucky=[{'finishMs':18000,'checkpoints':5}]+[{'finishMs':None,'checkpoints':4}]*3
        self.assertGreater(rank(stable),rank(lucky))
        self.assertGreater(rank(lucky),rank([{'finishMs':None,'checkpoints':0}]*4))

    def test_faster_is_rewarded_without_reference_target(self):
        for slower,faster in [(24000,23999),(20000,19999),(18000,17999)]:
            self.assertGreater(rank([{'finishMs':faster,'checkpoints':5}]*4),rank([{'finishMs':slower,'checkpoints':5}]*4))

    def test_top10_arrivals_are_the_search_target(self):
        target=20005
        seven=[{'finishMs':19990,'checkpoints':5}]*7+[{'finishMs':None,'checkpoints':4}]
        eight_but_slow=[{'finishMs':20010,'checkpoints':5}]*8
        self.assertGreater(rank(seven,None,target),rank(eight_but_slow,None,target))
        eight_target=[{'finishMs':19995,'checkpoints':5}]*8
        self.assertGreater(rank(eight_target,None,target),rank(seven,None,target))

    def test_human_rhythm_beats_time_only_after_top10_and_finish_counts_tie(self):
        human={'steeringChangesPerSecond':16.5,'steeringVariationPerSecond':1.3,
            'gasDuty':1.,'brakeDuty':0.,'gasTransitionsPerSecond':0.,'brakeTransitionsPerSecond':.2,
            'reversalsPerSecond':1.75,'smallReversalsPerSecond':.15,
            'rawSteeringStepP50P95P99':[0,3,8],'holdMsP50P90':[10,80],
            'gasPressMsP10P50P90':[10,20,30],'gasReleaseMsP10P50P90':[],
            'brakePressMsP10P50P90':[60,90,134],'brakeReleaseMsP10P50P90':[200,500,1000]}
        natural={'ticks':1000,'steeringChangesPerSecond':16.5,'steeringVariationPerSecond':1.3,
            'gasDuty':1.,'brakeDuty':0.,'gasChangesPerSecond':0.,'brakeChangesPerSecond':.2,
            'reversalsWithin100ms':18,'smallReversalsWithin100ms':1.5,
            'rawSteeringStepP50P95P99':[0,3,8],'steeringHoldMsP10P50P90':[10,10,80],
            'gasPressMsP10P50P90':[10,20,30],'gasReleaseMsP10P50P90':[],
            'brakePressMsP10P50P90':[60,90,134],'brakeReleaseMsP10P50P90':[200,500,1000]}
        noisy={'ticks':1000,'steeringChangesPerSecond':80.,'steeringVariationPerSecond':7.,
            'gasDuty':0.,'brakeDuty':1.,'gasChangesPerSecond':5.,'brakeChangesPerSecond':5.,
            'reversalsWithin100ms':1000,'smallReversalsWithin100ms':1000,
            'rawSteeringStepP50P95P99':[0,80,120],'steeringHoldMsP10P50P90':[500,1000,3000],
            'gasPressMsP10P50P90':[2000,3000,4000],'gasReleaseMsP10P50P90':[2000,3000,4000],
            'brakePressMsP10P50P90':[2000,3000,4000],'brakeReleaseMsP10P50P90':[2000,3000,4000]}
        smooth=[{'finishMs':20001,'checkpoints':5,'inputs':natural}]*4
        fast_but_noisy=[{'finishMs':19999,'checkpoints':5,'inputs':noisy}]*4
        self.assertGreater(rank(smooth,human,20005),rank(fast_but_noisy,human,20005))
        faster_natural=[dict(r,finishMs=19999) for r in smooth]
        self.assertGreater(rank(faster_natural,human,20005),rank(smooth,human,20005))
        # No rhythm bonus can make fewer Top 10s or finishes win.
        one_finish=[{'finishMs':19999,'checkpoints':5,'inputs':natural}]+[{'finishMs':None,'checkpoints':4}]*3
        self.assertGreater(rank(smooth,human,20005),rank(one_finish,human,20005))
        unfinished_natural=[{'finishMs':None,'checkpoints':3,'maximumReferenceIndex':800,'inputs':natural}]*4
        unfinished_noisy=[{'finishMs':None,'checkpoints':3,'maximumReferenceIndex':800,'inputs':noisy}]*4
        self.assertGreater(rank(unfinished_natural,human,20005),rank(unfinished_noisy,human,20005))

    def test_human_rhythm_beats_reference_cursor_micro_progress_when_all_finish(self):
        human={'steeringChangesPerSecond':16.5,'steeringVariationPerSecond':1.3,
            'gasDuty':1.,'brakeDuty':0.,'gasTransitionsPerSecond':0.,'brakeTransitionsPerSecond':0.,
            'reversalsPerSecond':1.75,'smallReversalsPerSecond':.15,
            'rawSteeringStepP50P95P99':[0,3,8],'holdMsP50P90':[10,80],
            'gasPressMsP10P50P90':[10,20,30],'gasReleaseMsP10P50P90':[],
            'brakePressMsP10P50P90':[],'brakeReleaseMsP10P50P90':[]}
        natural={'ticks':2000,'steeringChangesPerSecond':16.5,'steeringVariationPerSecond':1.3,
            'gasDuty':1.,'brakeDuty':0.,'gasChangesPerSecond':0.,'brakeChangesPerSecond':0.,
            'reversalsWithin100ms':35,'smallReversalsWithin100ms':3,
            'rawSteeringStepP50P95P99':[0,3,8],'steeringHoldMsP10P50P90':[10,10,80],
            'gasPressMsP10P50P90':[10,20,30],'gasReleaseMsP10P50P90':[],
            'brakePressMsP10P50P90':[],'brakeReleaseMsP10P50P90':[]}
        noisy=dict(natural,steeringChangesPerSecond=20.,steeringVariationPerSecond=2.,
            reversalsWithin100ms=90,smallReversalsWithin100ms=40,
            steeringHoldMsP10P50P90=[10,20,120])
        candidate=[{'finishMs':20000,'checkpoints':5,'maximumReferenceIndex':1999,'inputs':natural}]
        slower_style=[{'finishMs':20000,'checkpoints':5,'maximumReferenceIndex':2000,'inputs':noisy}]
        self.assertGreater(rank(candidate,human,20005),rank(slower_style,human,20005))

    def test_promotion_rejects_bc_regression_and_missing_client_replay(self):
        old=dict(finishes=38,top10Finishes=38,top10MeanMs=19000,count=64,meanMs=19000,medianMs=19000,bestMs=18900,worstMs=19500)
        new=dict(old,finishes=15,top10Finishes=15,bestMs=18800)
        arms={label:{family:dict(old) for family in ('normal64','perturbed64')} for label in ('legacyPhysical','beforeNormal','afterNormal')}
        arms['afterNormal']['normal64']=new
        self.assertFalse(promotion_gate(arms,True)['eligible'])
        arms['afterNormal']['normal64']=dict(old)
        self.assertFalse(promotion_gate(arms)['eligible'])
        self.assertTrue(promotion_gate(arms,True)['eligible'])

    def test_fixed_cases_reproduce_previous_suite(self):
        cases=benchmark_cases(3,1890)
        rng=np.random.default_rng(7030003)
        self.assertEqual([c['seed'] for c in cases['normal64']],[int(s) for s in rng.integers(1,2**32-1,64,dtype=np.uint32)])
        self.assertEqual([c['seed'] for c in cases['normal64']],[c['seed'] for c in cases['perturbed64']])
        self.assertEqual(cases,benchmark_cases(3,1890))

    def test_exploration_changes_only_executable_inputs_not_physics_states(self):
        ref=np.zeros((400,25),dtype=np.float32);ref[:,22]=1;ref[100:110,23]=1
        rng=np.random.default_rng(71);changed=False
        for _ in range(30):
            candidate,meta=mutate_reference(ref,rng)
            np.testing.assert_array_equal(candidate[:,:22],ref[:,:22])
            self.assertTrue(np.isin(candidate[:,22:24],[0,1]).all())
            np.testing.assert_allclose(candidate[:,24]*127,np.rint(candidate[:,24]*127),atol=1e-5)
            changed|=bool(np.any(candidate[:,22:]!=ref[:,22:]))
        self.assertTrue(changed)

    def test_median_smoothing_removes_an_isolated_steering_tap_only(self):
        ref=np.zeros((21,25),dtype=np.float32);ref[:,0:22]=3.;ref[:,22]=1.;ref[10,24]=8/127
        smooth=smooth_steering_reference(ref,5)
        np.testing.assert_array_equal(smooth[:,:24],ref[:,:24])
        np.testing.assert_array_equal(smooth[:,24],np.zeros(21,dtype=np.float32))
        self.assertTrue(np.allclose(smooth[:,24]*127,np.rint(smooth[:,24]*127)))

    def test_map_constraints_come_from_human_ghost_timelines_and_bound_candidates(self):
        limits=human_action_constraints(3)
        self.assertEqual(limits.shape,(29,));self.assertTrue(np.isfinite(limits).all())
        ref=np.zeros((400,25),dtype=np.float32);ref[:,22]=1.
        ref[::2,24]=1.;ref[1::2,24]=-1.;ref[::3,22]=0.
        safe=project_reference(ref,limits);steer=np.rint(safe[:,24]*127).astype(int)
        self.assertLessEqual(np.max(np.abs(np.diff(steer))),limits[0])
        self.assertLessEqual(np.max(np.abs(steer)),limits[8])
        changes=np.flatnonzero(np.diff(steer)!=0)+1
        self.assertLessEqual(len(changes),limits[9:].reshape(5,4)[:,0].sum())
        self.assertTrue(all(np.count_nonzero((changes>=start)&(changes<start+100))<=limits[1]
                            for start in range(0,len(steer),25)))
        delta=np.diff(steer);rev=[];small=[]
        for left,right in zip(changes[:-1],changes[1:]):
            a0,a1=int(delta[left-1]),int(delta[right-1])
            if right-left<=10 and (a0<0)!=(a1<0):
                rev.append(int(right*10))
                if max(abs(a0),abs(a1))<=2:small.append(int(right*10))
        for events,limit in ((rev,limits[2]),(small,limits[3])):
            for start in range(0,len(steer)*10,100):
                self.assertLessEqual(sum(start<=t<start+1000 for t in events),limit)
        for col,min_hold in ((22,limits[6]),(23,limits[7])):
            events=np.flatnonzero(np.diff(safe[:,col])!=0)+1
            self.assertLessEqual(max((sum(start<=t*10<start+1000 for t in events)
                                      for start in range(0,len(steer)*10,100)),default=0),limits[5])
            self.assertTrue(np.all(np.diff(events)*10>=min_hold))
        self.assertTrue(np.isin(safe[:,22:24],[0.,1.]).all())
        self.assertTrue(np.allclose(safe[:,24]*127,np.rint(safe[:,24]*127)))

    def test_verified_fall01_human_stream_is_inside_its_hard_action_envelope(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        human=np.load(root/'local/training/human-rework-0.70/corpus/01/leaderboard-rank1/timeline.npz')['controls']
        ref=np.zeros((len(human),25),dtype=np.float32);ref[:,22:25]=human
        projected=project_reference(ref,human_action_constraints(1))
        np.testing.assert_array_equal(projected[:,22:25],human)

    def test_fall01_contextual_reversal_reserve_keeps_rolling_human_cap(self):
        limits=human_action_constraints(1)
        # The matched-seed ablation found a local fast-reversal choke point in
        # segment four. Keep a small recovery reserve there while retaining
        # the measured rolling one-second reversal ceiling.
        self.assertEqual(limits[2],17.)
        self.assertEqual(limits[9+3*4+1],12.)

if __name__=='__main__':unittest.main()
