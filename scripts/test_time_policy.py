"""Changing the training objective must preserve the selected driving policy."""
from pathlib import Path
import tempfile
import unittest
import numpy as np
from gpu_ppo import Checkpoint,Helpers
from prepare_time_policy import prepare


class TimePolicyTests(unittest.TestCase):
    def test_steering_policy_keeps_predictions_and_resets_old_objective(self):
        helper=Helpers();rng=np.random.default_rng(42);nx,na,h=48,3,8
        an=h*(nx+1)+na*(h+1);cn=h*(nx+2)+1;n=an+cn+na
        cp=Checkpoint(nx,na,h,'test|policy_actions=pedals_direct3',13,
                      (.001,.999,.97,.2,.5,0.,.5,.01),4,64,
                      rng.normal(0,.1,n),np.ones(n),np.ones(n)*2,'shuffle','sampler')
        def predict(p,x,outputs):
            head=h*(nx+1)
            hidden=np.tanh(x@p[:h*nx].reshape(h,nx).T+p[h*nx:head])
            return np.tanh(hidden@p[head:head+outputs*h].reshape(outputs,h).T+p[-outputs:])
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.checkpoint';cp.save(source,helper)
            prepared=prepare(source,root/'new',1,3e-5,1.,.03)
            x=rng.normal(size=(100,nx))
            np.testing.assert_allclose(predict(cp.parameters[:an],x,3)[:,2],
                                       predict(prepared.parameters[:prepared.actor_count],x,1)[:,0],rtol=0,atol=1e-14)
            self.assertEqual(prepared.config[1:3],(1.,1.))
            self.assertEqual(prepared.step,0);self.assertFalse(prepared.first.any());self.assertFalse(prepared.second.any())
            self.assertEqual((prepared.shuffle,prepared.sampler),(cp.shuffle,cp.sampler))
            critic=prepared.parameters[prepared.actor_count:prepared.actor_count+prepared.critic_count]
            np.testing.assert_array_equal(critic[:h*(nx+1)],cp.parameters[an:an+h*(nx+1)])
            self.assertEqual(critic[-1],.7);self.assertFalse(critic[h*(nx+1):-1].any())
            roundtrip=Checkpoint.load(root/'new/initial.checkpoint',helper)
            np.testing.assert_array_equal(prepared.parameters,roundtrip.parameters)
            # Preparation must never replace an existing experiment.
            with self.assertRaises(FileExistsError):prepare(source,root/'new',1)


if __name__=='__main__':unittest.main()
